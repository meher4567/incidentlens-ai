"""Focused anomaly-detector contracts."""

from datetime import datetime, timezone

import numpy as np

from backend.app.models.metrics import MetricWindow
from backend.app.services.detection import detect_isolation_forest, detect_mad


class _IFModel:
    def __init__(self, prediction=-1, score=-0.15, *, fail=False):
        self.prediction = prediction
        self.score = score
        self.fail = fail
        self.calls = 0

    def decision_function(self, matrix):
        self.calls += 1
        if self.fail:
            raise ValueError("bad model")
        return np.array([self.score])

    def predict(self, matrix):
        return np.array([self.prediction])


def _window(service_id, *, size=300, p95=120):
    return MetricWindow(
        service_id=service_id,
        window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        window_size_seconds=size,
        request_count=100,
        error_count=1,
        error_rate=0.01,
        p50_latency_ms=80,
        p95_latency_ms=p95,
        unique_messages=10,
        baseline_request_count_median=100,
        baseline_request_count_mad=2,
        baseline_error_rate_median=0.005,
        baseline_error_rate_mad=0.01,
        baseline_p95_latency_median=100,
        baseline_p95_latency_mad=5,
    )


def test_isolation_forest_only_scores_training_granularity(db_session, seed_services):
    model = _IFModel()
    service_id = seed_services["api-gateway"].id

    assert (
        detect_isolation_forest(db_session, _window(service_id, size=60), {service_id: model}) == []
    )
    assert model.calls == 0


def test_isolation_forest_emits_one_truthful_multivariate_anomaly(db_session, seed_services):
    service_id = seed_services["api-gateway"].id
    model = _IFModel(prediction=-1, score=-0.25)

    result = detect_isolation_forest(db_session, _window(service_id), {service_id: model})

    assert len(result) == 1
    assert result[0]["metric"] == "multivariate"
    assert result[0]["score"] == 0.25
    assert result[0]["severity"] == "CRITICAL"


def test_isolation_forest_ignores_normal_invalid_and_failed_rows(db_session, seed_services):
    service_id = seed_services["api-gateway"].id

    assert (
        detect_isolation_forest(
            db_session, _window(service_id), {service_id: _IFModel(prediction=1)}
        )
        == []
    )
    assert (
        detect_isolation_forest(
            db_session,
            _window(service_id, p95=float("nan")),
            {service_id: _IFModel()},
        )
        == []
    )
    assert (
        detect_isolation_forest(db_session, _window(service_id), {service_id: _IFModel(fail=True)})
        == []
    )
    assert detect_isolation_forest(db_session, _window(service_id), {}) == []


def test_mad_direction_and_severity_rules(db_session, seed_services):
    service_id = seed_services["api-gateway"].id
    window = _window(service_id, p95=200)
    window.request_count = 80
    window.error_rate = 0.2

    results = detect_mad(db_session, window)

    assert {row["metric"] for row in results} == {
        "request_count",
        "error_rate",
        "p95_latency_ms",
    }
    assert all(row["severity"] in {"HIGH", "CRITICAL"} for row in results)
