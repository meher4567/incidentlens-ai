from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "IncidentLens AI"
    app_version: str = "0.1.0"
    cors_allowed_origins: str | list[str] = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = "postgresql://incidentlens:incidentlens@localhost:5432/incidentlens"
    database_url_async: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    debug: bool = False
    api_key: str | None = None
    ingest_rate_limit_per_minute: int = 0
    max_request_body_bytes: int = 5_000_000
    run_startup_migrations: bool = True
    seed: int = 42
    batch_max_size: int = 1000
    window_sizes_seconds: list[int] = [60, 300]
    baseline_window_count: int = 30
    mad_threshold_default: float = 4.0
    mad_floor_error_rate: float = 0.01
    mad_floor_p95_latency: float = 5.0
    mad_floor_request_count: float = 1.0
    dedup_same_service_window_minutes: int = 5
    dedup_shared_trace_window_minutes: int = 2
    dedup_max_component_minutes: int = 15
    alert_max_duration_minutes: int = 10
    incident_proximity_minutes: int = 5
    incident_close_minutes: int = 10
    incident_max_duration_minutes: int = 15
    watermark_grace_minutes: int = 5
    models_dir: str = "models"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def cors_origins(self) -> list[str]:
        if isinstance(self.cors_allowed_origins, str):
            return [
                origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()
            ]
        return self.cors_allowed_origins

    @property
    def cors_allow_credentials(self) -> bool:
        """Browsers reject credentialed CORS when every origin is allowed."""
        return "*" not in self.cors_origins

    @property
    def async_database_url(self) -> str:
        if self.database_url_async:
            return self.database_url_async
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return self.database_url


@lru_cache()
def get_settings() -> Settings:
    return Settings()
