"""Contracts for the deterministic, labeled synthetic data generator."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from generator.generate_logs import LogGenerator, load_config

CONFIG_PATH = Path(__file__).parents[2] / "generator" / "config.yaml"


def test_generator_is_reproducible_and_covers_scenario() -> None:
    config = load_config(CONFIG_PATH)

    first_logs, first_truth = LogGenerator(config, seed=42).generate(2_000)
    second_logs, second_truth = LogGenerator(config, seed=42).generate(2_000)

    assert first_logs == second_logs
    assert first_truth == second_truth
    assert len(first_truth) == 18
    assert {row["split"] for row in first_truth} == {"training", "held_out"}
    assert {row["scenario_version"] for row in first_truth} == {"2.0"}

    start = datetime.fromisoformat(first_logs[0]["timestamp"])
    end = datetime.fromisoformat(first_logs[-1]["timestamp"])
    assert (end - start).total_seconds() > 7 * 3600


def test_healthy_events_never_inherit_error_log_levels() -> None:
    config = deepcopy(load_config(CONFIG_PATH))
    for service in config["services"]:
        service["error_rate"] = 0.0

    generator = LogGenerator(config, seed=7)
    events = []
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(250):
        events.extend(generator._generate_trace("api-gateway", timestamp))

    assert events
    assert all(event["level"] not in {"ERROR", "CRITICAL"} for event in events)
    assert all(event["status_code"] < 500 for event in events)


def test_truth_affected_services_follow_callers_of_root() -> None:
    config = load_config(CONFIG_PATH)
    generator = LogGenerator(config, seed=42)

    assert generator._get_affected_services("payment-service", "ignored") == [
        "api-gateway",
        "checkout-service",
        "payment-service",
    ]
    assert generator._get_affected_services("auth-service", "ignored") == [
        "api-gateway",
        "auth-service",
    ]
