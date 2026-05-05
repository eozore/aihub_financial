"""Tests for migration 001_add_saas_columns."""
import importlib
import sqlite3
import uuid
import pytest

_mod = importlib.import_module("migrations.001_add_saas_columns")
apply = _mod.apply
rollback = _mod.rollback


def _create_test_db():
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


def _seed_transactions(conn, count=5):
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


def _get_columns(conn, table="transactions_gold"):
    """Return set of column names for a table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


class TestApply:
    """Tests for the apply() function."""

    def test_adds_all_new_columns(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        cols = _get_columns(conn)
        for expected in ("card_last4", "card_type", "is_refund",
                         "transaction_source", "upload_id", "needs_review"):
            assert expected in cols, f"Column {expected} missing after apply()"

    def test_backfills_legacy_rows(self):
        conn = _create_test_db()
        ids = _seed_transactions(conn, count=3)
        apply(conn)
        conn.commit()

        rows = conn.execute("SELECT * FROM transactions_gold").fetchall()
        assert len(rows) == 3

        for row in rows:
            assert row["transaction_source"] == "legacy_csv"
            assert row["card_last4"] is None
            assert row["needs_review"] == 0
            assert row["is_refund"] == 0

    def test_preserves_existing_data(self):
        conn = _create_test_db()
        ids = _seed_transactions(conn, count=2)
        apply(conn)
        conn.commit()

        rows = conn.execute(
            "SELECT id, amount, merchant_clean, category, owner FROM transactions_gold"
        ).fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row["amount"] == -99.90
            assert row["merchant_clean"] == "AMAZON"
            assert row["category"] == "Compras"
            assert row["owner"] == "Victor"

    def test_idempotent(self):
        """Running apply() twice should not fail or duplicate columns."""
        conn = _create_test_db()
        _seed_transactions(conn, count=2)
        apply(conn)
        conn.commit()
        # Second apply should be a no-op
        apply(conn)
        conn.commit()

        cols = _get_columns(conn)
        assert "card_last4" in cols
        rows = conn.execute("SELECT COUNT(*) FROM transactions_gold").fetchone()
        assert rows[0] == 2


class TestRollback:
    """Tests for the rollback() function."""

    def test_removes_new_columns(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        rollback(conn)
        conn.commit()

        cols = _get_columns(conn)
        for removed in ("card_last4", "card_type", "is_refund",
                        "transaction_source", "upload_id", "needs_review"):
            assert removed not in cols, f"Column {removed} still present after rollback()"

    def test_preserves_data_after_rollback(self):
        conn = _create_test_db()
        ids = _seed_transactions(conn, count=4)
        apply(conn)
        conn.commit()

        rollback(conn)
        conn.commit()

        rows = conn.execute("SELECT * FROM transactions_gold").fetchall()
        assert len(rows) == 4
        for row in rows:
            assert row["amount"] == -99.90
            assert row["merchant_clean"] == "AMAZON"
            assert row["owner"] == "Victor"

    def test_original_columns_restored(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        rollback(conn)
        conn.commit()

        expected = {
            "id", "tenant_id", "date", "month_ref", "amount",
            "merchant_clean", "category", "subcategory", "owner",
            "type", "created_at",
        }
        cols = _get_columns(conn)
        assert cols == expected


class TestApplyThenRollbackRoundTrip:
    """Verify full apply → rollback cycle preserves data integrity."""

    def test_round_trip_preserves_row_count(self):
        conn = _create_test_db()
        ids = _seed_transactions(conn, count=10)

        apply(conn)
        conn.commit()
        count_after_apply = conn.execute(
            "SELECT COUNT(*) FROM transactions_gold"
        ).fetchone()[0]
        assert count_after_apply == 10

        rollback(conn)
        conn.commit()
        count_after_rollback = conn.execute(
            "SELECT COUNT(*) FROM transactions_gold"
        ).fetchone()[0]
        assert count_after_rollback == 10
