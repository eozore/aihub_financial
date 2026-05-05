"""Tests for migration 002_create_saas_tables."""
import importlib
import sqlite3
import uuid
import pytest

_mod = importlib.import_module("migrations.002_create_saas_tables")
apply = _mod.apply
rollback = _mod.rollback

_TABLES = ("cards", "workspace_category_rules", "subscriptions", "upload_history")


def _create_test_db():
    """Create an in-memory SQLite DB (empty — no pre-existing tables needed)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table_name):
    """Return True if the table exists in the database."""
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row[0] > 0


def _get_columns(conn, table):
    """Return set of column names for a table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


class TestApply:
    """Tests for the apply() function."""

    def test_creates_all_tables(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        for table in _TABLES:
            assert _table_exists(conn, table), f"Table {table} not created"

    def test_cards_columns(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        cols = _get_columns(conn, "cards")
        expected = {
            "id", "workspace_id", "owner", "last4", "label",
            "card_type", "bank", "is_active", "created_at", "updated_at",
        }
        assert cols == expected

    def test_workspace_category_rules_columns(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        cols = _get_columns(conn, "workspace_category_rules")
        expected = {
            "id", "workspace_id", "merchant_pattern", "category",
            "created_by", "created_at",
        }
        assert cols == expected

    def test_subscriptions_columns(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        cols = _get_columns(conn, "subscriptions")
        expected = {
            "id", "workspace_id", "mp_preapproval_id", "plan_type",
            "status", "trial_ends_at", "current_period_start",
            "current_period_end", "created_at", "updated_at",
        }
        assert cols == expected

    def test_upload_history_columns(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        cols = _get_columns(conn, "upload_history")
        expected = {
            "id", "workspace_id", "user_id", "filename", "file_hash",
            "file_size_bytes", "statement_type", "bank", "period_start",
            "period_end", "transactions_count", "status", "error_message",
            "created_at",
        }
        assert cols == expected

    def test_idempotent(self):
        """Running apply() twice should not fail."""
        conn = _create_test_db()
        apply(conn)
        conn.commit()
        # Second apply should be a no-op
        apply(conn)
        conn.commit()

        for table in _TABLES:
            assert _table_exists(conn, table)


class TestCardsConstraints:
    """Tests for CHECK and UNIQUE constraints on the cards table."""

    def test_valid_card_insert(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("c1", "ws1", "Alice", "1234", "individual"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cards WHERE id='c1'").fetchone()
        assert row["last4"] == "1234"
        assert row["card_type"] == "individual"

    def test_last4_must_be_4_digits(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
                "VALUES (?, ?, ?, ?, ?)",
                ("c2", "ws1", "Alice", "123", "individual"),
            )

    def test_last4_rejects_non_numeric(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
                "VALUES (?, ?, ?, ?, ?)",
                ("c3", "ws1", "Alice", "12ab", "individual"),
            )

    def test_card_type_check(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
                "VALUES (?, ?, ?, ?, ?)",
                ("c4", "ws1", "Alice", "5678", "corporate"),
            )

    def test_unique_workspace_last4(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("c5", "ws1", "Alice", "9999", "individual"),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
                "VALUES (?, ?, ?, ?, ?)",
                ("c6", "ws1", "Bob", "9999", "shared"),
            )

    def test_same_last4_different_workspace_ok(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("c7", "ws1", "Alice", "1111", "individual"),
        )
        conn.execute(
            "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("c8", "ws2", "Bob", "1111", "shared"),
        )
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        assert count == 2


class TestSubscriptionsConstraints:
    """Tests for CHECK constraints on the subscriptions table."""

    def test_valid_subscription(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO subscriptions (id, workspace_id, plan_type, status) "
            "VALUES (?, ?, ?, ?)",
            ("s1", "ws1", "pro", "active"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM subscriptions WHERE id='s1'").fetchone()
        assert row["plan_type"] == "pro"
        assert row["status"] == "active"

    def test_plan_type_check(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO subscriptions (id, workspace_id, plan_type, status) "
                "VALUES (?, ?, ?, ?)",
                ("s2", "ws1", "enterprise", "active"),
            )

    def test_status_check(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO subscriptions (id, workspace_id, plan_type, status) "
                "VALUES (?, ?, ?, ?)",
                ("s3", "ws1", "free", "expired"),
            )

    def test_defaults(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO subscriptions (id, workspace_id) VALUES (?, ?)",
            ("s4", "ws1"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM subscriptions WHERE id='s4'").fetchone()
        assert row["plan_type"] == "free"
        assert row["status"] == "active"


class TestUploadHistoryConstraints:
    """Tests for CHECK constraints on the upload_history table."""

    def test_valid_upload(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO upload_history "
            "(id, workspace_id, user_id, filename, file_hash, statement_type, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u1", "ws1", "user1", "fatura.pdf", "abc123", "credit_card", "completed"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM upload_history WHERE id='u1'").fetchone()
        assert row["statement_type"] == "credit_card"
        assert row["status"] == "completed"

    def test_statement_type_check(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO upload_history "
                "(id, workspace_id, user_id, filename, file_hash, statement_type, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("u2", "ws1", "user1", "f.pdf", "h", "savings", "completed"),
            )

    def test_status_check(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO upload_history "
                "(id, workspace_id, user_id, filename, file_hash, statement_type, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("u3", "ws1", "user1", "f.pdf", "h", "credit_card", "deleted"),
            )

    def test_statement_type_nullable(self):
        """statement_type can be NULL (no CHECK violation for NULL)."""
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO upload_history "
            "(id, workspace_id, user_id, filename, file_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("u4", "ws1", "user1", "f.csv", "h2", "processing"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM upload_history WHERE id='u4'").fetchone()
        assert row["statement_type"] is None


class TestWorkspaceCategoryRulesConstraints:
    """Tests for UNIQUE constraint on workspace_category_rules."""

    def test_valid_rule(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO workspace_category_rules "
            "(id, workspace_id, merchant_pattern, category) "
            "VALUES (?, ?, ?, ?)",
            ("r1", "ws1", "AMAZON", "Compras"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM workspace_category_rules WHERE id='r1'"
        ).fetchone()
        assert row["merchant_pattern"] == "AMAZON"
        assert row["category"] == "Compras"

    def test_unique_workspace_merchant_pattern(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO workspace_category_rules "
            "(id, workspace_id, merchant_pattern, category) "
            "VALUES (?, ?, ?, ?)",
            ("r2", "ws1", "NETFLIX", "Streaming"),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO workspace_category_rules "
                "(id, workspace_id, merchant_pattern, category) "
                "VALUES (?, ?, ?, ?)",
                ("r3", "ws1", "NETFLIX", "Lazer"),
            )

    def test_same_pattern_different_workspace_ok(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO workspace_category_rules "
            "(id, workspace_id, merchant_pattern, category) "
            "VALUES (?, ?, ?, ?)",
            ("r4", "ws1", "UBER", "Transporte"),
        )
        conn.execute(
            "INSERT INTO workspace_category_rules "
            "(id, workspace_id, merchant_pattern, category) "
            "VALUES (?, ?, ?, ?)",
            ("r5", "ws2", "UBER", "Transporte"),
        )
        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM workspace_category_rules"
        ).fetchone()[0]
        assert count == 2


class TestRollback:
    """Tests for the rollback() function."""

    def test_drops_all_tables(self):
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        rollback(conn)
        conn.commit()

        for table in _TABLES:
            assert not _table_exists(conn, table), (
                f"Table {table} still exists after rollback"
            )

    def test_rollback_idempotent(self):
        """Rollback on non-existent tables should not fail."""
        conn = _create_test_db()
        # No apply — tables don't exist
        rollback(conn)
        conn.commit()

        for table in _TABLES:
            assert not _table_exists(conn, table)

    def test_rollback_preserves_other_tables(self):
        """Rollback should not affect tables outside the migration."""
        conn = _create_test_db()
        conn.execute(
            "CREATE TABLE transactions_gold (id TEXT PRIMARY KEY, amount REAL)"
        )
        conn.commit()

        apply(conn)
        conn.commit()
        rollback(conn)
        conn.commit()

        assert _table_exists(conn, "transactions_gold")
        for table in _TABLES:
            assert not _table_exists(conn, table)


class TestApplyThenRollbackRoundTrip:
    """Verify full apply → rollback cycle."""

    def test_round_trip(self):
        conn = _create_test_db()

        apply(conn)
        conn.commit()
        for table in _TABLES:
            assert _table_exists(conn, table)

        rollback(conn)
        conn.commit()
        for table in _TABLES:
            assert not _table_exists(conn, table)

    def test_round_trip_data_lost_on_rollback(self):
        """Data in the new tables is lost after rollback (expected)."""
        conn = _create_test_db()
        apply(conn)
        conn.commit()

        conn.execute(
            "INSERT INTO cards (id, workspace_id, owner, last4, card_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("c1", "ws1", "Alice", "1234", "individual"),
        )
        conn.commit()

        rollback(conn)
        conn.commit()

        assert not _table_exists(conn, "cards")
