"""Integration tests with real PDFs from the data/ folder.

Tests validate the full extraction pipeline (fallback + Gemini mock) and the
complete preview → confirm flow using the FastAPI TestClient.

Validates: Requirements 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.14, 2.16, 3.1
"""

from __future__ import annotations

import hashlib
import importlib
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

# Ensure the backend directory is on sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ---------------------------------------------------------------------------
# PDF / CSV paths (relative to workspace root)
# ---------------------------------------------------------------------------
# __file__ is at: <workspace>/finance-pilot/backend/tests/test_integration_pdf_upload.py
# parents[0] = tests/
# parents[1] = backend/
# parents[2] = finance-pilot/
# parents[3] = <workspace root>
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_CC_PDF = _WORKSPACE_ROOT / "data" / "Nubank_2026-05-04.pdf"
_CA_PDF = _WORKSPACE_ROOT / "data" / "NU_45499351_01ABR2026_30ABR2026.pdf"
_CSV_FILE = _WORKSPACE_ROOT / "data" / "fatura_victor_2026-03.csv"


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

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT,
            plan_type TEXT NOT NULL DEFAULT 'free',
            is_admin INTEGER NOT NULL DEFAULT 0,
            active_workspace_id TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            member_limit INTEGER,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP,
            PRIMARY KEY (workspace_id, user_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS workspace_invites (
            id TEXT PRIMARY KEY,
            workspace_id TEXT,
            inviter_user_id TEXT NOT NULL,
            invitee_email TEXT NOT NULL,
            invite_mode TEXT NOT NULL,
            target_workspace_name TEXT,
            status TEXT NOT NULL,
            created_at TIMESTAMP,
            accepted_at TIMESTAMP
        )
    """)

    conn.commit()

    # Redirect the app's database module to use this temp DB
    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    yield conn, db_path
    conn.close()


# ---------------------------------------------------------------------------
# Helper: mock Gemini to always raise an exception (force fallback)
# ---------------------------------------------------------------------------

def _gemini_always_fails(*args, **kwargs):
    raise RuntimeError("Gemini unavailable (mocked for integration test)")


# ---------------------------------------------------------------------------
# Helper: build a minimal valid Gemini JSON response
# ---------------------------------------------------------------------------

def _make_gemini_mock_response(statement_type: str, bank: str = "Nubank") -> MagicMock:
    """Return a mock Gemini client whose generate_content returns valid JSON."""
    if statement_type == "credit_card":
        payload = {
            "statement_type": "credit_card",
            "bank": bank,
            "holder_name": "Victor De Almeida Zoré",
            "due_date": "2026-05-04",
            "period_start": "2026-03-28",
            "period_end": "2026-04-27",
            "total_amount": 9580.75,
            "sections": [
                {
                    "owner_name": "Victor De Almeida Zoré",
                    "subtotal": 9580.75,
                    "transactions": [
                        {
                            "date": "2026-04-05",
                            "card_last4": None,
                            "description": "UBER *TRIP",
                            "amount": 25.50,
                            "is_refund": False,
                            "is_installment": False,
                            "installment_current": None,
                            "installment_total": None,
                            "original_currency": None,
                        },
                        {
                            "date": "2026-04-10",
                            "card_last4": None,
                            "description": "IFOOD*RESTAURANTE",
                            "amount": 45.00,
                            "is_refund": False,
                            "is_installment": False,
                            "installment_current": None,
                            "installment_total": None,
                            "original_currency": None,
                        },
                    ],
                }
            ],
        }
    else:
        payload = {
            "statement_type": "current_account",
            "bank": bank,
            "holder_name": "Victor De Almeida Zoré",
            "due_date": None,
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "total_amount": 1500.00,
            "sections": [
                {
                    "owner_name": "Victor De Almeida Zoré",
                    "subtotal": 1500.00,
                    "transactions": [
                        {
                            "date": "2026-04-05",
                            "card_last4": None,
                            "description": "PIX enviado - Aluguel",
                            "amount": 2000.00,
                            "is_refund": False,
                            "is_installment": False,
                            "installment_current": None,
                            "installment_total": None,
                            "original_currency": None,
                        },
                        {
                            "date": "2026-04-01",
                            "card_last4": None,
                            "description": "PIX recebido - Salario",
                            "amount": 5000.00,
                            "is_refund": True,
                            "is_installment": False,
                            "installment_current": None,
                            "installment_total": None,
                            "original_currency": None,
                        },
                    ],
                }
            ],
        }

    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


# ===========================================================================
# Teste 1 — Fallback CC com PDF real (Nubank_2026-05-04.pdf)
# ===========================================================================

def test_fallback_credit_card_real_pdf():
    """Teste 1: Fallback pdfplumber extrai corretamente o PDF de cartão de crédito.

    Usa Nubank_2026-05-04.pdf (fatura de cartão de crédito de maio 2026).
    Gemini é mockado para falhar em todas as tentativas, forçando o fallback.
    """
    pytest.importorskip("pdfplumber")
    assert _CC_PDF.exists(), f"PDF não encontrado: {_CC_PDF}"

    pdf_bytes = _CC_PDF.read_bytes()

    from extraction_service import ExtractionService

    svc = ExtractionService()
    with patch.object(svc, "_call_gemini", side_effect=_gemini_always_fails):
        result = svc.extract(pdf_bytes)

    # statement_type deve ser credit_card
    assert result.statement_type == "credit_card", (
        f"Esperado statement_type='credit_card', obtido: {result.statement_type!r}"
    )

    # holder_name não deve ser o valor padrão/vazio
    assert result.holder_name not in ["Titular", "", None], (
        f"holder_name inválido: {result.holder_name!r} (esperado nome real)"
    )

    # period_start deve ser em 2026 (não hardcoded ou garbage)
    assert result.period_start.startswith("2026-"), (
        f"period_start inválido: {result.period_start!r} (esperado data em 2026)"
    )

    # Deve ter pelo menos uma seção
    assert len(result.sections) > 0, "Nenhuma seção extraída"

    # Deve ter pelo menos uma transação
    total_txns = sum(len(s.transactions) for s in result.sections)
    assert total_txns > 0, (
        f"Nenhuma transação extraída (sections={len(result.sections)}, "
        f"sample descriptions: {[t.description for s in result.sections for t in s.transactions[:3]]!r})"
    )


# ===========================================================================
# Teste 2 — Conta corrente com PDF real (NU_45499351_01ABR2026_30ABR2026.pdf)
# ===========================================================================

def test_fallback_current_account_real_pdf():
    """Teste 2: Fallback pdfplumber extrai corretamente o extrato de conta corrente.

    Usa NU_45499351_01ABR2026_30ABR2026.pdf (extrato de conta corrente de abril 2026).
    Gemini é mockado para falhar, forçando o fallback.
    """
    pytest.importorskip("pdfplumber")
    assert _CA_PDF.exists(), f"PDF não encontrado: {_CA_PDF}"

    pdf_bytes = _CA_PDF.read_bytes()

    from extraction_service import ExtractionService

    svc = ExtractionService()
    with patch.object(svc, "_call_gemini", side_effect=_gemini_always_fails):
        result = svc.extract(pdf_bytes)

    # statement_type deve ser current_account
    assert result.statement_type == "current_account", (
        f"Esperado statement_type='current_account', obtido: {result.statement_type!r}"
    )

    # bank deve ser Nubank
    assert result.bank == "Nubank", (
        f"Esperado bank='Nubank', obtido: {result.bank!r}"
    )

    # period_start deve ser em abril 2026
    assert result.period_start.startswith("2026-04"), (
        f"period_start inválido: {result.period_start!r} (esperado '2026-04-...')"
    )


# ===========================================================================
# Teste 3 — Fluxo completo preview → confirm (cartão de crédito)
# ===========================================================================

def test_full_flow_credit_card(test_db, monkeypatch):
    """Teste 3: Fluxo completo preview → confirm para cartão de crédito.

    Usa Nubank_2026-05-04.pdf com Gemini mockado para retornar JSON válido.
    Verifica que upload_history e transactions_gold são preenchidos corretamente.
    """
    assert _CC_PDF.exists(), f"PDF não encontrado: {_CC_PDF}"

    conn, db_path = test_db

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    # Reload main to pick up the patched DB path
    import main as main_module
    importlib.reload(main_module)

    from fastapi.testclient import TestClient
    client = TestClient(main_module.app)

    pdf_bytes = _CC_PDF.read_bytes()
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Mock Gemini to return valid credit_card JSON
    mock_client = _make_gemini_mock_response("credit_card")

    with patch.object(main_module._extraction_service, "_model", mock_client):
        # Clear cache to force re-extraction
        main_module._extraction_service._cache.clear()

        # Step 1: POST /upload (preview)
        response = client.post(
            "/upload",
            files={"file": ("Nubank_2026-05-04.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"owner": "Victor"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

    assert response.status_code == 200, (
        f"Preview falhou: {response.status_code} {response.text}"
    )

    preview = response.json()
    assert preview["statement_type"] == "credit_card", (
        f"statement_type incorreto no preview: {preview['statement_type']!r}"
    )
    assert preview["bank"], "bank não deve ser vazio no preview"
    assert preview["holder_name"], "holder_name não deve ser vazio no preview"
    assert len(preview["transactions"]) > 0, "Nenhuma transação no preview"

    # Step 2: POST /upload/confirm
    confirmed_transactions = [
        {
            "date": tx["date"],
            "card_last4": tx.get("card_last4"),
            "description": tx["description"],
            "amount": tx["amount"],
            "is_refund": tx["is_refund"],
            "category": tx["suggested_category"],
            "owner": "Victor",
        }
        for tx in preview["transactions"]
    ]

    confirm_body = {
        "file_hash": preview["file_hash"],
        "statement_type": preview["statement_type"],
        "bank": preview["bank"],
        "transactions": confirmed_transactions,
    }

    confirm_response = client.post(
        "/upload/confirm",
        json=confirm_body,
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert confirm_response.status_code == 200, (
        f"Confirm falhou: {confirm_response.status_code} {confirm_response.text}"
    )

    confirm_data = confirm_response.json()
    assert confirm_data["saved_count"] > 0, "Nenhuma transação salva no confirm"

    # Verify upload_history
    c = conn.cursor()
    c.execute(
        "SELECT * FROM upload_history WHERE file_hash = ? ORDER BY created_at DESC LIMIT 1",
        (preview["file_hash"],),
    )
    history_row = c.fetchone()
    assert history_row is not None, "upload_history não foi criado"
    assert dict(history_row)["statement_type"] == "credit_card", (
        f"upload_history.statement_type incorreto: {dict(history_row)['statement_type']!r}"
    )
    assert dict(history_row)["bank"] is not None, "upload_history.bank não deve ser None"

    # Verify transactions_gold has entries
    c.execute(
        "SELECT COUNT(*) as cnt FROM transactions_gold WHERE tenant_id = 'test-tenant'",
    )
    gold_count = c.fetchone()["cnt"]
    assert gold_count > 0, "Nenhuma transação salva em transactions_gold"


# ===========================================================================
# Teste 4 — Fluxo completo preview → confirm (conta corrente)
# ===========================================================================

def test_full_flow_current_account(test_db, monkeypatch):
    """Teste 4: Fluxo completo preview → confirm para conta corrente.

    Usa NU_45499351_01ABR2026_30ABR2026.pdf com Gemini mockado para retornar
    JSON válido de conta corrente. Verifica que current_account_movements é
    preenchido e transactions_gold NÃO é alterado.
    """
    assert _CA_PDF.exists(), f"PDF não encontrado: {_CA_PDF}"

    conn, db_path = test_db

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    import main as main_module
    importlib.reload(main_module)

    from fastapi.testclient import TestClient
    client = TestClient(main_module.app)

    pdf_bytes = _CA_PDF.read_bytes()

    # Mock Gemini to return valid current_account JSON
    mock_client = _make_gemini_mock_response("current_account")

    with patch.object(main_module._extraction_service, "_model", mock_client):
        # Clear cache to force re-extraction
        main_module._extraction_service._cache.clear()

        # Step 1: POST /upload (preview)
        response = client.post(
            "/upload",
            files={"file": ("NU_45499351_01ABR2026_30ABR2026.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"owner": "Victor"},
            headers={"X-Tenant-ID": "test-tenant"},
        )

    assert response.status_code == 200, (
        f"Preview falhou: {response.status_code} {response.text}"
    )

    preview = response.json()
    assert preview["statement_type"] == "current_account", (
        f"statement_type incorreto no preview: {preview['statement_type']!r}"
    )
    assert len(preview["transactions"]) > 0, "Nenhuma transação no preview"

    # Step 2: POST /upload/confirm
    confirmed_transactions = [
        {
            "date": tx["date"],
            "card_last4": tx.get("card_last4"),
            "description": tx["description"],
            "amount": tx["amount"],
            "is_refund": tx["is_refund"],
            "category": tx["suggested_category"],
            "owner": "Victor",
        }
        for tx in preview["transactions"]
    ]

    confirm_body = {
        "file_hash": preview["file_hash"],
        "statement_type": "current_account",
        "bank": preview["bank"],
        "transactions": confirmed_transactions,
    }

    confirm_response = client.post(
        "/upload/confirm",
        json=confirm_body,
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert confirm_response.status_code == 200, (
        f"Confirm falhou: {confirm_response.status_code} {confirm_response.text}"
    )

    confirm_data = confirm_response.json()
    assert confirm_data["saved_count"] > 0, "Nenhuma movimentação salva no confirm"

    # Verify current_account_movements has entries
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) as cnt FROM current_account_movements WHERE tenant_id = 'test-tenant'",
    )
    ca_count = c.fetchone()["cnt"]
    assert ca_count > 0, "Nenhuma movimentação salva em current_account_movements"

    # Verify transactions_gold was NOT altered
    c.execute(
        "SELECT COUNT(*) as cnt FROM transactions_gold WHERE tenant_id = 'test-tenant'",
    )
    gold_count = c.fetchone()["cnt"]
    assert gold_count == 0, (
        f"transactions_gold foi alterado indevidamente: {gold_count} registros "
        f"(esperado 0 para conta corrente)"
    )


# ===========================================================================
# Teste 5 — Classificação de merchant NuTag
# ===========================================================================

def test_classification_nutag_transporte():
    """Teste 5: NuTag deve ser classificado como Transporte com needs_review=False."""
    from categories import ClassificationService

    svc = ClassificationService()
    result = svc.classify("NuTag 0001 Rodovia SP-330", "test")

    assert result.category == "Transporte", (
        f"Esperado category='Transporte', obtido: {result.category!r}"
    )
    assert result.needs_review is False, (
        f"Esperado needs_review=False, obtido: {result.needs_review}"
    )


# ===========================================================================
# Teste 6 — Regressão CSV inalterado
# ===========================================================================

def test_csv_upload_regression(test_db, monkeypatch):
    """Teste 6: Fluxo CSV continua funcionando sem alterações.

    Usa data/fatura_victor_2026-03.csv e verifica que transações são salvas
    em transactions_gold.
    """
    assert _CSV_FILE.exists(), f"CSV não encontrado: {_CSV_FILE}"

    conn, db_path = test_db

    import database
    monkeypatch.setattr(database, "DB_PATH", db_path)

    import main as main_module
    importlib.reload(main_module)

    from fastapi.testclient import TestClient
    client = TestClient(main_module.app)

    csv_bytes = _CSV_FILE.read_bytes()

    # Step 1: POST /upload (preview)
    response = client.post(
        "/upload",
        files={"file": ("fatura_victor_2026-03.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"owner": "Victor", "month_ref": "2026-03"},
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert response.status_code == 200, (
        f"Preview CSV falhou: {response.status_code} {response.text}"
    )

    preview = response.json()
    assert len(preview["transactions"]) > 0, "Nenhuma transação no preview CSV"

    # Step 2: POST /upload/confirm
    confirmed_transactions = [
        {
            "date": tx["date"],
            "card_last4": tx.get("card_last4"),
            "description": tx["description"],
            "amount": tx["amount"],
            "is_refund": tx.get("is_refund", False),
            "category": tx["suggested_category"],
            "owner": "Victor",
        }
        for tx in preview["transactions"]
    ]

    confirm_body = {
        "file_hash": preview["file_hash"],
        "statement_type": "credit_card",
        "bank": "CSV Import",
        "transactions": confirmed_transactions,
    }

    confirm_response = client.post(
        "/upload/confirm",
        json=confirm_body,
        headers={"X-Tenant-ID": "test-tenant"},
    )

    assert confirm_response.status_code == 200, (
        f"Confirm CSV falhou: {confirm_response.status_code} {confirm_response.text}"
    )

    confirm_data = confirm_response.json()
    assert confirm_data["saved_count"] > 0, "Nenhuma transação CSV salva no confirm"

    # Verify transactions_gold has entries
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) as cnt FROM transactions_gold WHERE tenant_id = 'test-tenant'",
    )
    gold_count = c.fetchone()["cnt"]
    assert gold_count > 0, "Nenhuma transação CSV salva em transactions_gold"
