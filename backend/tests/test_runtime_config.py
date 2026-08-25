"""Tests for runtime app configuration."""

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.core.http import ApiBoundaryMiddleware
from backend.app.main import create_app


def _cors_kwargs(app):
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs
    raise AssertionError("CORS middleware was not configured")


def test_settings_parse_comma_separated_cors_origins():
    settings = Settings(cors_allowed_origins="https://ops.example.com, http://localhost:5173")

    assert settings.cors_allowed_origins == [
        "https://ops.example.com",
        "http://localhost:5173",
    ]


def test_settings_parse_cors_origins_from_environment(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://ops.example.com, http://localhost:5173",
    )

    settings = Settings()

    assert settings.cors_allowed_origins == [
        "https://ops.example.com",
        "http://localhost:5173",
    ]


def test_settings_derive_async_database_url_from_sync_database_url():
    settings = Settings(
        database_url="postgresql://incidentlens:incidentlens@db:5432/incidentlens",
        database_url_async=None,
    )

    assert (
        settings.async_database_url
        == "postgresql+asyncpg://incidentlens:incidentlens@db:5432/incidentlens"
    )


def test_settings_keep_explicit_async_database_url():
    settings = Settings(
        database_url="postgresql://incidentlens:incidentlens@db:5432/incidentlens",
        database_url_async="postgresql+asyncpg://custom:custom@db:5432/custom",
    )

    assert settings.async_database_url == "postgresql+asyncpg://custom:custom@db:5432/custom"


def test_create_app_uses_runtime_metadata_and_cors_origins():
    settings = Settings(
        app_name="IncidentLens Test",
        app_version="9.8.7",
        cors_allowed_origins=["https://dashboard.example.com"],
    )

    app = create_app(settings=settings, run_startup_migrations=False)

    assert app.title == "IncidentLens Test"
    assert app.version == "9.8.7"
    assert _cors_kwargs(app)["allow_origins"] == ["https://dashboard.example.com"]
    assert _cors_kwargs(app)["allow_credentials"] is True


def test_wildcard_cors_disables_credentials():
    app = create_app(Settings(cors_allowed_origins="*"), run_startup_migrations=False)

    assert _cors_kwargs(app)["allow_origins"] == ["*"]
    assert _cors_kwargs(app)["allow_credentials"] is False


def test_create_app_registers_root_health_endpoint():
    app = create_app(Settings(), run_startup_migrations=False)

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_app_exposes_prometheus_metrics():
    app = create_app(Settings(), run_startup_migrations=False)

    with TestClient(app) as client:
        client.get("/healthz")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "incidentlens_http_requests_total" in response.text
    assert response.headers["content-type"].startswith("text/plain")


def test_http_boundary_adds_request_and_security_headers():
    app = create_app(Settings(), run_startup_migrations=False)

    with TestClient(app) as client:
        response = client.get("/healthz", headers={"X-Request-ID": "trace-123"})

    assert response.headers["X-Request-ID"] == "trace-123"
    assert float(response.headers["X-Process-Time-Ms"]) >= 0
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_api_key_protects_mutations_but_not_health():
    app = create_app(Settings(api_key="secret"), run_startup_migrations=False)

    with TestClient(app) as client:
        health = client.get("/healthz")
        rejected = client.post("/api/services", json={"name": "billing"})
        authenticated = client.post(
            "/api/services",
            json={},
            headers={"X-API-Key": "secret"},
        )

    assert health.status_code == 200
    assert rejected.status_code == 401
    assert authenticated.status_code == 422


def test_http_boundary_rejects_oversized_payloads():
    app = create_app(
        Settings(max_request_body_bytes=8),
        run_startup_migrations=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/logs/single", content="0123456789")

    assert response.status_code == 413


def test_ingestion_rate_limit_returns_retry_after(monkeypatch):
    async def always_limited(self, request, supplied_key):
        return True

    monkeypatch.setattr(ApiBoundaryMiddleware, "_is_rate_limited", always_limited)
    app = create_app(
        Settings(ingest_rate_limit_per_minute=1),
        run_startup_migrations=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/logs/single", json={})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
