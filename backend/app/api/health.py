from datetime import datetime, timezone

from fastapi import APIRouter, Response, status
from redis import Redis
from sqlalchemy import text as sa_text

from backend.app.core.config import get_settings
from backend.app.db.session import sync_engine

router = APIRouter()
settings = get_settings()


@router.get("/health")
def extended_health(response: Response):
    """Extended health check with Redis and DB status."""
    try:
        with sync_engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    try:
        redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        redis_ok = bool(redis_client.ping())
    except Exception:
        redis_ok = False

    status = "ok" if db_ok and redis_ok else "degraded"
    if not db_ok:
        response.status_code = 503

    return {
        "status": status,
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
def readiness(response: Response):
    """Readiness requires the database used by every dashboard request."""
    try:
        with sync_engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": "disconnected"}
    return {"status": "ready", "database": "connected"}
