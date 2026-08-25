"""Dialect contracts for the PostgreSQL/SQLite compatibility types."""

import uuid

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.compat import CompatARRAY, CompatBigInteger, CompatJSONB, CompatUUID


def test_compat_big_integer_preserves_sqlite_autoincrement_affinity() -> None:
    compat = CompatBigInteger()

    assert compat.compile(dialect=postgresql.dialect()) == "BIGINT"
    assert compat.compile(dialect=sqlite.dialect()) == "INTEGER"


def test_compat_uuid_round_trips_by_dialect() -> None:
    value = uuid.uuid4()
    compat = CompatUUID()
    sqlite_dialect = sqlite.dialect()
    postgres_dialect = postgresql.dialect()

    assert compat.load_dialect_impl(sqlite_dialect).length == 36
    assert compat.load_dialect_impl(postgres_dialect).as_uuid is True
    assert compat.process_bind_param(value, sqlite_dialect) == str(value)
    assert compat.process_bind_param(str(value), postgres_dialect) == value
    assert compat.process_bind_param(value, postgres_dialect) == value
    assert compat.process_bind_param(None, sqlite_dialect) is None
    assert compat.process_result_value(str(value), sqlite_dialect) == value
    assert compat.process_result_value(value, sqlite_dialect) == value
    assert compat.process_result_value("not-a-uuid", sqlite_dialect) == "not-a-uuid"
    assert compat.process_result_value(value, postgres_dialect) == value
    assert compat.process_result_value(None, sqlite_dialect) is None


def test_compat_array_round_trips_json_and_native_values() -> None:
    value = uuid.uuid4()
    compat = CompatARRAY(UUID(as_uuid=True))
    sqlite_dialect = sqlite.dialect()
    postgres_dialect = postgresql.dialect()

    assert compat.load_dialect_impl(postgres_dialect).item_type.as_uuid is True
    assert compat.process_bind_param([value], sqlite_dialect) == f'["{value}"]'
    assert compat.process_bind_param([value], postgres_dialect) == [value]
    assert compat.process_bind_param(None, sqlite_dialect) is None
    assert compat.process_result_value(f'["{value}"]', sqlite_dialect) == [value]
    assert compat.process_result_value("invalid", sqlite_dialect) == []
    assert compat.process_result_value([value], sqlite_dialect) == [value]
    assert compat.process_result_value([value], postgres_dialect) == [value]
    assert compat.process_result_value(None, sqlite_dialect) is None


def test_compat_jsonb_round_trips_json_and_native_values() -> None:
    payload = {"trace": "abc", "attempt": 2}
    compat = CompatJSONB()
    sqlite_dialect = sqlite.dialect()
    postgres_dialect = postgresql.dialect()

    assert compat.load_dialect_impl(postgres_dialect).__class__.__name__ == "_PGJSONB"
    assert compat.process_bind_param(payload, sqlite_dialect) == '{"trace": "abc", "attempt": 2}'
    assert compat.process_bind_param(payload, postgres_dialect) == payload
    assert compat.process_bind_param(None, sqlite_dialect) is None
    assert compat.process_result_value('{"trace": "abc"}', sqlite_dialect) == {"trace": "abc"}
    assert compat.process_result_value("invalid", sqlite_dialect) == {}
    assert compat.process_result_value(payload, sqlite_dialect) == payload
    assert compat.process_result_value(payload, postgres_dialect) == payload
    assert compat.process_result_value(None, sqlite_dialect) is None
