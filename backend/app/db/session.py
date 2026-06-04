from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.app.core.config import get_settings

settings = get_settings()

SYNC_DATABASE_URL = settings.database_url
ASYNC_DATABASE_URL = settings.database_url_async

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


def get_sync_session():
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()


async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session
