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
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.random = random.Random(seed)
        self.service_configs: dict[str, dict] = {}
        self.dep_graph: dict[str, list[str]] = {}
        self._init_services()

    def _random_uuid(self) -> uuid.UUID:
        """Return a deterministic UUID from the generator's seeded RNG."""
        return uuid.UUID(int=self.random.getrandbits(128), version=4)

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
        trace_id = self._random_uuid()
        upstream = service
        while upstream:
            cfg = self.service_configs[upstream]
            request_id = self._random_uuid()
            latency_ms = int(self._log_normal_sample(cfg["p95_latency_ms"]))
            is_error = self.rng.random() < cfg["error_rate"]
            status_code = 500 if is_error else 200
            normal_levels = [
                level for level in cfg["log_levels"] if level not in {"ERROR", "CRITICAL"}
            ]
            level = "ERROR" if is_error else self.random.choice(normal_levels or ["INFO"])

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
                    user_id = self._random_uuid().hex[:8]
                    e["message"] = f"{e['service']} ERROR: AuthenticationFailed for user {user_id}"
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

    def generate(
        self,
        total_events: int,
        *,
        duration_seconds: float | None = None,
        base_time: datetime | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Generate a deterministic, fully-covered scenario dataset.

        ``duration_seconds`` controls event-time coverage independently of data
        volume. This lets a CI-sized dataset cover the same warm-up, training,
        and held-out periods as the full demo.
        """
        if total_events <= 0:
            raise ValueError("total_events must be greater than zero")

        log_events: list[dict] = []
        truth_incidents: list[dict] = []

        if base_time is None:
            configured_base = self.config.get("base_time")
            if configured_base:
                base_time = datetime.fromisoformat(str(configured_base).replace("Z", "+00:00"))
            else:
                base_time = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) - timedelta(hours=24)
        if base_time.tzinfo is None or base_time.utcoffset() is None:
            base_time = base_time.replace(tzinfo=timezone.utc)
        else:
            base_time = base_time.astimezone(timezone.utc)

        if duration_seconds is None and self.config.get("duration_hours") is not None:
            duration_seconds = float(self.config["duration_hours"]) * 3600.0
        if duration_seconds is not None and duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")

        total_rate = sum(s["req_per_min"] for s in self.config["services"]) / 60.0
        current_time = base_time
        scenario_version = str(self.config.get("scenario_version", "1.0"))
        generator_run_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"incidentlens:{scenario_version}:{self.seed}:{base_time.isoformat()}:{total_events}",
        )

        # Generate incident schedule
        incident_schedule: list[dict] = []
        for split in ("training", "held_out"):
            for inc_cfg in self.config["incidents"][split]:
                count = int(inc_cfg.get("count", 1))
                start_offset = int(inc_cfg["start_offset_seconds"])
                spacing = int(inc_cfg.get("spacing_seconds", 1200))
                duration = int(inc_cfg["duration_seconds"])
                for index in range(count):
                    istart = base_time + timedelta(seconds=start_offset + index * spacing)
                    iend = istart + timedelta(seconds=duration)
                    incident_id = uuid.uuid5(
                        generator_run_id,
                        f"{split}:{inc_cfg['type']}:{index}",
                    )
                    incident_schedule.append(
                        {
                            "incident_id": incident_id,
                            "type": inc_cfg["type"],
                            "start_time": istart,
                            "end_time": iend,
                            "root_cause": inc_cfg["root_cause"],
                            "affected_metric": inc_cfg["affected_metric"],
                            "split": split,
                        }
                    )

        # Sort by start time
        incident_schedule.sort(key=lambda x: x["start_time"])

        # Generate log events
        generated = 0
        while generated < total_events:
            service_names = list(self.service_configs)
            service_weights = [self.service_configs[name]["req_per_min"] for name in service_names]
            service = self.random.choices(service_names, weights=service_weights, k=1)[0]
            events = self._generate_trace(service, current_time)
            original_event_count = len(events)

            # Check if within any incident window
            for inc in incident_schedule:
                if inc["start_time"] <= current_time <= inc["end_time"]:
                    root_cause = inc["root_cause"]
                    perturbed_events: list[dict] = []
                    for event in events:
                        is_root = event["service"] == root_cause
                        is_affected = self._is_affected(event["service"], root_cause)
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

            if duration_seconds is None:
                dt = float(self.rng.exponential(1.0 / total_rate))
            else:
                mean_step = duration_seconds * max(original_event_count, 1) / total_events
                dt = float(self.rng.exponential(mean_step))
            current_time += timedelta(seconds=dt)

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
                    "affected_metric": inc["affected_metric"],
                    "split": inc["split"],
                    "generator_run_id": str(generator_run_id),
                    "seed": self.seed,
                    "scenario_version": scenario_version,
                }
            )

        return log_events[:total_events], truth_incidents

    def _is_affected(self, service: str, root_cause: str) -> bool:
        """Return whether a dependency failure can propagate to ``service``.

        Edges point from caller to dependency. A failed dependency affects the
        root itself and callers that can reach it, not services below the root.
        """
        if service == root_cause:
            return True
        visited: set[str] = set()
        stack = [service]
        while stack:
            node = stack.pop()
            if node == root_cause:
                return True
            if node not in visited:
                visited.add(node)
                stack.extend(self.dep_graph.get(node, []))
        return False

    def _get_affected_services(self, root_cause: str, inc_type: str) -> list[str]:
        del inc_type  # retained for backwards-compatible call sites
        return sorted(
            service for service in self.service_configs if self._is_affected(service, root_cause)
        )


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic logs for IncidentLens")
    parser.add_argument("--events", type=int, default=100000, help="Number of log events")
    parser.add_argument("--output", type=str, default="logs.jsonl", help="Output logs file")
    parser.add_argument(
        "--truth", type=str, default="incidents_truth.jsonl", help="Truth incidents file"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--duration-hours",
        type=float,
        default=None,
        help="Event-time coverage; defaults to duration_hours in the config",
    )
    parser.add_argument(
        "--base-time",
        type=str,
        default=None,
        help="ISO-8601 dataset start; defaults to base_time in the config",
    )
    parser.add_argument(
        "--config", type=str, default="generator/config.yaml", help="Config file path"
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    generator = LogGenerator(config, seed=args.seed)

    duration_seconds = args.duration_hours * 3600.0 if args.duration_hours else None
    base_time = (
        datetime.fromisoformat(args.base_time.replace("Z", "+00:00")) if args.base_time else None
    )
    print(f"Generating {args.events} log events with seed={args.seed}...")
    logs, truth = generator.generate(
        args.events,
        duration_seconds=duration_seconds,
        base_time=base_time,
    )

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
