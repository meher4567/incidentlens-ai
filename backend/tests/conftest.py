"""
Pytest conftest — SQLite/Postgres dual-backend test support.

For SQLite (local): patches Postgres-specific types (UUID, ARRAY, JSONB)
into SQLite-compatible TypeDecorators at module import time.
For Postgres (CI via DATABASE_URL env): uses native types.
"""

import json
import os
import uuid

# Detect backend early
_TEST_DB_URL = os.environ.get("DATABASE_URL", "")
if not _TEST_DB_URL:
    _TEST_DB_URL = "sqlite:///:memory:"
_IS_SQLITE = "sqlite" in _TEST_DB_URL

# For SQLite: import and patch models BEFORE anything else uses them
if _IS_SQLITE:
    from sqlalchemy import String
    from sqlalchemy.types import CHAR, TypeDecorator

    # Define SQLite-compatible type replacements
    class _CompatUUID(TypeDecorator):
        impl = CHAR(36)
        cache_ok = True

        def load_dialect_impl(self, dialect):
            return dialect.type_descriptor(CHAR(36))

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            return str(value) if isinstance(value, uuid.UUID) else str(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, uuid.UUID):
                return value
            try:
                return uuid.UUID(str(value))
            except (ValueError, AttributeError):
                return value

    class _CompatJSONB(TypeDecorator):
        impl = String(4096)
        cache_ok = True

        def load_dialect_impl(self, dialect):
            return dialect.type_descriptor(String(4096))

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            return json.dumps(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return {}
            return value

    class _CompatARRAY(TypeDecorator):
        impl = String(4096)
        cache_ok = True

        def load_dialect_impl(self, dialect):
            return dialect.type_descriptor(String(4096))

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            return json.dumps([str(v) if isinstance(v, uuid.UUID) else v for v in (value or [])])

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    result = []
                    for item in parsed:
                        if not isinstance(item, str):
                            result.append(item)
                            continue
                        try:
                            result.append(uuid.UUID(item))
                        except ValueError:
                            result.append(item)
                    return result
                except json.JSONDecodeError:
                    return []
            return list(value) if value else []

    # Force-import all models to populate Base.metadata, then patch
    from backend.app.db.session import Base
    from backend.app.models import *  # noqa: F401, F403 - triggers all model imports

    for table_name, table in Base.metadata.tables.items():
        for col in table.columns:
            col_type = type(col.type)
            type_name = col_type.__name__
            module_name = col_type.__module__

            if "UUID" in type_name or "uuid" in module_name.lower():
                col.type = _CompatUUID()
            elif (
                "JSONB" in type_name
                or "json" in type_name.lower()
                or "jsonb" in module_name.lower()
            ):
                col.type = _CompatJSONB()
            elif "ARRAY" in type_name or "array" in module_name.lower():
                col.type = _CompatARRAY()

# Now safe to import pytest and remaining fixtures
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import Base


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test. Uses transactional rollback on Postgres."""
    if _IS_SQLITE:
        engine = create_engine(
            _TEST_DB_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
            Base.metadata.drop_all(bind=engine)
            engine.dispose()
    else:
        # Postgres: use per-function engine with create_all for schema setup
        engine = create_engine(_TEST_DB_URL)
        # Create tables if they don't exist (for CI where Alembic may not have run)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.rollback()
            session.close()
            # Drop all tables for clean isolation between tests
            Base.metadata.drop_all(bind=engine)
            engine.dispose()


@pytest.fixture(scope="function")
def seed_services(db_session):
    from backend.app.models.services import Service

    service_names = [
        "api-gateway",
        "auth-service",
        "checkout-service",
        "payment-service",
        "inventory-service",
        "notification-service",
    ]
    services = {}
    for name in service_names:
        svc = Service(name=name)
        db_session.add(svc)
        db_session.flush()
        services[name] = svc
    db_session.commit()
    return services


@pytest.fixture(scope="function")
def seed_dependencies(db_session, seed_services):
    from backend.app.models.services import ServiceDependency

    deps = [
        ("api-gateway", "auth-service"),
        ("api-gateway", "checkout-service"),
        ("checkout-service", "payment-service"),
        ("checkout-service", "inventory-service"),
        ("checkout-service", "notification-service"),
    ]
    for up_name, down_name in deps:
        dep = ServiceDependency(
            upstream_id=seed_services[up_name].id,
            downstream_id=seed_services[down_name].id,
        )
        db_session.add(dep)
    db_session.commit()
    return seed_services
