"""
Alembic migration helper.

Provides run_migrations() to apply all pending migrations at startup.
"""
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def get_alembic_config() -> Config:
    """Load Alembic configuration."""
    # Try to locate alembic.ini relative to project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    alembic_ini = project_root / "alembic.ini"

    if not alembic_ini.exists():
        # Fallback: create tables directly if alembic.ini missing
        raise FileNotFoundError(f"alembic.ini not found at {alembic_ini}")

    alembic_cfg = Config(str(alembic_ini))

    # Set script location relative to project root
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))

    return alembic_cfg


def run_migrations() -> None:
    """
    Apply all pending Alembic migrations.

    Fails loudly if alembic.ini is not found or migrations fail.
    No fallback to create_all — production systems must use migrations.
    """
    from backend.app.core.config import get_settings

    settings = get_settings()

    alembic_cfg = get_alembic_config()
    # Set DB URL from settings
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")
    print("[migrations] Alembic upgrade complete.")


def stamp_head() -> None:
    """Stamp the database with the current head revision (for fresh DBs)."""
    from backend.app.core.config import get_settings

    settings = get_settings()
    try:
        alembic_cfg = get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.stamp(alembic_cfg, "head")
        print("[migrations] Stamped head revision.")
    except Exception as exc:
        print(f"[migrations] Stamp failed: {exc}", file=sys.stderr)
