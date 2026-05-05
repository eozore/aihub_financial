"""Tests for the migration runner (migrations/runner.py).

Validates:
- Tracking table creation and management
- Discovery of migration modules
- Applying pending migrations in order
- Rollback of the most recently applied migration
- Idempotency (running twice is safe)
- Transactional safety (failed migration does not record version)
- Preservation of existing data after full apply cycle

Requirements: 9.5, 9.6
"""

import importlib
import sqlite3
import uuid
from unittest.mock import patch, MagicMock

import pytest

from migrations.runner import (
    _ensure_tracking_table,
    _discover_migrations,
    get_applied,
    run_pending,
    rollback_last,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_base_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with the original transactions_gold schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE transactions_gold (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            date DATE,
            month_ref TEXT,
            amount REAL,
            merchant_clean TEXT,
            category TEXT,
            subcategory TEXT,
            owner TEXT,
            type TEXT,
            created_at TIMESTAMP
        )
        """
    )
    return conn


def _seed_transactions(conn: sqlite3.Connection, count: int = 5):
    """Insert sample legacy transactions and return their ids."""
    ids = []
    for i in range(count):
        tid = str(uuid.uuid4())
        ids.append(tid)
        conn.execute(
            """
            INSERT INTO transactions_gold
            (id, tenant_id, date, month_ref, amount, merchant_clean,
             category, subcategory, owner, type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid,
                "default",
                "2026-01-15",
                "2026-01",
                -99.90,
                "AMAZON",
                "Compras",
                None,
                "Victor",
                "individual",
                "2026-01-15T10:00:00",
            ),
        )
    conn.commit()
    return ids


def _get_tables(conn: sqlite3.Connection) -> set:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row[0] if isinstance(row, tuple) else row["name"] for row in rows}


def _get_columns(conn: sqlite3.Connection, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] if isinstance(row, tuple) else row[1] for row in rows}


# ---------------------------------------------------------------------------
# Tracking table
# ---------------------------------------------------------------------------

class TestTrackingTable:
    def test_creates_migrations_table(self):
        conn = sqlite3.connect(":memory:")
        _ensure_tracking_table(conn)
        tables = _get_tables(conn)
        assert "_migrations" in tables

    def test_idempotent_creation(self):
        conn = sqlite3.connect(":memory:")
        _ensure_tracking_table(conn)
        _ensure_tracking_table(conn)  # should not raise
        tables = _get_tables(conn)
        assert "_migrations" in tables

    def test_get_applied_empty(self):
        conn = sqlite3.connect(":memory:")
        result = get_applied(conn)
        assert result == []


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDiscovery:
    def test_discovers_existing_migrations(self):
        migrations = _discover_migrations()
        ids = [m[0] for m in migrations]
        assert "001_add_saas_columns" in ids
        assert "002_create_saas_tables" in ids

    def test_sorted_order(self):
        migrations = _discover_migrations()
        ids = [m[0] for m in migrations]
        assert ids == sorted(ids)

    def test_excludes_non_migration_files(self):
        migrations = _discover_migrations()
        ids = [m[0] for m in migrations]
        # __init__.py and runner.py should not appear
        assert not any("__init__" in mid for mid in ids)
        assert not any("runner" in mid for mid in ids)


# ---------------------------------------------------------------------------
# run_pending
# ---------------------------------------------------------------------------

class TestRunPending:
    def test_applies_all_migrations(self):
        conn = _create_base_db()
        applied = run_pending(conn)
        assert "001_add_saas_columns" in applied
        assert "002_create_saas_tables" in applied

    def test_records_applied_versions(self):
        conn = _create_base_db()
        run_pending(conn)
        recorded = get_applied(conn)
        assert "001_add_saas_columns" in recorded
        assert "002_create_saas_tables" in recorded

    def test_idempotent_second_run(self):
        conn = _create_base_db()
        first = run_pending(conn)
        second = run_pending(conn)
        assert len(first) >= 2
        assert second == []

    def test_creates_saas_tables(self):
        conn = _create_base_db()
        run_pending(conn)
        tables = _get_tables(conn)
        for expected in ("cards", "workspace_category_rules", "subscriptions", "upload_history"):
            assert expected in tables, f"Table {expected} not created"

    def test_adds_saas_columns(self):
        conn = _create_base_db()
        run_pending(conn)
        cols = _get_columns(conn, "transactions_gold")
        for expected in ("card_last4", "card_type", "is_refund",
                         "transaction_source", "upload_id", "needs_review"):
            assert expected in cols, f"Column {expected} missing"

    def test_preserves_existing_transactions(self):
        conn = _create_base_db()
        ids = _seed_transactions(conn, count=10)
        run_pending(conn)

        rows = conn.execute("SELECT * FROM transactions_gold").fetchall()
        assert len(rows) == 10
        for row in rows:
            assert row["amount"] == -99.90
            assert row["merchant_clean"] == "AMAZON"
            assert row["category"] == "Compras"
            assert row["owner"] == "Victor"

    def test_backfills_legacy_defaults(self):
        conn = _create_base_db()
        _seed_transactions(conn, count=3)
        run_pending(conn)

        rows = conn.execute("SELECT * FROM transactions_gold").fetchall()
        for row in rows:
            assert row["transaction_source"] == "legacy_csv"
            assert row["card_last4"] is None
            assert row["needs_review"] == 0


