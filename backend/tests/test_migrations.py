"""Unit contracts for startup migration orchestration."""

from types import SimpleNamespace

from alembic.config import Config

from backend.app.db import migrate


def test_get_alembic_config_points_to_repository() -> None:
    config = migrate.get_alembic_config()

    config_file_name = config.config_file_name
    script_location = config.get_main_option("script_location")
    assert config_file_name is not None
    assert script_location is not None
    assert config_file_name.endswith("alembic.ini")
    assert script_location.endswith("alembic")


def test_run_migrations_uses_runtime_database_url(monkeypatch) -> None:
    config = Config()
    calls = []
    monkeypatch.setattr(migrate, "get_alembic_config", lambda: config)
    monkeypatch.setattr(
        migrate.command, "upgrade", lambda cfg, revision: calls.append((cfg, revision))
    )
    monkeypatch.setattr(
        "backend.app.core.config.get_settings",
        lambda: SimpleNamespace(database_url="postgresql://runtime/db"),
    )

    migrate.run_migrations()

    assert config.get_main_option("sqlalchemy.url") == "postgresql://runtime/db"
    assert calls == [(config, "head")]


def test_stamp_head_reports_errors_without_crashing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "backend.app.core.config.get_settings",
        lambda: SimpleNamespace(database_url="postgresql://runtime/db"),
    )
    monkeypatch.setattr(
        migrate,
        "get_alembic_config",
        lambda: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )

    migrate.stamp_head()

    assert "Stamp failed: missing" in capsys.readouterr().err
