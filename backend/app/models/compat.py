"""
Type compatibility layer: works with Postgres ARRAY/UUID/JSONB natively,
falls back to SQLite-compatible variants (JSON text) for local testing.
"""
import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.types import CHAR, TypeDecorator


class CompatUUID(TypeDecorator):
    """UUID that works in both Postgres (native) and SQLite (text fallback)."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            if isinstance(value, str):
                return uuid.UUID(value)
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(value)
        except (ValueError, AttributeError):
            return value


def CompatARRAY(item_type):
    """ARRAY that works in Postgres natively, falls back to text in SQLite."""

    class CompatArrayType(TypeDecorator):
        impl = String(4096)
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == "postgresql":
                if hasattr(item_type, "as_uuid") and getattr(item_type, "as_uuid", False):
                    return dialect.type_descriptor(ARRAY(UUID(as_uuid=True)))
                return dialect.type_descriptor(ARRAY(item_type))
            return dialect.type_descriptor(String(4096))

        def process_bind_param(self, value, dialect):
            import json

            if value is None:
                return None
            if dialect.name == "postgresql":
                return value
            return json.dumps([str(v) if isinstance(v, uuid.UUID) else v for v in value])

        def process_result_value(self, value, dialect):
            import json

            if value is None:
                return None
            if dialect.name == "postgresql":
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if hasattr(item_type, "as_uuid") and getattr(item_type, "as_uuid", False):
                        return [uuid.UUID(v) for v in parsed]
                    return parsed
                except (json.JSONDecodeError, ValueError, TypeError):
                    return []
            return value

    return CompatArrayType()


def CompatJSONB():
    """JSONB that works in Postgres natively, falls back to text in SQLite."""

    class CompatJSONBType(TypeDecorator):
        impl = String(4096)
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == "postgresql":
                return dialect.type_descriptor(JSONB)
            return dialect.type_descriptor(String(4096))

        def process_bind_param(self, value, dialect):
            import json

            if value is None:
                return None
            if dialect.name == "postgresql":
                return value
            return json.dumps(value)

        def process_result_value(self, value, dialect):
            import json

            if value is None:
                return None
            if dialect.name == "postgresql":
                return value
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return {}
            return value

    return CompatJSONBType()
