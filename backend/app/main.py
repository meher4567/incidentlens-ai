from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as sa_text

from backend.app.api import router as api_router
from backend.app.core.config import get_settings
from backend.app.db.migrate import run_migrations
from backend.app.db.session import sync_engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run Alembic migrations
    run_migrations()
    yield
    # Shutdown
    sync_engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/healthz")
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