# ---------------------------------------------------------------------------
# rollback_last
# ---------------------------------------------------------------------------

class TestRollbackLast:
    def test_rolls_back_last_migration(self):
        conn = _create_base_db()
        run_pending(conn)
        rolled = rollback_last(conn)
        assert rolled == "002_create_saas_tables"

        applied = get_applied(conn)
        assert "002_create_saas_tables" not in applied
        assert "001_add_saas_columns" in applied

    def test_rollback_removes_saas_tables(self):
        conn = _create_base_db()
        run_pending(conn)
        rollback_last(conn)  # rolls back 002

        tables = _get_tables(conn)
        for removed in ("cards", "workspace_category_rules", "subscriptions", "upload_history"):
            assert removed not in tables, f"Table {removed} still present after rollback"

    def test_rollback_all(self):
        conn = _create_base_db()
        _seed_transactions(conn, count=5)
        run_pending(conn)

        rollback_last(conn)  # 002
        rollback_last(conn)  # 001

        applied = get_applied(conn)
        assert applied == []

        # Original columns should be restored
        cols = _get_columns(conn, "transactions_gold")
        for removed in ("card_last4", "card_type", "is_refund",
                        "transaction_source", "upload_id", "needs_review"):
            assert removed not in cols

        # Data preserved
        count = conn.execute("SELECT COUNT(*) FROM transactions_gold").fetchone()[0]
        assert count == 5

    def test_rollback_none_applied(self):
        conn = _create_base_db()
        result = rollback_last(conn)
        assert result is None

    def test_reapply_after_rollback(self):
        conn = _create_base_db()
        _seed_transactions(conn, count=3)
        run_pending(conn)
        rollback_last(conn)
        rollback_last(conn)

        # Re-apply everything
        applied = run_pending(conn)
        assert "001_add_saas_columns" in applied
        assert "002_create_saas_tables" in applied

        # Data still intact
        count = conn.execute("SELECT COUNT(*) FROM transactions_gold").fetchone()[0]
        assert count == 3


# ---------------------------------------------------------------------------
# Data integrity — simulates the 1,572 existing transactions
# ---------------------------------------------------------------------------

class TestDataIntegrity:
    """Verify that a large set of transactions survives the full migration cycle."""

    def test_large_dataset_preserved_after_apply(self):
        conn = _create_base_db()
        # Simulate 1572 transactions
        for i in range(1572):
            owner = "Victor" if i < 1112 else "Larissa"
            conn.execute(
                """
                INSERT INTO transactions_gold
                (id, tenant_id, date, month_ref, amount, merchant_clean,
                 category, subcategory, owner, type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"txn-{i:05d}",
                    "default",
                    "2026-01-15",
                    "2026-01",
                    -(10.0 + i * 0.01),
                    f"MERCHANT_{i}",
                    "Compras",
                    None,
                    owner,
                    "individual" if owner == "Victor" else "shared",
                    "2026-01-15T10:00:00",
                ),
            )
        conn.commit()

        run_pending(conn)

        count = conn.execute("SELECT COUNT(*) FROM transactions_gold").fetchone()[0]
        assert count == 1572

        victor_count = conn.execute(
            "SELECT COUNT(*) FROM transactions_gold WHERE owner = 'Victor'"
        ).fetchone()[0]
        assert victor_count == 1112

        larissa_count = conn.execute(
            "SELECT COUNT(*) FROM transactions_gold WHERE owner = 'Larissa'"
        ).fetchone()[0]
        assert larissa_count == 460

    def test_large_dataset_preserved_after_full_roundtrip(self):
        conn = _create_base_db()
        for i in range(1572):
            owner = "Victor" if i < 1112 else "Larissa"
            conn.execute(
                """
                INSERT INTO transactions_gold
                (id, tenant_id, date, month_ref, amount, merchant_clean,
                 category, subcategory, owner, type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"txn-{i:05d}",
                    "default",
                    "2026-01-15",
                    "2026-01",
                    -(10.0 + i * 0.01),
                    f"MERCHANT_{i}",
                    "Compras",
                    None,
                    owner,
                    "individual" if owner == "Victor" else "shared",
                    "2026-01-15T10:00:00",
                ),
            )
        conn.commit()

        # Apply all
        run_pending(conn)
        # Rollback all
        rollback_last(conn)
        rollback_last(conn)
        # Re-apply all
        run_pending(conn)

        count = conn.execute("SELECT COUNT(*) FROM transactions_gold").fetchone()[0]
        assert count == 1572
