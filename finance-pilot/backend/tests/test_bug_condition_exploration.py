"""Bug Condition Exploration Tests — Task 1 of pdf-upload-review spec.

These tests MUST FAIL on the unfixed code. Each failure documents a concrete
counterexample that proves the bug exists. DO NOT fix the code when these tests
fail — the failures are the expected outcome at this stage.

After all fixes are applied (Tasks 3–9), re-running this file should produce
all PASSING results (Task 10).

Validates: Requirements 1.1, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.10, 1.14, 1.16
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Environment setup — must happen before any app imports
# ---------------------------------------------------------------------------
os.environ["USE_SQLITE"] = "true"
os.environ["USE_MOCK_DATA"] = "false"
os.environ["REQUIRE_AUTH_FOR_DATA"] = "false"
os.environ["TENANT_REQUIRED"] = "false"
os.environ["PROJECT_ID"] = "test-project"

# Ensure the backend directory is on sys.path so imports work when running
# pytest from the workspace root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ---------------------------------------------------------------------------
# PDF paths (relative to workspace root)
# ---------------------------------------------------------------------------
# __file__ is at: <workspace>/finance-pilot/backend/tests/test_bug_condition_exploration.py
# parents[0] = tests/
# parents[1] = backend/
# parents[2] = finance-pilot/
# parents[3] = <workspace root>  (e.g. aihub_financial/)
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_CC_PDF = _WORKSPACE_ROOT / "data" / "Nubank_2026-05-04.pdf"
_CA_PDF = _WORKSPACE_ROOT / "data" / "NU_45499351_01ABR2026_30ABR2026.pdf"


# ---------------------------------------------------------------------------
# Shared fixture: in-memory SQLite DB with full schema
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    """Temporary SQLite database with the full schema required by the app."""
    db_path = tmp_path / "test_finance.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS current_account_movements (
            tenant_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            movement_id TEXT NOT NULL,
            date DATE,
            month_ref TEXT,
            amount_signed REAL,
            description TEXT,
            source_file TEXT,
            is_card_invoice_payment INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP,
            PRIMARY KEY (tenant_id, owner, movement_id)
        )
    """)

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

    # Redirect the app's database module to use this temp DB
    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    yield conn, db_path
    conn.close()


# ---------------------------------------------------------------------------
# Helper: mock Gemini to always raise an exception
# ---------------------------------------------------------------------------

def _gemini_always_fails(*args, **kwargs):
    raise RuntimeError("Gemini unavailable (mocked for bug exploration)")


# ===========================================================================
# Bug 1 — Fallback pdfplumber: empty transactions for credit card PDF
# ===========================================================================

def test_bug1_fallback_cc_transactions_not_empty():
    """Bug 1: pdfplumber fallback returns empty or garbage transactions for CC PDF.

    The fallback regex is too loose — it matches summary/header lines like
    "Total de saídas" instead of real transaction lines. Real transactions
    should have a merchant name and a non-zero amount.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: all extracted transactions have amount=0 or are summary rows
    """
    pytest.importorskip("pdfplumber")
    assert _CC_PDF.exists(), f"PDF not found: {_CC_PDF}"

    pdf_bytes = _CC_PDF.read_bytes()

    from extraction_service import ExtractionService

    svc = ExtractionService()
    with patch.object(svc, "_call_gemini", side_effect=_gemini_always_fails):
        result = svc.extract(pdf_bytes)

    # Real transactions must have amount > 0 and a meaningful description
    # (not summary rows like "Total de saídas" or "Total de entradas")
    real_transactions = [
        t
        for s in result.sections
        for t in s.transactions
        if t.amount > 0
        and "total de" not in t.description.lower()
        and "saldo" not in t.description.lower()
    ]

    # BUG: this assertion FAILS — fallback extracts only summary/header rows,
    # not real merchant transactions
    assert len(real_transactions) > 0, (
        f"Bug 1 confirmed: fallback extracted {sum(len(s.transactions) for s in result.sections)} "
        f"rows total but {len(real_transactions)} real merchant transactions "
        f"(expected > 0 real transactions with amount > 0 and non-summary descriptions). "
        f"Sample transactions: {[t.description for s in result.sections for t in s.transactions[:5]]}"
    )


# ===========================================================================
# Bug 1.4 — Fallback pdfplumber: holder_name defaults to "Titular"
# ===========================================================================

