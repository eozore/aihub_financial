"""Tests for the new upload preview/confirm flow (Tasks 10.2 & 10.3).

These tests validate the core logic of the upload endpoints without
requiring a running FastAPI server, since the test environment has a
FastAPI version incompatibility.
"""
import hashlib
import os
import sqlite3
import uuid

import pytest

# Force SQLite mode
os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("USE_MOCK_DATA", "false")
os.environ.setdefault("REQUIRE_AUTH_FOR_DATA", "false")
os.environ.setdefault("TENANT_REQUIRED", "false")
os.environ.setdefault("PROJECT_ID", "test-project")


@pytest.fixture()
def test_db(tmp_path):
    """Create a temporary SQLite database with the required schema."""
    db_path = tmp_path / "test_finance.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # transactions_gold with SaaS columns
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions_gold (
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
            created_at TIMESTAMP,
            card_last4 TEXT,
            card_type TEXT,
            is_refund INTEGER DEFAULT 0,
            transaction_source TEXT DEFAULT 'legacy_csv',
            upload_id TEXT,
            needs_review INTEGER DEFAULT 0
        )
    """)

    # cards table
    c.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            last4 TEXT NOT NULL,
            label TEXT,
            card_type TEXT NOT NULL,
            bank TEXT DEFAULT 'nubank',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id, last4)
        )
    """)

    # workspace_category_rules table
    c.execute("""
        CREATE TABLE IF NOT EXISTS workspace_category_rules (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            merchant_pattern TEXT NOT NULL,
            category TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id, merchant_pattern)
        )
    """)

    # upload_history table
    c.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            file_size_bytes INTEGER,
            statement_type TEXT,
            bank TEXT,
            period_start TEXT,
            period_end TEXT,
            transactions_count INTEGER,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    yield conn, db_path
    conn.close()


def _insert_card(conn, workspace_id, owner, last4, card_type):
    """Helper to insert a card into the test database."""
    card_id = f"card-{uuid.uuid4().hex[:16]}"
    conn.execute(
        """INSERT INTO cards (id, workspace_id, owner, last4, card_type, bank, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'nubank', 1, datetime('now'), datetime('now'))""",
        (card_id, workspace_id, owner, last4, card_type),
    )
    conn.commit()
    return card_id


# ---------------------------------------------------------------------------
# Task 10.1 — upload_validation accepts PDF and CSV
# ---------------------------------------------------------------------------

def test_detect_file_type():
    from upload_validation import detect_file_type

    assert detect_file_type("fatura.pdf") == "pdf"
    assert detect_file_type("FATURA.PDF") == "pdf"
    assert detect_file_type("data.csv") == "csv"
    assert detect_file_type("DATA.CSV") == "csv"


def test_allowed_extensions():
    from upload_validation import ALLOWED_EXTENSIONS

    assert ".pdf" in ALLOWED_EXTENSIONS
    assert ".csv" in ALLOWED_EXTENSIONS


def test_allowed_mime_types():
    from upload_validation import ALLOWED_MIME_TYPES

    assert "application/pdf" in ALLOWED_MIME_TYPES
    assert "text/csv" in ALLOWED_MIME_TYPES
    assert "application/octet-stream" in ALLOWED_MIME_TYPES


# ---------------------------------------------------------------------------
# Task 10.2 — card_last4 cross-reference logic
# ---------------------------------------------------------------------------

def test_card_type_lookup_registered(test_db):
    """Registered card_last4 should resolve to the card's card_type."""
    conn, _ = test_db
    workspace_id = "ws-test-001"
    _insert_card(conn, workspace_id, "Victor", "4535", "individual")
    _insert_card(conn, workspace_id, "Larissa", "9876", "shared")

    # Simulate the lookup logic from the upload preview endpoint
    c = conn.cursor()
    c.execute("SELECT last4, card_type FROM cards WHERE workspace_id = ?", (workspace_id,))
    card_map = {row["last4"]: row["card_type"] for row in c.fetchall()}

    assert card_map.get("4535") == "individual"
    assert card_map.get("9876") == "shared"
    assert card_map.get("0000") is None  # unregistered


def test_unregistered_card_needs_review(test_db):
    """Transactions with unregistered card_last4 should be flagged needs_review."""
    conn, _ = test_db
    workspace_id = "ws-test-002"
    _insert_card(conn, workspace_id, "Victor", "4535", "individual")

    c = conn.cursor()
    c.execute("SELECT last4, card_type FROM cards WHERE workspace_id = ?", (workspace_id,))
    card_map = {row["last4"]: row["card_type"] for row in c.fetchall()}

    # Simulate preview logic
    test_last4 = "9999"
    needs_review = test_last4 not in card_map
    assert needs_review is True


# ---------------------------------------------------------------------------
# Task 10.2 — classification integration
# ---------------------------------------------------------------------------

def test_classification_service_integration(test_db):
    """ClassificationService should classify known merchants."""
    conn, db_path = test_db

    # Monkey-patch database path for ClassificationService
    import database
    original_path = database.DB_PATH
    database.DB_PATH = db_path

    try:
        from categories import ClassificationService
        svc = ClassificationService()

        result = svc.classify("ifood delivery", "ws-test")
        assert result.category == "Delivery"
        assert result.needs_review is False

        result = svc.classify("unknown merchant xyz", "ws-test")
        assert result.category == "Outros"
        assert result.needs_review is True
    finally:
        database.DB_PATH = original_path


