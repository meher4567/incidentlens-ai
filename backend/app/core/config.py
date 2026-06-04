from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://incidentlens:incidentlens@localhost:5432/incidentlens"
    database_url_async: str = (
        "postgresql+asyncpg://incidentlens:incidentlens@localhost:5432/incidentlens"
    )
    redis_url: str = "redis://localhost:6379/0"
    app_name: str = "IncidentLens AI"
    debug: bool = False
    seed: int = 42
    batch_max_size: int = 1000
    window_sizes_seconds: list[int] = [60, 300]
    baseline_window_count: int = 30
    mad_threshold_default: float = 4.0
    mad_floor_error_rate: float = 0.001
    mad_floor_p95_latency: float = 5.0
    mad_floor_request_count: float = 1.0
    dedup_same_service_window_minutes: int = 5
    dedup_shared_trace_window_minutes: int = 2
    incident_proximity_minutes: int = 5
    incident_close_minutes: int = 10
    watermark_grace_minutes: int = 5
    models_dir: str = "models"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