def test_bug1_4_fallback_cc_holder_name_not_default():
    """Bug 1.4: pdfplumber fallback returns holder_name='Titular' (default).

    EXPECTED TO FAIL on unfixed code.
    Counterexample: holder_name = "Titular"
    """
    pytest.importorskip("pdfplumber")
    assert _CC_PDF.exists(), f"PDF not found: {_CC_PDF}"

    pdf_bytes = _CC_PDF.read_bytes()

    from extraction_service import ExtractionService

    svc = ExtractionService()
    with patch.object(svc, "_call_gemini", side_effect=_gemini_always_fails):
        result = svc.extract(pdf_bytes)

    # BUG: this assertion FAILS — fallback returns "Titular" as default
    assert result.holder_name != "Titular", (
        f"Bug 1.4 confirmed: holder_name = {result.holder_name!r} "
        f"(expected real name, not default 'Titular')"
    )


# ===========================================================================
# Bug 1.5 — Fallback pdfplumber: period_start is hardcoded "2026-01-01"
# ===========================================================================

def test_bug1_5_fallback_cc_period_not_hardcoded():
    """Bug 1.5: pdfplumber fallback returns a garbage/wrong period_start.

    The regex in _extract_period matches arbitrary 4-digit numbers as years
    (e.g. "4549" from card numbers or other text), producing nonsensical dates
    like "4549-01-01". The correct period for this PDF (Nubank_2026-05-04.pdf)
    covers transactions from late March to late April 2026 (billing cycle for
    the May 2026 invoice).

    EXPECTED TO FAIL on unfixed code.
    Counterexample: period_start = "4549-01-01" (garbage from regex mismatch)
    """
    pytest.importorskip("pdfplumber")
    assert _CC_PDF.exists(), f"PDF not found: {_CC_PDF}"

    pdf_bytes = _CC_PDF.read_bytes()

    from extraction_service import ExtractionService

    svc = ExtractionService()
    with patch.object(svc, "_call_gemini", side_effect=_gemini_always_fails):
        result = svc.extract(pdf_bytes)

    # The PDF is the May 2026 invoice — period covers transactions in 2026
    # (billing cycle: ~28 MAR to 27 APR 2026, due date 04 MAI 2026).
    # BUG: this assertion FAILS — fallback returns garbage date like "4549-01-01"
    # because the regex matches card numbers or other 4-digit sequences as years.
    assert result.period_start.startswith("2026-"), (
        f"Bug 1.5 confirmed: period_start = {result.period_start!r} "
        f"(expected a date in 2026 like '2026-03-28' or '2026-04-01', got garbage from "
        f"regex matching non-date 4-digit numbers in the PDF text)"
    )


# ===========================================================================
# Bug 2 — Fallback pdfplumber: current account PDF returns wrong statement_type
# ===========================================================================

def test_bug2_fallback_ca_statement_type_correct():
    """Bug 2: pdfplumber fallback returns statement_type='credit_card' for CA PDF.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: statement_type = "credit_card"
    """
    pytest.importorskip("pdfplumber")
    assert _CA_PDF.exists(), f"PDF not found: {_CA_PDF}"

    pdf_bytes = _CA_PDF.read_bytes()

    from extraction_service import ExtractionService

    svc = ExtractionService()
    with patch.object(svc, "_call_gemini", side_effect=_gemini_always_fails):
        result = svc.extract(pdf_bytes)

    # BUG: this assertion FAILS — fallback hardcodes "credit_card"
    assert result.statement_type == "current_account", (
        f"Bug 2 confirmed: statement_type = {result.statement_type!r} "
        f"(expected 'current_account' for CA PDF, got 'credit_card' hardcoded)"
    )


# ===========================================================================
# Bug 3 — Classification: NuTag not classified as Transporte
# ===========================================================================

def test_bug3_classification_nutag_transporte(test_db):
    """Bug 3: NuTag merchant classified as 'Outros' instead of 'Transporte'.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: category = "Outros", needs_review = True
    """
    conn, db_path = test_db

    from categories import ClassificationService

    svc = ClassificationService()
    result = svc.classify("NuTag 0001 Rodovia SP-330", workspace_id="test")

    # BUG: this assertion FAILS — "nutag" keyword missing from DEFAULT_CATEGORIES
    assert result.category == "Transporte", (
        f"Bug 3 (NuTag) confirmed: category = {result.category!r}, "
        f"needs_review = {result.needs_review} "
        f"(expected category='Transporte', needs_review=False)"
    )
    assert result.needs_review is False, (
        f"Bug 3 (NuTag) confirmed: needs_review = {result.needs_review} "
        f"(expected False for known merchant)"
    )


