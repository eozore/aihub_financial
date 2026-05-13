"""Preservation Tests — Task 2 of pdf-upload-review spec.

These tests capture the BASELINE behaviours that must NOT be broken by any fix.
They MUST PASS on the unfixed code.  If any of these tests fail after a fix is
applied, the fix introduced a regression.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10,
           3.11, 3.12
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Environment setup — must happen before any app imports
# ---------------------------------------------------------------------------
os.environ["USE_SQLITE"] = "true"
os.environ["USE_MOCK_DATA"] = "false"
os.environ["REQUIRE_AUTH_FOR_DATA"] = "false"
os.environ["TENANT_REQUIRED"] = "false"
os.environ["PROJECT_ID"] = "test-project"

# Ensure the backend directory is on sys.path so bare imports work when
# running pytest from the workspace root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ---------------------------------------------------------------------------
# Hypothesis imports (property-based testing)
# ---------------------------------------------------------------------------
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

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

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    yield conn, db_path
    conn.close()


# ===========================================================================
# Preservation 1 — CSV upload inalterado
# ===========================================================================

# All known keywords from DEFAULT_CATEGORIES in categories.py — used to
# generate merchants that DO match a known category (for Preservation 1).
_KNOWN_MERCHANTS = [
    "restaurante do bairro",
    "ifood pedido",
    "mercado extra",
    "uber trip",
    "aluguel mensal",
    "farmacia popular",
    "curso udemy",
    "cinema ingresso",
    "netflix assinatura",
    "shopee compra",
    "google one assinatura",
    "airbnb hospedagem",
    "petlove compra",
    "iof taxa",
    "pix transferencia",
]


@given(merchant=st.sampled_from(_KNOWN_MERCHANTS))
@settings(max_examples=15, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_preservation1_csv_classification_consistent(merchant):
    """Preservation 1: ClassificationService.classify() returns a consistent,
    non-empty result for any merchant string.

    Validates: Requirements 3.1, 3.2
    """
    from categories import ClassificationService

    svc = ClassificationService()
    result = svc.classify(merchant, workspace_id="test-workspace")

    # The result must always have a non-empty category
    assert result.category, (
        f"Preservation 1 FAILED: classify({merchant!r}) returned empty category"
    )
    # The result must be one of the known categories or "Outros"
    from categories import DEFAULT_CATEGORIES
    valid_categories = set(DEFAULT_CATEGORIES.keys())
    assert result.category in valid_categories, (
        f"Preservation 1 FAILED: classify({merchant!r}) returned unknown category "
        f"{result.category!r}. Valid categories: {valid_categories}"
    )


# ===========================================================================
# Preservation 2 — Gemini bem-sucedido não aciona fallback
# ===========================================================================

def _make_valid_statement_json() -> str:
    """Return a valid free-form Gemini Stage-1 JSON string.

    Mirrors the structure returned by GEMINI_RAW_PROMPT so that
    _parse_raw_to_extracted() can convert it to an ExtractedStatement.
    """
    return json.dumps({
        "document_info": {
            "bank": "Nubank",
            "customer_name": "Victor Zore",
            "due_date": "04 MAI 2026",
            "billing_period": {"start": "01 ABR", "end": "30 ABR"},
        },
        "summary": {
            "total_purchases": 150.00,
            "total_to_pay": 150.00,
        },
        "transactions": [
            {
                "date": "10 ABR",
                "description": "UBER *TRIP",
                "card_last_digits": "4535",
                "amount": 25.50,
            }
        ],
    })


def test_preservation2_gemini_success_no_fallback():
    """Preservation 2: When Gemini returns valid JSON, _fallback_pdfplumber is
    NOT called and the result is the ExtractedStatement from Gemini.

    Validates: Requirements 3.3, 3.4
    """
    from extraction_service import ExtractionService, ExtractedStatement

    svc = ExtractionService()

    with patch.object(svc, "_call_gemini", return_value=_make_valid_statement_json()) as mock_gemini, \
         patch.object(svc, "_fallback_pdfplumber") as mock_fallback:

        result = svc.extract(b"fake-pdf-bytes-for-preservation-2")

    # Gemini was called once
    assert mock_gemini.call_count == 1, (
        f"Preservation 2 FAILED: _call_gemini called {mock_gemini.call_count} times "
        f"(expected 1)"
    )
    # Fallback was NOT called
    assert mock_fallback.call_count == 0, (
        f"Preservation 2 FAILED: _fallback_pdfplumber was called "
        f"{mock_fallback.call_count} times (expected 0 when Gemini succeeds)"
    )
    # Result is an ExtractedStatement from Gemini
    assert isinstance(result, ExtractedStatement), (
        f"Preservation 2 FAILED: result is {type(result)}, expected ExtractedStatement"
    )
    assert result.bank == "Nubank", (
        f"Preservation 2 FAILED: result.bank = {result.bank!r} (expected 'Nubank')"
    )
    assert result.holder_name == "Victor Zore", (
        f"Preservation 2 FAILED: result.holder_name = {result.holder_name!r}"
    )


# ===========================================================================
# Preservation 3 — Cache em memória funciona
# ===========================================================================

def test_preservation3_in_memory_cache_works():
    """Preservation 3: Calling extract() twice with the same PDF bytes uses the
    in-memory cache — _call_gemini is called only once.

    Validates: Requirements 3.5, 3.6
    """
    from extraction_service import ExtractionService

    svc = ExtractionService()
    pdf_bytes = b"same-pdf-content-for-cache-test-preservation-3"

    call_count = 0

    def mock_gemini(pdf, prompt=None):
        nonlocal call_count
        call_count += 1
        return _make_valid_statement_json()

    with patch.object(svc, "_call_gemini", side_effect=mock_gemini):
        result1 = svc.extract(pdf_bytes)
        result2 = svc.extract(pdf_bytes)

    # Gemini called only once — second call uses cache
    assert call_count == 1, (
        f"Preservation 3 FAILED: _call_gemini called {call_count} times "
        f"(expected 1 — second call should use cache)"
    )
    # Both results are identical
    assert result1 == result2, (
        f"Preservation 3 FAILED: cached result differs from original result"
    )


# ===========================================================================
# Preservation 4 — Regras de workspace têm prioridade máxima
# ===========================================================================

def test_preservation4_workspace_rule_takes_priority(test_db):
    """Preservation 4: When a workspace rule exists for a merchant, it takes
    priority over default keyword matching — regardless of what keywords match.

    Validates: Requirements 3.7, 3.8
    """
    conn, db_path = test_db

    from categories import ClassificationService

    svc = ClassificationService()

    # "uber" would normally match "Transporte" via default keywords.
    # We create a workspace rule that overrides it to "Viagem".
    workspace_rule = {"category": "Viagem"}

    with patch.object(
        ClassificationService,
        "_get_workspace_rule",
        return_value=workspace_rule,
    ):
        result = svc.classify("uber trip", workspace_id="test-workspace")

    # Workspace rule must win over keyword match
    assert result.category == "Viagem", (
        f"Preservation 4 FAILED: category = {result.category!r} "
        f"(expected 'Viagem' from workspace rule, not keyword-matched category)"
    )
    assert result.needs_review is False, (
        f"Preservation 4 FAILED: needs_review = {result.needs_review} "
        f"(expected False when workspace rule is found)"
    )


# ===========================================================================
# Preservation 5 — Validações de upload inalteradas
# ===========================================================================

def test_preservation5_file_too_large_returns_413(test_db, monkeypatch):
    """Preservation 5a: Uploading a file > 10 MB returns HTTP 413.

    Validates: Requirements 3.9, 3.10
    """
    conn, db_path = test_db

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    import importlib
    import main as main_module
    importlib.reload(main_module)

    from fastapi.testclient import TestClient
    client = TestClient(main_module.app)

    # Create a file slightly larger than 10 MB
    large_content = b"x" * (10 * 1024 * 1024 + 1)

    response = client.post(
        "/upload",
        files={"file": ("big_file.pdf", io.BytesIO(large_content), "application/pdf")},
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert response.status_code == 413, (
        f"Preservation 5a FAILED: expected HTTP 413 for file > 10 MB, "
        f"got {response.status_code}: {response.text}"
    )


def test_preservation5_invalid_extension_returns_400(test_db, monkeypatch):
    """Preservation 5b: Uploading a .txt file returns HTTP 400.

    Validates: Requirements 3.9, 3.10
    """
    conn, db_path = test_db

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    import importlib
    import main as main_module
    importlib.reload(main_module)

    from fastapi.testclient import TestClient
    client = TestClient(main_module.app)

    txt_content = b"This is a plain text file, not a PDF or CSV."

    response = client.post(
        "/upload",
        files={"file": ("document.txt", io.BytesIO(txt_content), "text/plain")},
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert response.status_code == 400, (
        f"Preservation 5b FAILED: expected HTTP 400 for .txt extension, "
        f"got {response.status_code}: {response.text}"
    )


# ===========================================================================
# Preservation 6 — Fallback para "Outros" inalterado
# ===========================================================================

# All known keywords from DEFAULT_CATEGORIES — used to filter them out
_ALL_KNOWN_KEYWORDS = [
    "restaurante", "bar", "padaria", "lanchonete", "pizza", "sushi",
    "ifood", "rappi", "uber eats", "ifd",
    "mercado", "supermercado", "hortifruti", "carrefour",
    "uber", "99", "combustivel", "posto", "estacionamento", "pedagio",
    "aluguel", "condominio", "luz", "energia", "agua", "internet",
    "farmacia", "drogaria", "medico", "academia", "totalpass",
    "curso", "escola", "udemy", "alura", "linkedin",
    "cinema", "show", "ingresso", "parque",
    "netflix", "spotify", "disney", "hbo", "amazon prime", "youtube premium",
    "shopee", "mercado livre", "amazon", "magazine",
    "google one", "icloud", "canva", "chatgpt", "github",
    "airbnb", "hotel", "pousada", "booking", "azul", "latam",
    "petlove", "petshop", "veterinario",
    "iof", "anuidade", "taxa",
    "pix", "ted", "transferencia",
]


def _has_known_keyword(text: str) -> bool:
    """Return True if text contains any known keyword (case-insensitive)."""
    lower = text.lower()
    return any(kw in lower for kw in _ALL_KNOWN_KEYWORDS)


@given(
    merchant=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters=" -_",
        ),
        min_size=5,
        max_size=40,
    ).filter(lambda s: not _has_known_keyword(s) and s.strip())
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_preservation6_unknown_merchant_falls_back_to_outros(merchant):
    """Preservation 6: Any merchant string that contains no known keyword must
    be classified as 'Outros' with needs_review=True.

    Validates: Requirements 3.11, 3.12
    """
    from categories import ClassificationService

    svc = ClassificationService()

    # Patch _get_workspace_rule to return None (no workspace rule)
    with patch.object(ClassificationService, "_get_workspace_rule", return_value=None):
        result = svc.classify(merchant, workspace_id="test-workspace")

    assert result.category == "Outros", (
        f"Preservation 6 FAILED: classify({merchant!r}) returned category="
        f"{result.category!r} (expected 'Outros' for unknown merchant)"
    )
    assert result.needs_review is True, (
        f"Preservation 6 FAILED: classify({merchant!r}) returned needs_review="
        f"{result.needs_review} (expected True for unknown merchant)"
    )


# ===========================================================================
# Preservation 7 — Gemini com 3 falhas aciona fallback pdfplumber
# ===========================================================================

def test_preservation7_three_gemini_failures_trigger_fallback():
    """Preservation 7: When _call_gemini fails on all 3 attempts, the service
    falls back to _fallback_pdfplumber and returns its result.

    Validates: Requirements 3.3, 3.4
    """
    from extraction_service import ExtractionService, ExtractedStatement

    svc = ExtractionService()

    fallback_result = ExtractedStatement(
        statement_type="credit_card",
        bank="Nubank",
        holder_name="Victor Zore",
        due_date=None,
        period_start="2026-04-01",
        period_end="2026-04-30",
        total_amount=500.00,
        sections=[],
    )

    with patch.object(
        svc, "_call_gemini", side_effect=RuntimeError("Gemini unavailable")
    ) as mock_gemini, patch.object(
        svc, "_fallback_pdfplumber", return_value=fallback_result
    ) as mock_fallback:
        result = svc.extract(b"fake-pdf-for-preservation-7")

    # Gemini was attempted 3 times
    assert mock_gemini.call_count == 3, (
        f"Preservation 7 FAILED: _call_gemini called {mock_gemini.call_count} times "
        f"(expected 3 attempts before fallback)"
    )
    # Fallback was called exactly once
    assert mock_fallback.call_count == 1, (
        f"Preservation 7 FAILED: _fallback_pdfplumber called {mock_fallback.call_count} "
        f"times (expected 1)"
    )
    # Result is the fallback result
    assert result == fallback_result, (
        f"Preservation 7 FAILED: result is not the fallback result"
    )


# ===========================================================================
# V2 Preservation Tests — pdf-upload-fix-v2 spec (Task 2)
# ===========================================================================
# These tests validate preservation concerns specific to the v2 bugfix.
# They MUST PASS on the unfixed code (confirms baseline behavior to preserve).
# Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6


def test_v2_cache_preservation():
    """V2 Preservation — Cache: When a PDF is processed once via extract(),
    a second call with the same bytes returns the cached result without
    invoking _call_gemini again.

    Validates: Requirements 3.3, 3.5
    """
    from extraction_service import ExtractionService, ExtractedStatement

    svc = ExtractionService()
    pdf_bytes = b"v2-cache-preservation-test-pdf-content"

    with patch.object(svc, "_call_gemini", return_value=_make_valid_statement_json()) as mock_gemini:
        result1 = svc.extract(pdf_bytes)
        result2 = svc.extract(pdf_bytes)

    # _call_gemini should only be called once (first call); second uses cache
    assert mock_gemini.call_count == 1, (
        f"V2 Cache Preservation FAILED: _call_gemini called {mock_gemini.call_count} "
        f"times (expected 1 — second call should use cache)"
    )
    # Both results must be identical
    assert result1 == result2, (
        "V2 Cache Preservation FAILED: cached result differs from original"
    )
    # Result must be a valid ExtractedStatement
    assert isinstance(result1, ExtractedStatement), (
        f"V2 Cache Preservation FAILED: result type is {type(result1)}, "
        f"expected ExtractedStatement"
    )


def test_v2_fallback_preservation():
    """V2 Preservation — Fallback: When _call_gemini raises an exception on
    all 3 retries, extract() falls back to pdfplumber and returns a valid
    ExtractedStatement (with statement_type field, non-empty bank, etc.).

    Validates: Requirements 3.1, 3.2
    """
    from extraction_service import ExtractionService, ExtractedStatement

    svc = ExtractionService()

    # Mock _call_gemini to always raise an exception (simulating 3 failures)
    with patch.object(
        svc, "_call_gemini", side_effect=RuntimeError("Gemini API unavailable")
    ) as mock_gemini:
        # Use a real PDF from the data folder for pdfplumber to parse
        pdf_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "NU_45499351_01ABR2026_30ABR2026.pdf"
        if pdf_path.exists():
            pdf_bytes = pdf_path.read_bytes()
        else:
            # Fallback: use the PDF from finance-pilot/data if available
            alt_path = Path(__file__).resolve().parent.parent.parent / "data" / "NU_45499351_01ABR2026_30ABR2026.pdf"
            if alt_path.exists():
                pdf_bytes = alt_path.read_bytes()
            else:
                pytest.skip("No real PDF available for fallback test")

        result = svc.extract(pdf_bytes)

    # Gemini was attempted 3 times before fallback
    assert mock_gemini.call_count == 3, (
        f"V2 Fallback Preservation FAILED: _call_gemini called "
        f"{mock_gemini.call_count} times (expected 3 attempts before fallback)"
    )
    # Result must be a valid ExtractedStatement
    assert isinstance(result, ExtractedStatement), (
        f"V2 Fallback Preservation FAILED: result type is {type(result)}, "
        f"expected ExtractedStatement"
    )
    # statement_type must be set
    assert result.statement_type in ("credit_card", "current_account"), (
        f"V2 Fallback Preservation FAILED: statement_type = {result.statement_type!r}"
    )
    # bank must be non-empty
    assert result.bank and len(result.bank) > 0, (
        f"V2 Fallback Preservation FAILED: bank is empty or None"
    )


def test_v2_pdfplumber_fallback_still_works():
    """V2 Preservation — pdfplumber fallback still works: When _call_gemini
    always raises an exception, extract() with a real PDF returns a result
    with statement_type set and bank set.

    Validates: Requirements 3.1, 3.2, 3.6
    """
    from extraction_service import ExtractionService, ExtractedStatement

    svc = ExtractionService()

    # Mock _call_gemini to always raise (forces pdfplumber fallback)
    with patch.object(
        svc, "_call_gemini", side_effect=Exception("Forced failure for v2 test")
    ) as mock_gemini:
        # Try the current account PDF
        pdf_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "Nubank_2026-05-04.pdf"
        if pdf_path.exists():
            pdf_bytes = pdf_path.read_bytes()
        else:
            alt_path = Path(__file__).resolve().parent.parent.parent / "data" / "Nubank_2026-05-04.pdf"
            if alt_path.exists():
                pdf_bytes = alt_path.read_bytes()
            else:
                pytest.skip("No real PDF available for pdfplumber fallback test")

        result = svc.extract(pdf_bytes)

    # Gemini was attempted 3 times
    assert mock_gemini.call_count == 3, (
        f"V2 pdfplumber Fallback FAILED: _call_gemini called "
        f"{mock_gemini.call_count} times (expected 3)"
    )
    # Result must be a valid ExtractedStatement
    assert isinstance(result, ExtractedStatement), (
        f"V2 pdfplumber Fallback FAILED: result type is {type(result)}"
    )
    # statement_type must be set to a valid value
    assert result.statement_type in ("credit_card", "current_account"), (
        f"V2 pdfplumber Fallback FAILED: statement_type = {result.statement_type!r}"
    )
    # bank must be set
    assert result.bank and len(result.bank) > 0, (
        f"V2 pdfplumber Fallback FAILED: bank is empty or None"
    )
    # holder_name should be set (pdfplumber extracts it)
    assert result.holder_name and result.holder_name != "Unknown", (
        f"V2 pdfplumber Fallback FAILED: holder_name = {result.holder_name!r}"
    )