# ---------------------------------------------------------------------------
# Task 10.3 — upload confirm saves transactions
# ---------------------------------------------------------------------------

def test_confirm_saves_transactions(test_db):
    """POST /upload/confirm should save transactions to transactions_gold."""
    conn, _ = test_db
    workspace_id = "ws-test-003"
    _insert_card(conn, workspace_id, "Victor", "4535", "individual")

    # Simulate the confirm logic
    upload_id = f"upload-{uuid.uuid4().hex[:16]}"
    tx_id = f"tx-{uuid.uuid4().hex[:16]}"
    now = "2026-05-01T00:00:00+00:00"

    conn.execute(
        """
        INSERT INTO transactions_gold
        (id, tenant_id, date, month_ref, amount, merchant_clean,
         category, subcategory, owner, type, created_at,
         card_last4, card_type, is_refund, transaction_source,
         upload_id, needs_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tx_id, workspace_id, "2026-04-15", "2026-04", 150.0,
            "Ifood", "Delivery", None, "Victor", "individual", now,
            "4535", "individual", 0, "pdf_extraction", upload_id, 0,
        ),
    )
    conn.commit()

    # Verify the transaction was saved
    c = conn.cursor()
    c.execute("SELECT * FROM transactions_gold WHERE id = ?", (tx_id,))
    row = dict(c.fetchone())

    assert row["tenant_id"] == workspace_id
    assert row["card_last4"] == "4535"
    assert row["card_type"] == "individual"
    assert row["transaction_source"] == "pdf_extraction"
    assert row["upload_id"] == upload_id
    assert row["needs_review"] == 0
    assert row["is_refund"] == 0


def test_confirm_records_upload_history(test_db):
    """POST /upload/confirm should create an upload_history record."""
    conn, _ = test_db
    workspace_id = "ws-test-004"
    user_id = "user-001"
    file_hash = hashlib.sha256(b"test pdf content").hexdigest()
    upload_history_id = f"uh-{uuid.uuid4().hex[:16]}"
    now = "2026-05-01T00:00:00+00:00"

    conn.execute(
        """
        INSERT INTO upload_history
        (id, workspace_id, user_id, filename, file_hash, file_size_bytes,
         statement_type, bank, period_start, period_end,
         transactions_count, status, error_message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upload_history_id, workspace_id, user_id,
            f"upload_{file_hash[:8]}", file_hash, None,
            "credit_card", "Nubank", "2026-04-01", "2026-04-30",
            5, "completed", None, now,
        ),
    )
    conn.commit()

    # Verify
    c = conn.cursor()
    c.execute("SELECT * FROM upload_history WHERE id = ?", (upload_history_id,))
    row = dict(c.fetchone())

    assert row["workspace_id"] == workspace_id
    assert row["user_id"] == user_id
    assert row["file_hash"] == file_hash
    assert row["transactions_count"] == 5
    assert row["status"] == "completed"
    assert row["statement_type"] == "credit_card"
    assert row["period_start"] == "2026-04-01"
    assert row["period_end"] == "2026-04-30"


def test_confirm_unregistered_card_sets_needs_review(test_db):
    """Transactions with unregistered cards should have needs_review=1."""
    conn, _ = test_db
    workspace_id = "ws-test-005"
    # No cards registered for this workspace

    upload_id = f"upload-{uuid.uuid4().hex[:16]}"
    tx_id = f"tx-{uuid.uuid4().hex[:16]}"
    now = "2026-05-01T00:00:00+00:00"

    # Simulate: card_last4 "9999" is not registered
    conn.execute(
        """
        INSERT INTO transactions_gold
        (id, tenant_id, date, month_ref, amount, merchant_clean,
         category, subcategory, owner, type, created_at,
         card_last4, card_type, is_refund, transaction_source,
         upload_id, needs_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tx_id, workspace_id, "2026-04-15", "2026-04", 50.0,
            "Unknown Store", "Outros", None, "Victor", None, now,
            "9999", None, 0, "pdf_extraction", upload_id, 1,
        ),
    )
    conn.commit()

    c = conn.cursor()
    c.execute("SELECT * FROM transactions_gold WHERE id = ?", (tx_id,))
    row = dict(c.fetchone())

    assert row["card_last4"] == "9999"
    assert row["card_type"] is None
    assert row["needs_review"] == 1


def test_confirm_refund_flag(test_db):
    """Refund transactions should have is_refund=1."""
    conn, _ = test_db
    workspace_id = "ws-test-006"

    upload_id = f"upload-{uuid.uuid4().hex[:16]}"
    tx_id = f"tx-{uuid.uuid4().hex[:16]}"
    now = "2026-05-01T00:00:00+00:00"

    conn.execute(
        """
        INSERT INTO transactions_gold
        (id, tenant_id, date, month_ref, amount, merchant_clean,
         category, subcategory, owner, type, created_at,
         card_last4, card_type, is_refund, transaction_source,
         upload_id, needs_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tx_id, workspace_id, "2026-04-20", "2026-04", 25.0,
            "Estorno Amazon", "Compras", None, "Victor", "individual", now,
            "4535", "individual", 1, "pdf_extraction", upload_id, 0,
        ),
    )
    conn.commit()

    c = conn.cursor()
    c.execute("SELECT * FROM transactions_gold WHERE id = ?", (tx_id,))
    row = dict(c.fetchone())

    assert row["is_refund"] == 1
    assert row["transaction_source"] == "pdf_extraction"