# ===========================================================================
# Bug 3 — Classification: IFD* wildcard not working for iFood
# ===========================================================================

def test_bug3_classification_ifd_wildcard_delivery(test_db):
    """Bug 3: IFD* wildcard not interpreted as prefix — classified as 'Outros'.

    Uses "IFD*COMPRA 789" to avoid matching other keywords (e.g. "pizza" which
    would match Alimentação, or "restaurante" which also matches Alimentação,
    both appearing before Delivery in the dict iteration order).

    EXPECTED TO FAIL on unfixed code.
    Counterexample: category = "Outros" (wildcard "ifd*" never matches as substring)
    """
    conn, db_path = test_db

    from categories import ClassificationService

    svc = ClassificationService()
    result = svc.classify("IFD*COMPRA 789", workspace_id="test")

    # BUG: this assertion FAILS — "ifd*" is treated as literal string, not prefix
    assert result.category == "Delivery", (
        f"Bug 3 (IFD*) confirmed: category = {result.category!r} "
        f"(expected 'Delivery' for iFood prefix 'IFD*', got 'Outros' because "
        f"wildcard 'ifd*' is never a substring of real descriptions)"
    )


# ===========================================================================
# Bug 3 — Classification: Apple.Com/Bill not classified as Streaming
# ===========================================================================

def test_bug3_classification_apple_bill_streaming(test_db):
    """Bug 3: Apple.Com/Bill classified as 'Outros' instead of 'Streaming'.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: category = "Outros"
    """
    conn, db_path = test_db

    from categories import ClassificationService

    svc = ClassificationService()
    result = svc.classify("Apple.Com/Bill", workspace_id="test")

    # BUG: this assertion FAILS — "apple.com/bill" keyword missing from DEFAULT_CATEGORIES
    assert result.category == "Streaming", (
        f"Bug 3 (Apple.Com/Bill) confirmed: category = {result.category!r} "
        f"(expected 'Streaming', got 'Outros' because keyword is missing from "
        f"DEFAULT_CATEGORIES in categories.py)"
    )


# ===========================================================================
# Bug 5 — upload_history: statement_type hardcoded as "credit_card"
# ===========================================================================

