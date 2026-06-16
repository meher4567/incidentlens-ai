from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as sa_text

from backend.app.api import router as api_router
from backend.app.core.config import Settings, get_settings
from backend.app.db.migrate import run_migrations
from backend.app.db.session import sync_engine


async def healthz():
    """Health check endpoint."""
    try:
        with sync_engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def create_app(
    settings: Settings | None = None,
    *,
    run_startup_migrations: bool = True,
) -> FastAPI:
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_startup_migrations:
            run_migrations()
        yield
        sync_engine.dispose()

    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")
    app.add_api_route("/healthz", healthz, methods=["GET"])
    return app


app = create_app()
