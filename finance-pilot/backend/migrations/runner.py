"""
Migration runner for Finance Pilot.

Discovers migration modules in the ``migrations/`` directory (files matching
``NNN_*.py``), executes pending ones in order, and records each applied
version in a ``_migrations`` tracking table.

All operations are transactional — if a migration fails mid-way the
transaction is rolled back and the version is **not** recorded.

Public API
----------
- ``run_pending(conn)`` — apply all unapplied migrations in order.
- ``rollback_last(conn)`` — roll back the most recently applied migration.
- ``get_applied(conn)`` — return list of applied migration ids.

Requirements: 9.5, 9.6
"""

import importlib
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("finance-pilot.migrations")

# Directory that contains the numbered migration scripts.
_MIGRATIONS_DIR = Path(__file__).resolve().parent

# Pattern: ``001_add_saas_columns.py`` → group(1) = "001", group(2) = "add_saas_columns"
_MIGRATION_RE = re.compile(r"^(\d{3})_(.+)\.py$")


# ---------------------------------------------------------------------------
# Tracking table helpers
# ---------------------------------------------------------------------------

def _ensure_tracking_table(conn: sqlite3.Connection) -> None:
    """Create the ``_migrations`` table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at   TEXT NOT NULL
        )
        """
    )


def get_applied(conn: sqlite3.Connection) -> List[str]:
    """Return an ordered list of migration ids that have been applied."""
    _ensure_tracking_table(conn)
    rows = conn.execute(
        "SELECT migration_id FROM _migrations ORDER BY migration_id ASC"
    ).fetchall()
    return [row[0] if isinstance(row, tuple) else row["migration_id"] for row in rows]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _discover_migrations() -> List[Tuple[str, str]]:
    """Return ``[(migration_id, module_name), ...]`` sorted by id.

    ``migration_id`` is the filename stem, e.g. ``001_add_saas_columns``.
    ``module_name`` is the dotted import path, e.g.
    ``migrations.001_add_saas_columns``.
    """
    results: List[Tuple[str, str]] = []
    for path in sorted(_MIGRATIONS_DIR.iterdir()):
        match = _MIGRATION_RE.match(path.name)
        if match:
            migration_id = path.stem  # e.g. "001_add_saas_columns"
            module_name = f"migrations.{migration_id}"
            results.append((migration_id, module_name))
    return results


def _load_module(module_name: str):
    """Import (or re-import) a migration module and return it."""
    return importlib.import_module(module_name)


# ---------------------------------------------------------------------------
# Apply / Rollback
# ---------------------------------------------------------------------------

def run_pending(conn: sqlite3.Connection) -> List[str]:
    """Apply all pending migrations in order.

    Returns the list of migration ids that were applied during this call.
    """
    _ensure_tracking_table(conn)
    applied = set(get_applied(conn))
    all_migrations = _discover_migrations()

    newly_applied: List[str] = []
    for migration_id, module_name in all_migrations:
        if migration_id in applied:
            logger.debug("Migration %s already applied — skipping", migration_id)
            continue

        module = _load_module(module_name)
        apply_fn = getattr(module, "apply", None)
        if apply_fn is None:
            logger.warning("Migration %s has no apply() function — skipping", migration_id)
            continue

        logger.info("Applying migration %s …", migration_id)
        try:
            apply_fn(conn)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO _migrations (migration_id, applied_at) VALUES (?, ?)",
                (migration_id, now),
            )
            conn.commit()
            logger.info("Migration %s applied successfully", migration_id)
            newly_applied.append(migration_id)
        except Exception:
            conn.rollback()
            logger.exception("Migration %s failed — rolled back", migration_id)
            raise

    if not newly_applied:
        logger.info("No pending migrations")
    return newly_applied


def rollback_last(conn: sqlite3.Connection) -> Optional[str]:
    """Roll back the most recently applied migration.

    Returns the migration id that was rolled back, or ``None`` if there
    are no applied migrations.
    """
    _ensure_tracking_table(conn)
    applied = get_applied(conn)
    if not applied:
        logger.info("No migrations to roll back")
        return None

    last_id = applied[-1]

    # Find the corresponding module.
    all_migrations = dict(_discover_migrations())
    module_name = all_migrations.get(last_id)
    if module_name is None:
        raise RuntimeError(
            f"Cannot rollback migration {last_id}: module not found on disk"
        )

    module = _load_module(module_name)
    rollback_fn = getattr(module, "rollback", None)
    if rollback_fn is None:
        raise RuntimeError(
            f"Cannot rollback migration {last_id}: no rollback() function"
        )

    logger.info("Rolling back migration %s …", last_id)
    try:
        rollback_fn(conn)
        conn.execute("DELETE FROM _migrations WHERE migration_id = ?", (last_id,))
        conn.commit()
        logger.info("Migration %s rolled back successfully", last_id)
        return last_id
    except Exception:
        conn.rollback()
        logger.exception("Rollback of %s failed — rolled back transaction", last_id)
        raise