def test_bug5_upload_history_statement_type_not_hardcoded(test_db, monkeypatch):
    """Bug 5: upload_history.statement_type is hardcoded 'credit_card'.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: upload_history.statement_type = "credit_card" (hardcoded)
    """
    conn, db_path = test_db

    # Import app after env vars are set
    from fastapi.testclient import TestClient  # noqa: PLC0415

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    # Re-import main to pick up the patched DB path
    import importlib
    import main as main_module
    importlib.reload(main_module)

    client = TestClient(main_module.app)

    # Build a minimal confirm request.
    # NOTE: UploadConfirmRequest currently has NO statement_type field — that's
    # part of Bug 5. We send a transaction and check what gets persisted.
    file_hash = hashlib.sha256(b"test-ca-pdf-content").hexdigest()

    confirm_body = {
        "file_hash": file_hash,
        "statement_type": "current_account",
        "transactions": [
            {
                "date": "2026-05-01",
                "card_last4": None,
                "description": "PIX enviado - Teste",
                "amount": 100.0,
                "is_refund": False,
                "category": "Transferência",
                "owner": "Victor",
            }
        ],
    }

    response = client.post(
        "/upload/confirm",
        json=confirm_body,
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert response.status_code == 200, (
        f"Unexpected error from /upload/confirm: {response.status_code} {response.text}"
    )

    # Check what was persisted in upload_history
    c = conn.cursor()
    c.execute(
        "SELECT statement_type FROM upload_history WHERE file_hash = ? ORDER BY created_at DESC LIMIT 1",
        (file_hash,),
    )
    row = c.fetchone()
    assert row is not None, "upload_history record not found"

    persisted_type = row["statement_type"]

    # With statement_type sent in the request, upload_history should persist it correctly.
    assert persisted_type == "current_account", (
        f"Bug 5 (upload_history) confirmed: statement_type = {persisted_type!r} "
        f"(expected 'current_account' but got hardcoded 'credit_card')"
    )


# ===========================================================================
# Bug 5 — Routing: current_account transactions saved to transactions_gold
# ===========================================================================

def test_bug5_current_account_routing_to_correct_table(test_db, monkeypatch):
    """Bug 5: current_account transactions are saved to transactions_gold instead
    of current_account_movements.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: persisted_to = "transactions_gold" (wrong table)
    """
    conn, db_path = test_db

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    import importlib
    import main as main_module
    importlib.reload(main_module)

    from fastapi.testclient import TestClient  # noqa: PLC0415
    client = TestClient(main_module.app)

    file_hash = hashlib.sha256(b"test-ca-routing-content").hexdigest()

    confirm_body = {
        "file_hash": file_hash,
        "statement_type": "current_account",
        "transactions": [
            {
                "date": "2026-05-02",
                "card_last4": None,
                "description": "PIX recebido - Salario",
                "amount": 5000.0,
                "is_refund": True,
                "category": "Transferência",
                "owner": "Victor",
            }
        ],
    }

    response = client.post(
        "/upload/confirm",
        json=confirm_body,
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert response.status_code == 200, (
        f"Unexpected error from /upload/confirm: {response.status_code} {response.text}"
    )

    c = conn.cursor()

    # Check current_account_movements — should have the transaction (but won't)
    c.execute(
        "SELECT COUNT(*) as cnt FROM current_account_movements WHERE tenant_id = 'test-tenant'",
    )
    ca_count = c.fetchone()["cnt"]

    # Check transactions_gold — should NOT have it (but will, due to the bug)
    c.execute(
        "SELECT COUNT(*) as cnt FROM transactions_gold WHERE tenant_id = 'test-tenant' AND merchant_clean LIKE '%PIX%'",
    )
    gold_count = c.fetchone()["cnt"]

    # With statement_type="current_account" in the request, the transaction should
    # be routed to current_account_movements, not transactions_gold.
    assert ca_count > 0, (
        f"Bug 5 (routing) confirmed: current_account_movements has {ca_count} rows "
        f"(expected > 0), transactions_gold has {gold_count} rows. "
        f"Transaction was routed to transactions_gold instead of current_account_movements."
    )


# ===========================================================================
# V2 Bug Condition Exploration Tests
# ===========================================================================
# These tests target the Gemini Flash Lite extraction pipeline bugs identified
# in the pdf-upload-fix-v2 spec. They mock _call_gemini to return controlled
# JSON strings that demonstrate the parser's inability to handle:
# 1. Transactions nested inside "sections" (not at top level)
# 2. Field name variants ("valor" instead of "amount", "data" instead of "date")
# 3. Markdown fences wrapping JSON responses
# 4. Use of GEMINI_RAW_PROMPT instead of GEMINI_EXTRACTION_PROMPT
#
# EXPECTED OUTCOME: All v2 tests FAIL on unfixed code — this proves the bugs exist.
# Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8
# ===========================================================================


def _empty_fallback_result():
    """Return a minimal empty ExtractedStatement for mocking the pdfplumber fallback."""
    from extraction_service import ExtractedStatement, ExtractedSection
    return ExtractedStatement(
        statement_type="credit_card",
        bank="Nubank",
        holder_name="Unknown",
        due_date=None,
        period_start="2026-01-01",
        period_end="2026-01-31",
        total_amount=0.0,
        sections=[ExtractedSection(owner_name="Unknown", subtotal=0.0, transactions=[])],
    )


# ---------------------------------------------------------------------------
# V2 Test 1: Transactions nested inside "sections" — parser fails to find them
# ---------------------------------------------------------------------------

def test_v2_nested_sections_transactions_extracted():
    """V2 Bug: _parse_raw_to_extracted() only looks at top-level "transactions".

    When Gemini Flash Lite returns JSON with transactions nested inside
    "sections" (e.g., {"sections": [{"card_holder": "Victor", "transactions": [...]}]}),
    the current parser does raw_dict.get("transactions", []) which returns []
    because transactions are nested one level deeper.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: _parse_raw_to_extracted({"sections": [{"transactions": [...]}]})
    returns ExtractedStatement with 0 transactions in all sections.
    """
    import json
    from unittest.mock import patch as mock_patch
    from extraction_service import ExtractionService

    # Simulate Flash Lite returning transactions nested inside "sections"
    nested_json = json.dumps({
        "statement_type": "credit_card",
        "bank": "Nubank",
        "holder_name": "Victor Zoré",
        "document_info": {
            "bank": "Nubank",
            "customer_name": "Victor Zoré",
            "due_date": "04 Mai 2026",
            "billing_period": {"start": "01 Abr 2026", "end": "30 Abr 2026"},
        },
        "sections": [
            {
                "card_holder": "Victor Zoré",
                "card_last4": "2456",
                "transactions": [
                    {
                        "date": "2026-04-05",
                        "description": "UBER *TRIP",
                        "amount": 12.50,
                        "is_refund": False,
                        "card_last4": "2456",
                    },
                    {
                        "date": "2026-04-10",
                        "description": "NETFLIX",
                        "amount": 55.90,
                        "is_refund": False,
                        "card_last4": "2456",
                    },
                    {
                        "date": "2026-03-28",
                        "description": "AMAZON.COM.BR",
                        "amount": 89.90,
                        "is_refund": False,
                        "card_last4": "2456",
                    },
                ],
            },
            {
                "card_holder": "Maria Zoré",
                "card_last4": "4535",
                "transactions": [
                    {
                        "date": "2026-04-12",
                        "description": "MERCADO LIVRE",
                        "amount": 199.00,
                        "is_refund": False,
                        "card_last4": "4535",
                    },
                ],
            },
        ],
    })

    svc = ExtractionService()

    # Mock _call_gemini to return our nested JSON, and mock fallback + sleep
    # to prevent pdfplumber from crashing on fake bytes
    with patch.object(svc, "_call_gemini", return_value=nested_json), \
         patch.object(svc, "_fallback_pdfplumber", return_value=_empty_fallback_result()), \
         mock_patch("time.sleep"):
        result = svc.extract(b"fake-pdf-bytes-v2-nested")

    # Assert: the parser should extract transactions from nested sections
    all_transactions = [t for s in result.sections for t in s.transactions]

    assert len(result.sections) > 0, (
        f"V2 Bug (nested sections): result has {len(result.sections)} sections (expected > 0)"
    )
    assert len(all_transactions) > 0, (
        f"V2 Bug (nested sections) confirmed: parser extracted 0 transactions "
        f"from nested 'sections' structure. raw_dict.get('transactions', []) returns [] "
        f"because transactions are inside sections[].transactions, not at top level."
    )
    assert any(t.amount > 0 for t in all_transactions), (
        f"V2 Bug (nested sections): all transactions have amount=0 "
        f"(expected at least one with amount > 0)"
    )


# ---------------------------------------------------------------------------
# V2 Test 2: Field name variants — parser doesn't recognize "valor", "data"
# ---------------------------------------------------------------------------

def test_v2_field_name_variants_extracted_correctly():
    """V2 Bug: _parse_raw_to_extracted() only recognizes "amount" and "date".

    When Gemini Flash Lite returns transactions with Portuguese field names
    like "valor" (instead of "amount") and "data" (instead of "date"), the
    current parser produces amount=0.0 and date="2026-01-01" (defaults).

    EXPECTED TO FAIL on unfixed code.
    Counterexample: transactions with "valor": 150.0 produce amount=0.0;
    transactions with "data": "2026-04-15" produce date="2026-01-01".
    """
    import json
    from unittest.mock import patch as mock_patch
    from extraction_service import ExtractionService

    # Simulate Flash Lite returning Portuguese field names
    variant_json = json.dumps({
        "bank": "Nubank",
        "holder_name": "Victor Zoré",
        "document_info": {
            "bank": "Nubank",
            "customer_name": "Victor Zoré",
            "due_date": "04 Mai 2026",
            "billing_period": {"start": "01 Abr 2026", "end": "30 Abr 2026"},
        },
        "transactions": [
            {
                "data": "2026-04-15",
                "descricao": "UBER *TRIP",
                "valor": 150.00,
                "is_refund": False,
                "card_last4": "2456",
            },
            {
                "data": "2026-04-20",
                "descricao": "MERCADO LIVRE",
                "valor": 299.90,
                "is_refund": False,
                "card_last4": "2456",
            },
            {
                "data": "2026-03-28",
                "descricao": "NETFLIX",
                "valor": 55.90,
                "is_refund": False,
                "card_last4": "2456",
            },
        ],
    })

    svc = ExtractionService()

    with patch.object(svc, "_call_gemini", return_value=variant_json), \
         patch.object(svc, "_fallback_pdfplumber", return_value=_empty_fallback_result()), \
         mock_patch("time.sleep"):
        result = svc.extract(b"fake-pdf-bytes-v2-variants")

    all_transactions = [t for s in result.sections for t in s.transactions]

    # The parser should recognize "valor" as amount and "data" as date
    assert len(all_transactions) > 0, (
        f"V2 Bug (field variants): no transactions extracted at all"
    )

    # Check that amounts are NOT the default 0.0
    amounts = [t.amount for t in all_transactions]
    assert all(a > 0 for a in amounts), (
        f"V2 Bug (field variants) confirmed: parser produced amounts={amounts} "
        f"(expected all > 0, but got 0.0 defaults because 'valor' is not recognized "
        f"as an amount field). The parser only checks raw_tx.get('amount')."
    )

    # Check that dates are NOT the default "2026-01-01"
    dates = [t.date for t in all_transactions]
    assert all(d != "2026-01-01" for d in dates), (
        f"V2 Bug (field variants) confirmed: parser produced dates={dates} "
        f"(expected valid ISO dates like '2026-04-15', but got '2026-01-01' defaults "
        f"because 'data' is not recognized as a date field). "
        f"The parser only checks raw_tx.get('date')."
    )

    # Check descriptions are not empty (parser should recognize "descricao")
    descriptions = [t.description for t in all_transactions]
    assert all(d and len(d) > 0 for d in descriptions), (
        f"V2 Bug (field variants): parser produced empty descriptions={descriptions} "
        f"(expected non-empty, 'descricao' not recognized as description field)"
    )


# ---------------------------------------------------------------------------
# V2 Test 3: Markdown fences wrapping JSON — parsing fails
# ---------------------------------------------------------------------------

def test_v2_markdown_fences_edge_case_parsed():
    """V2 Bug: _call_gemini fence-stripping is fragile for edge cases.

    When Gemini Flash Lite returns JSON wrapped in markdown fences with
    additional content (e.g., language tag, trailing text), the manual
    fence-stripping logic may fail. With response_mime_type="application/json"
    this wouldn't happen, but without it the model wraps output in fences.

    This test verifies that even with markdown fences containing edge cases
    (like a description field with backticks inside), the extraction succeeds.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: json.loads() fails because fence-stripping removes wrong lines.
    """
    from unittest.mock import patch as mock_patch
    from extraction_service import ExtractionService

    # Simulate Flash Lite returning JSON wrapped in markdown fences
    # with a description containing backticks (edge case that breaks naive stripping)
    fenced_response = '```json\n{\n    "bank": "Nubank",\n    "holder_name": "Victor Zoré",\n    "document_info": {\n        "bank": "Nubank",\n        "customer_name": "Victor Zoré",\n        "due_date": "04 Mai 2026",\n        "billing_period": {"start": "01 Abr 2026", "end": "30 Abr 2026"}\n    },\n    "transactions": [\n        {\n            "date": "2026-04-05",\n            "description": "UBER *TRIP ```special``` promo",\n            "amount": 12.50,\n            "is_refund": false,\n            "card_last4": "2456"\n        },\n        {\n            "date": "2026-04-10",\n            "description": "NETFLIX",\n            "amount": 55.90,\n            "is_refund": false,\n            "card_last4": "2456"\n        }\n    ]\n}\n```'

    svc = ExtractionService()

    with patch.object(svc, "_call_gemini", return_value=fenced_response), \
         patch.object(svc, "_fallback_pdfplumber", return_value=_empty_fallback_result()), \
         mock_patch("time.sleep"):
        result = svc.extract(b"fake-pdf-bytes-v2-fences")

    all_transactions = [t for s in result.sections for t in s.transactions]

    # The extraction should succeed and produce valid transactions
    assert len(result.sections) > 0, (
        f"V2 Bug (markdown fences): extraction produced 0 sections"
    )
    assert len(all_transactions) > 0, (
        f"V2 Bug (markdown fences) confirmed: extraction failed to parse JSON "
        f"wrapped in markdown fences with edge cases (backticks in description). "
        f"The fence-stripping logic removes lines containing '```' which breaks "
        f"the JSON when descriptions contain backtick sequences."
    )
    assert all(t.amount > 0 for t in all_transactions), (
        f"V2 Bug (markdown fences): transactions have amount=0 after fence parsing"
    )


# ---------------------------------------------------------------------------
# V2 Test 4: Current code uses GEMINI_RAW_PROMPT (not the detailed one)
# ---------------------------------------------------------------------------

def test_v2_extract_uses_detailed_prompt():
    """V2 Bug: extract() uses GEMINI_RAW_PROMPT instead of GEMINI_EXTRACTION_PROMPT.

    The detailed GEMINI_EXTRACTION_PROMPT (150+ lines with Nubank-specific rules,
    few-shot examples, and explicit JSON schema) exists in extraction_service.py
    but is never used in the primary extraction path. The code always passes
    prompt=GEMINI_RAW_PROMPT to _call_gemini().

    This test captures the prompt argument passed to _call_gemini and verifies
    it contains Nubank-specific instructions (indicating the detailed prompt is used).

    EXPECTED TO FAIL on unfixed code.
    Counterexample: prompt passed to _call_gemini is the 4-line generic prompt
    "Identify all fields..." instead of the detailed one with "Nubank" instructions.
    """
    import json
    from unittest.mock import patch as mock_patch
    from extraction_service import ExtractionService, GEMINI_EXTRACTION_PROMPT

    # We'll capture what prompt is passed to _call_gemini
    captured_prompts = []

    def mock_call_gemini(pdf_bytes, prompt=None):
        captured_prompts.append(prompt)
        # Return valid JSON so the extraction doesn't fall through to pdfplumber
        return json.dumps({
            "statement_type": "credit_card",
            "bank": "Nubank",
            "holder_name": "Victor Zoré",
            "due_date": "2026-05-04",
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "total_amount": 1500.00,
            "document_info": {
                "bank": "Nubank",
                "customer_name": "Victor Zoré",
                "due_date": "04 Mai 2026",
                "billing_period": {"start": "01 Abr 2026", "end": "30 Abr 2026"},
            },
            "transactions": [
                {
                    "date": "2026-04-05",
                    "description": "UBER *TRIP",
                    "amount": 12.50,
                    "is_refund": False,
                    "card_last4": "2456",
                },
                {
                    "date": "2026-04-10",
                    "description": "NETFLIX",
                    "amount": 55.90,
                    "is_refund": False,
                    "card_last4": "2456",
                },
            ],
        })

    svc = ExtractionService()

    with patch.object(svc, "_call_gemini", side_effect=mock_call_gemini), \
         patch.object(svc, "_fallback_pdfplumber", return_value=_empty_fallback_result()), \
         mock_patch("time.sleep"):
        svc.extract(b"fake-pdf-bytes-v2-prompt-check")

    # Verify the prompt used contains Nubank-specific instructions
    assert len(captured_prompts) > 0, "No prompt was captured — _call_gemini was not called"

    prompt_used = captured_prompts[0]

    # The detailed prompt contains "Nubank" specific instructions, "CREDIT CARD",
    # "CURRENT ACCOUNT", few-shot examples, etc.
    assert "Nubank" in prompt_used, (
        f"V2 Bug (wrong prompt) confirmed: extract() uses the generic GEMINI_RAW_PROMPT "
        f"('Identify all fields...') instead of GEMINI_EXTRACTION_PROMPT which contains "
        f"Nubank-specific instructions. Prompt starts with: {prompt_used[:80]!r}..."
    )
    assert "credit_card" in prompt_used.lower() or "CREDIT CARD" in prompt_used, (
        f"V2 Bug (wrong prompt): prompt does not contain credit card detection rules. "
        f"The detailed prompt should include statement type detection instructions."
    )
    assert prompt_used == GEMINI_EXTRACTION_PROMPT, (
        f"V2 Bug (wrong prompt) confirmed: prompt passed to _call_gemini is NOT "
        f"GEMINI_EXTRACTION_PROMPT. The code uses GEMINI_RAW_PROMPT (generic 4-line prompt) "
        f"instead of the detailed 150+ line prompt with Nubank-specific rules."
    )
