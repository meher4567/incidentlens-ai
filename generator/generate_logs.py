"""
Synthetic microservice log generator for IncidentLens AI.

Produces logs.jsonl + incidents_truth.jsonl with 5 training services,
Poisson-distributed request rates, log-normal latencies, trace_id propagation,
and 5 incident types (3 training, 2 held-out).

Usage:
    python -m generator.generate_logs --events 100000 --output logs.jsonl --truth incidents_truth.jsonl
"""
import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping config in {config_path}")
    return data


def floor_dt(dt: datetime, seconds: int) -> datetime:
    ts = dt.timestamp()
    return datetime.fromtimestamp((ts // seconds) * seconds, tz=timezone.utc)


class LogGenerator:
    def __init__(self, config: dict, seed: int = 42):
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.random = random.Random(seed)
        self.service_configs: dict[str, dict] = {}
        self.dep_graph: dict[str, list[str]] = {}
        self._init_services()

    def _init_services(self):
        for svc in self.config["services"]:
            self.service_configs[svc["name"]] = svc
            self.dep_graph[svc["name"]] = []

        for dep in self.config["dependencies"]:
            up = dep["upstream"]
            down = dep["downstream"]
            if up in self.dep_graph and down in self.service_configs:
                self.dep_graph[up].append(down)
            if down not in self.dep_graph:
                self.dep_graph[down] = []

    def _log_normal_sample(self, mean_ms: float) -> float:
        """Sample from log-normal with given p95. Approximate mu/sigma."""
        mu = np.log(mean_ms / 2.5)
        sigma = 0.5
        return float(self.rng.lognormal(mu, sigma))

    def _generate_trace(self, service: str, t: datetime) -> list[dict]:
        """Generate a request chain along the dependency graph."""
        events: list[dict] = []
        trace_id = uuid.uuid4()
        upstream = service
        while upstream:
            cfg = self.service_configs[upstream]
            request_id = uuid.uuid4()
            latency_ms = int(self._log_normal_sample(cfg["p95_latency_ms"]))
            is_error = self.rng.random() < cfg["error_rate"]
            status_code = 500 if is_error else 200
            level = "ERROR" if is_error else self.random.choice(cfg["log_levels"])

            msg = f"{upstream} processed request {request_id}"
            if is_error:
                msg = f"{upstream} ERROR: request {request_id} failed with status {status_code}"

            events.append(
                {
                    "timestamp": t.isoformat(),
                    "service": upstream,
                    "level": level,
                    "message": msg,
                    "request_id": str(request_id),
                    "trace_id": str(trace_id),
                    "latency_ms": latency_ms,
                    "status_code": status_code,
                    "host": f"{upstream}-pod-{self.random.randint(1, 5)}",
                    "region": "us-west-2",
                }
            )

            # Propagate to one random downstream
            downstreams = self.dep_graph.get(upstream, [])
            if downstreams:
                upstream = self.random.choice(downstreams)
                t = t + timedelta(milliseconds=latency_ms + float(self.rng.exponential(10)))
            else:
                break
        return events

    def _apply_incident_perturbation(
        self, event: dict, incident_type: str, is_root: bool, is_affected: bool
    ) -> dict | None:
        """Mutate log events during an incident window."""
        e = dict(event)
        if incident_type == "payment_latency_spike":
            if is_root:
                e["latency_ms"] = int(self.rng.lognormal(7.3, 0.3))
                if self.rng.random() < 0.3:
                    e["level"] = "ERROR"
                    e["status_code"] = 504
                    e["message"] = f"{e['service']} ERROR: gateway timeout"
            elif is_affected:
                e["latency_ms"] = int(e.get("latency_ms", 100) * 2.5)
                if self.rng.random() < 0.15:
                    e["level"] = "ERROR"
                    e["status_code"] = 504

        elif incident_type == "auth_error_spike":
            if is_root:
                if self.rng.random() < 0.3:
                    e["level"] = "ERROR"
                    e["status_code"] = 401
                    e[
                        "message"
                    ] = f"{e['service']} ERROR: AuthenticationFailed for user {uuid.uuid4().hex[:8]}"
            elif is_affected:
                if self.rng.random() < 0.2:
                    e["level"] = "ERROR"
                    e["status_code"] = 502
                    e["message"] = f"{e['service']} ERROR: upstream auth failure"

        elif incident_type == "inventory_traffic_drop":
            if is_root:
                if self.rng.random() < 0.8:
                    return None  # Drop event entirely
            elif is_affected:
                if self.rng.random() < 0.1:
                    e["level"] = "ERROR"
                    e["status_code"] = 503
                    e["message"] = f"{e['service']} ERROR: inventory service unavailable"

        elif incident_type == "db_timeout_cascade":
            if is_root or is_affected:
                if self.rng.random() < 0.2:
                    e["level"] = "ERROR"
                    e["status_code"] = 504
                    e["latency_ms"] = int((e.get("latency_ms", 100) or 100) * 3)
                    e["message"] = f"{e['service']} ERROR: database query timeout"

        elif incident_type == "notification_silent_fail":
            if is_root:
                if self.rng.random() < 0.25:
                    e["level"] = "ERROR"
                    e["status_code"] = 500
                    e["message"] = f"{e['service']} ERROR: notification delivery failed silently"

        return e

    def generate(self, total_events: int) -> tuple[list[dict], list[dict]]:
        log_events: list[dict] = []
        truth_incidents: list[dict] = []

        base_time = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(hours=24)
        total_rate = sum(s["req_per_min"] for s in self.config["services"]) / 60.0
        current_time = base_time

        # Generate incident schedule
        incident_schedule: list[dict] = []
        all_incidents = self.config["incidents"]["training"] + self.config["incidents"]["held_out"]
        for inc_cfg in all_incidents:
            count = inc_cfg.get("count", 20)
            start_offset = inc_cfg["start_offset_seconds"]
            duration = inc_cfg["duration_seconds"]
            for i in range(count):
                offset_jitter = int(self.rng.integers(0, 1200))  # spread within 20 min
                istart = base_time + timedelta(seconds=start_offset + offset_jitter)
                iend = istart + timedelta(seconds=duration + int(self.rng.integers(0, 300)))
                incident_schedule.append(
                    {
                        "incident_id": uuid.uuid4(),
                        "type": inc_cfg["type"],
                        "start_time": istart,
                        "end_time": iend,
                        "root_cause": inc_cfg["root_cause"],
                        "training": inc_cfg in self.config["incidents"]["training"],
                    }
                )

        # Sort by start time
        incident_schedule.sort(key=lambda x: x["start_time"])

        # Generate log events
        generated = 0
        while generated < total_events:
            # Inter-arrival time (Poisson)
            dt = float(self.rng.exponential(1.0 / total_rate))
            current_time += timedelta(seconds=dt)

            service = self.random.choice(list(self.service_configs.keys()))
            events = self._generate_trace(service, current_time)

            # Check if within any incident window
            for inc in incident_schedule:
                if inc["start_time"] <= current_time <= inc["end_time"]:
                    root_cause = inc["root_cause"]
                    # Determine if this service is root or affected
                    is_root = any(e["service"] == root_cause for e in events)
                    is_affected = any(
                        e["service"] != root_cause
                        for e in events
                        if self._is_affected(e["service"], root_cause, inc["type"])
                    )
                    perturbed_events: list[dict] = []
                    for event in events:
                        perturbed = self._apply_incident_perturbation(
                            event,
                            inc["type"],
                            is_root,
                            is_affected,
                        )
                        if perturbed is not None:
                            perturbed_events.append(perturbed)
                    events = perturbed_events
                    break

            log_events.extend(events)
            generated += len(events)

        # Sort by timestamp
        log_events.sort(key=lambda e: e["timestamp"])

        # Build truth incidents
        for inc in incident_schedule:
            affected = self._get_affected_services(inc["root_cause"], inc["type"])
            truth_incidents.append(
                {
                    "truth_incident_id": str(inc["incident_id"]),
                    "type": inc["type"],
                    "start_time": inc["start_time"].isoformat(),
                    "end_time": inc["end_time"].isoformat(),
                    "root_cause_service": inc["root_cause"],
                    "affected_services": affected,
                    "training": inc["training"],
                }
            )

        return log_events[:total_events], truth_incidents

    def _is_affected(self, service: str, root_cause: str, inc_type: str) -> bool:
        """Check if a service is downstream of root cause."""
        if service == root_cause:
            return True
        visited: set[str] = set()
        stack = [root_cause]
        while stack:
            node = stack.pop()
            if node == service:
                return True
            if node not in visited:
                visited.add(node)
                stack.extend(self.dep_graph.get(node, []))
        return False

    def _get_affected_services(self, root_cause: str, inc_type: str) -> list[str]:
        affected = {root_cause}
        stack = [root_cause]
        while stack:
            node = stack.pop()
            for down in self.dep_graph.get(node, []):
                if down not in affected:
                    affected.add(down)
                    stack.append(down)
        # For held-out notification type, add notification-service
        if inc_type == "notification_silent_fail":
            affected.add("notification-service")
        return sorted(affected)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic logs for IncidentLens")
    parser.add_argument("--events", type=int, default=100000, help="Number of log events")
    parser.add_argument("--output", type=str, default="logs.jsonl", help="Output logs file")
    parser.add_argument(
        "--truth", type=str, default="incidents_truth.jsonl", help="Truth incidents file"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--config", type=str, default="generator/config.yaml", help="Config file path"
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    generator = LogGenerator(config, seed=args.seed)

    print(f"Generating {args.events} log events with seed={args.seed}...")
    logs, truth = generator.generate(args.events)

    with open(args.output, "w") as f:
        for log in logs:
            f.write(json.dumps(log) + "\n")
    print(f"Wrote {len(logs)} log events to {args.output}")

    with open(args.truth, "w") as f:
        for inc in truth:
            f.write(json.dumps(inc) + "\n")
    print(f"Wrote {len(truth)} incident truths to {args.truth}")


if __name__ == "__main__":
    main()
