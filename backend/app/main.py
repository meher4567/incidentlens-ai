from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from backend.app.api import router as api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.http import ApiBoundaryMiddleware
from backend.app.db.migrate import run_migrations
from backend.app.db.session import sync_engine


def healthz():
    """Cheap process liveness probe with no downstream dependencies."""
    return {"status": "ok"}


def metrics():
    """Expose Prometheus metrics without coupling them to dashboard metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def create_app(
    settings: Settings | None = None,
    *,
    run_startup_migrations: bool | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    should_migrate = (
        active_settings.run_startup_migrations
        if run_startup_migrations is None
        else run_startup_migrations
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if should_migrate:
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
        allow_credentials=active_settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ApiBoundaryMiddleware, settings=active_settings)

    app.include_router(api_router, prefix="/api")
    app.add_api_route("/healthz", healthz, methods=["GET"])
    app.add_api_route("/metrics", metrics, methods=["GET"], include_in_schema=False)
    return app


app = create_app()
