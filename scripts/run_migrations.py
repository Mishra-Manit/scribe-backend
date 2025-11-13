#!/usr/bin/env python3
"""
Database migration helper script.
Provides convenient commands for managing Alembic migrations.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic import command


def get_alembic_config() -> Config:
    """Get Alembic configuration object."""
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    return alembic_cfg


def upgrade(revision: str = "head"):
    """
    Upgrade database to a specific revision.

    Args:
        revision: Target revision (default: 'head' for latest)
    """
    print(f"Upgrading database to revision: {revision}")
    alembic_cfg = get_alembic_config()
    command.upgrade(alembic_cfg, revision)
    print("✓ Database upgraded successfully")


def downgrade(revision: str = "-1"):
    """
    Downgrade database to a specific revision.

    Args:
        revision: Target revision (default: '-1' for one step back)
    """
    print(f"Downgrading database to revision: {revision}")
    alembic_cfg = get_alembic_config()
    command.downgrade(alembic_cfg, revision)
    print("✓ Database downgraded successfully")


def current():
    """Show current database revision."""
    print("Current database revision:")
    alembic_cfg = get_alembic_config()
    command.current(alembic_cfg)


def history():
    """Show migration history."""
    print("Migration history:")
    alembic_cfg = get_alembic_config()
    command.history(alembic_cfg)


def revision(message: str, autogenerate: bool = True):
    """
    Create a new migration revision.

    Args:
        message: Description of the migration
        autogenerate: Whether to use autogenerate (default: True)
    """
    print(f"Creating new migration: {message}")
    alembic_cfg = get_alembic_config()
    command.revision(
        alembic_cfg,
        message=message,
        autogenerate=autogenerate
    )
    print("✓ Migration created successfully")


def main():
    """Main CLI entrypoint."""
    if len(sys.argv) < 2:
        print("Database Migration Helper")
        print("\nUsage:")
        print("  python scripts/run_migrations.py upgrade        - Upgrade to latest")
        print("  python scripts/run_migrations.py downgrade      - Downgrade one step")
        print("  python scripts/run_migrations.py current        - Show current revision")
        print("  python scripts/run_migrations.py history        - Show migration history")
        print("  python scripts/run_migrations.py create <msg>   - Create new migration")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    try:
        if cmd == "upgrade":
            revision_arg = sys.argv[2] if len(sys.argv) > 2 else "head"
            upgrade(revision_arg)
        elif cmd == "downgrade":
            revision_arg = sys.argv[2] if len(sys.argv) > 2 else "-1"
            downgrade(revision_arg)
        elif cmd == "current":
            current()
        elif cmd == "history":
            history()
        elif cmd == "create":
            if len(sys.argv) < 3:
                print("Error: Migration message required")
                print("Usage: python scripts/run_migrations.py create <message>")
                sys.exit(1)
            message = " ".join(sys.argv[2:])
            revision(message, autogenerate=True)
        else:
            print(f"Unknown command: {cmd}")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
