"""Tests for runtime app configuration."""

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _cors_kwargs(app):
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs
    raise AssertionError("CORS middleware was not configured")


def test_settings_parse_comma_separated_cors_origins():
    settings = Settings(
        cors_allowed_origins="https://ops.example.com, http://localhost:5173"
    )

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


def test_create_app_registers_root_health_endpoint():
    app = create_app(Settings(), run_startup_migrations=False)

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}
