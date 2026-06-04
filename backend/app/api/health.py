from datetime import datetime, timezone

from fastapi import APIRouter
from redis import Redis
from sqlalchemy import text as sa_text

from backend.app.core.config import get_settings
from backend.app.db.session import sync_engine

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def extended_health():
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

    return {
        "status": status,
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
