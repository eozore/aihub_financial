"""Unit tests for extraction_service.py — PDF extraction via Gemini + pdfplumber fallback.

Validates Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

import hashlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure the backend directory is on sys.path so bare imports work
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from extraction_service import (
    ExtractedSection,
    ExtractedStatement,
    ExtractedTransaction,
    ExtractionService,
    GEMINI_EXTRACTION_PROMPT,
)


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

def _make_transaction(**overrides) -> dict:
    """Return a valid ExtractedTransaction dict with sensible defaults."""
    defaults = {
        "date": "2026-04-15",
        "card_last4": "4535",
        "description": "UBER *TRIP",
        "amount": 25.50,
        "is_refund": False,
        "is_installment": False,
        "installment_current": None,
        "installment_total": None,
        "original_currency": None,
    }
    defaults.update(overrides)
    return defaults


def _make_section(**overrides) -> dict:
    """Return a valid ExtractedSection dict."""
    defaults = {
        "owner_name": "Victor Zore",
        "subtotal": 150.00,
        "transactions": [_make_transaction()],
    }
    defaults.update(overrides)
    return defaults


def _make_statement(**overrides) -> dict:
    """Return a valid ExtractedStatement dict."""
    defaults = {
        "statement_type": "credit_card",
        "bank": "Nubank",
        "holder_name": "Victor Zore",
        "due_date": "2026-05-04",
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "total_amount": 1500.00,
        "sections": [_make_section()],
    }
    defaults.update(overrides)
    return defaults


def _make_gemini_json_response(**overrides) -> str:
    """Return a JSON string that Gemini would return."""
    return json.dumps(_make_statement(**overrides))


# ---------------------------------------------------------------------------
# Task 9.1 — Pydantic model tests
# ---------------------------------------------------------------------------

class TestExtractedTransaction:
    """Validates: Requirements 5.1, 5.2"""

    def test_create_with_all_fields(self):
        tx = ExtractedTransaction(
            date="2026-04-15",
            card_last4="4535",
            description="UBER *TRIP",
            amount=25.50,
            is_refund=False,
            is_installment=True,
            installment_current=3,
            installment_total=12,
            original_currency="USD",
        )
        assert tx.date == "2026-04-15"
        assert tx.card_last4 == "4535"
        assert tx.description == "UBER *TRIP"
        assert tx.amount == 25.50
        assert tx.is_refund is False
        assert tx.is_installment is True
        assert tx.installment_current == 3
        assert tx.installment_total == 12
        assert tx.original_currency == "USD"

    def test_create_with_defaults(self):
        tx = ExtractedTransaction(
            date="2026-04-15",
            description="MERCADO LIVRE",
            amount=99.90,
        )
        assert tx.card_last4 is None
        assert tx.is_refund is False
        assert tx.is_installment is False
        assert tx.installment_current is None
        assert tx.installment_total is None
        assert tx.original_currency is None

    def test_round_trip_serialize_deserialize(self):
        """Validates: Property 7 — Round-trip schema de extração"""
        tx = ExtractedTransaction(
            date="2026-04-15",
            card_last4="4535",
            description="AMAZON.COM.BR parcela 3/12",
            amount=89.90,
            is_refund=False,
            is_installment=True,
            installment_current=3,
            installment_total=12,
            original_currency=None,
        )
        json_str = tx.model_dump_json()
        restored = ExtractedTransaction.model_validate_json(json_str)
        assert restored == tx

    def test_round_trip_with_all_optional_fields(self):
        tx = ExtractedTransaction(
            date="2026-01-10",
            card_last4=None,
            description="PIX RECEBIDO",
            amount=500.00,
            is_refund=True,
            is_installment=False,
            installment_current=None,
            installment_total=None,
            original_currency=None,
        )
        json_str = tx.model_dump_json()
        restored = ExtractedTransaction.model_validate_json(json_str)
        assert restored == tx


class TestExtractedSection:
    """Validates: Requirements 5.1, 5.7"""

    def test_create_section_with_transactions(self):
        section = ExtractedSection(
            owner_name="Victor Zore",
            subtotal=150.00,
            transactions=[
                ExtractedTransaction(**_make_transaction()),
                ExtractedTransaction(**_make_transaction(description="IFOOD", amount=45.00)),
            ],
        )
        assert section.owner_name == "Victor Zore"
        assert section.subtotal == 150.00
        assert len(section.transactions) == 2

    def test_round_trip_section(self):
        section = ExtractedSection(
            owner_name="Larissa",
            subtotal=200.00,
            transactions=[ExtractedTransaction(**_make_transaction())],
        )
        json_str = section.model_dump_json()
        restored = ExtractedSection.model_validate_json(json_str)
        assert restored == section


class TestExtractedStatement:
    """Validates: Requirements 5.1, 5.2, 5.6"""

    def test_create_credit_card_statement(self):
        stmt = ExtractedStatement(**_make_statement())
        assert stmt.statement_type == "credit_card"
        assert stmt.bank == "Nubank"
        assert stmt.holder_name == "Victor Zore"
        assert stmt.due_date == "2026-05-04"
        assert stmt.period_start == "2026-04-01"
        assert stmt.period_end == "2026-04-30"
        assert stmt.total_amount == 1500.00
        assert len(stmt.sections) == 1

    def test_create_current_account_statement(self):
        stmt = ExtractedStatement(**_make_statement(statement_type="current_account"))
        assert stmt.statement_type == "current_account"

    def test_invalid_statement_type_rejected(self):
        with pytest.raises(Exception):
            ExtractedStatement(**_make_statement(statement_type="savings"))

    def test_due_date_optional(self):
        stmt = ExtractedStatement(**_make_statement(due_date=None))
        assert stmt.due_date is None

    def test_multiple_sections(self):
        """Validates: Requirement 5.7 — multi-holder PDFs"""
        stmt = ExtractedStatement(**_make_statement(
            sections=[
                _make_section(owner_name="Victor Zore", subtotal=800.00),
                _make_section(owner_name="Larissa", subtotal=700.00),
            ]
        ))
        assert len(stmt.sections) == 2
        assert stmt.sections[0].owner_name == "Victor Zore"
        assert stmt.sections[1].owner_name == "Larissa"

    def test_round_trip_full_statement(self):
        """Validates: Property 7 — Round-trip schema de extração"""
        stmt = ExtractedStatement(**_make_statement(
            sections=[
                _make_section(
                    owner_name="Victor",
                    subtotal=100.00,
                    transactions=[
                        _make_transaction(
                            description="NETFLIX",
                            amount=55.90,
                            is_installment=False,
                        ),
                        _make_transaction(
                            description="AMAZON USD",
                            amount=120.00,
                            original_currency="USD",
                            is_installment=True,
                            installment_current=1,
                            installment_total=6,
                        ),
                    ],
                ),
            ]
        ))
        json_str = stmt.model_dump_json()
        restored = ExtractedStatement.model_validate_json(json_str)
        assert restored == stmt

    def test_round_trip_via_dict(self):
        """Serialize to dict and back."""
        stmt = ExtractedStatement(**_make_statement())
        d = stmt.model_dump()
        restored = ExtractedStatement.model_validate(d)
        assert restored == stmt


# ---------------------------------------------------------------------------
# Task 9.2 — ExtractionService: cache + Gemini + retry
# ---------------------------------------------------------------------------

class TestExtractionServiceCache:
    """Validates: Requirement 5.3 — Cache by SHA-256 hash"""

    def test_cache_hit_returns_cached_result(self):
        """Same PDF bytes → same result without calling Gemini again."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = _make_gemini_json_response()
        mock_model.generate_content.return_value = mock_response

        service = ExtractionService(gemini_model=mock_model)
        pdf_bytes = b"fake-pdf-content-for-cache-test"

        # First call — should call Gemini
        result1 = service.extract(pdf_bytes)
        assert mock_model.generate_content.call_count == 1

        # Second call with same bytes — should use cache
        result2 = service.extract(pdf_bytes)
        assert mock_model.generate_content.call_count == 1  # NOT called again
        assert result1 == result2

    def test_different_pdf_not_cached(self):
        """Different PDF bytes → different hash → calls Gemini again."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = _make_gemini_json_response()
        mock_model.generate_content.return_value = mock_response

        service = ExtractionService(gemini_model=mock_model)

        service.extract(b"pdf-content-A")
        service.extract(b"pdf-content-B")

        assert mock_model.generate_content.call_count == 2

    def test_cache_stores_by_sha256_hash(self):
        """Verify the cache key is the SHA-256 hash of the PDF bytes."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = _make_gemini_json_response()
        mock_model.generate_content.return_value = mock_response

        service = ExtractionService(gemini_model=mock_model)
        pdf_bytes = b"test-pdf-bytes"

        service.extract(pdf_bytes)

        expected_hash = hashlib.sha256(pdf_bytes).hexdigest()
        assert expected_hash in service._cache


class TestExtractionServiceGemini:
    """Validates: Requirements 5.1, 5.4, 5.6"""

    def test_gemini_success_on_first_attempt(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = _make_gemini_json_response()
        mock_model.generate_content.return_value = mock_response

        service = ExtractionService(gemini_model=mock_model)
        result = service.extract(b"some-pdf")

        assert isinstance(result, ExtractedStatement)
        assert result.bank == "Nubank"
        assert mock_model.generate_content.call_count == 1

    def test_gemini_strips_markdown_fences(self):
        """Gemini sometimes wraps JSON in ```json ... ``` fences."""
        raw_json = _make_gemini_json_response()
        fenced = f"```json\n{raw_json}\n```"

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = fenced
        mock_model.generate_content.return_value = mock_response

        service = ExtractionService(gemini_model=mock_model)
        result = service.extract(b"pdf-with-fences")

        assert isinstance(result, ExtractedStatement)
        assert result.bank == "Nubank"

    def test_gemini_validates_against_pydantic_schema(self):
        """Invalid JSON from Gemini should trigger retry/fallback."""
        mock_model = MagicMock()
        # Return invalid JSON (missing required fields)
        bad_response = MagicMock()
        bad_response.text = '{"invalid": "data"}'
        mock_model.generate_content.return_value = bad_response

        service = ExtractionService(gemini_model=mock_model)

        # Should fall through to fallback after 3 failed Gemini attempts
        # The fallback will also fail on non-PDF bytes, so we patch it
        with patch.object(service, "_fallback_pdfplumber") as mock_fallback:
            mock_fallback.return_value = ExtractedStatement(**_make_statement())
            result = service.extract(b"some-pdf")

        # Gemini was called 3 times (retries)
        assert mock_model.generate_content.call_count == 3
        # Fallback was called once
        assert mock_fallback.call_count == 1


class TestExtractionServiceRetry:
    """Validates: Requirement 5.4 — Retry with exponential backoff"""

    @patch("extraction_service.time.sleep")
    def test_retry_on_gemini_failure(self, mock_sleep):
        """Gemini fails twice, succeeds on third attempt."""
        mock_model = MagicMock()

        fail_response = MagicMock()
        fail_response.text = "not valid json"

        success_response = MagicMock()
        success_response.text = _make_gemini_json_response()

        mock_model.generate_content.side_effect = [
            Exception("API error"),
            Exception("API error"),
            success_response,
        ]

        service = ExtractionService(gemini_model=mock_model)
        result = service.extract(b"retry-pdf")

        assert isinstance(result, ExtractedStatement)
        assert mock_model.generate_content.call_count == 3
        # Exponential backoff: sleep(1), sleep(2)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2^0 = 1
        mock_sleep.assert_any_call(2)  # 2^1 = 2

    @patch("extraction_service.time.sleep")
    def test_fallback_after_three_failures(self, mock_sleep):
        """All 3 Gemini attempts fail → falls back to pdfplumber."""
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API down")

        service = ExtractionService(gemini_model=mock_model)

        with patch.object(service, "_fallback_pdfplumber") as mock_fallback:
            mock_fallback.return_value = ExtractedStatement(**_make_statement())
            result = service.extract(b"failing-pdf")

        assert mock_model.generate_content.call_count == 3
        assert mock_fallback.call_count == 1
        assert isinstance(result, ExtractedStatement)
        # Backoff sleeps: 1s, 2s (not after the 3rd attempt)
        assert mock_sleep.call_count == 2

    @patch("extraction_service.time.sleep")
    def test_fallback_result_is_cached(self, mock_sleep):
        """Fallback result should also be cached."""
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API down")

        service = ExtractionService(gemini_model=mock_model)
        pdf_bytes = b"fallback-cache-test"

        with patch.object(service, "_fallback_pdfplumber") as mock_fallback:
            mock_fallback.return_value = ExtractedStatement(**_make_statement())
            result1 = service.extract(pdf_bytes)

        # Second call should hit cache
        result2 = service.extract(pdf_bytes)
        assert result1 == result2
        # Gemini should NOT be called again
        assert mock_model.generate_content.call_count == 3  # only from first call


# ---------------------------------------------------------------------------
# Task 9.3 — pdfplumber fallback
# ---------------------------------------------------------------------------

class TestFallbackPdfplumber:
    """Validates: Requirements 5.5, 5.7"""

    def test_fallback_raises_on_empty_pdf(self):
        """Non-PDF bytes should raise ValueError."""
        service = ExtractionService(gemini_model=MagicMock())
        with pytest.raises(Exception):
            service._fallback_pdfplumber(b"not a real pdf")

    def test_parse_brl_amount(self):
        """Brazilian currency parsing: 1.234,56 → 1234.56"""
        service = ExtractionService(gemini_model=MagicMock())
        assert service._parse_brl_amount("1.234,56") == 1234.56
        assert service._parse_brl_amount("99,90") == 99.90
        assert service._parse_brl_amount("1.000.000,00") == 1000000.00
        assert service._parse_brl_amount("0,50") == 0.50
        assert service._parse_brl_amount("25") == 25.0

    def test_parse_pt_date(self):
        """Portuguese date parsing."""
        service = ExtractionService(gemini_model=MagicMock())
        assert service._parse_pt_date("05 ABR 2026") == "2026-04-05"
        assert service._parse_pt_date("15 jan 2026") == "2026-01-15"
        assert service._parse_pt_date("1 dez 2025") == "2025-12-01"
        # Without year, uses ref_year
        assert service._parse_pt_date("10 mar", ref_year="2026") == "2026-03-10"

    def test_extract_transactions_from_text(self):
        """Regex extraction of transaction lines."""
        service = ExtractionService(gemini_model=MagicMock())
        text = (
            "05 ABR   UBER *TRIP              12,50\n"
            "10 ABR   AMAZON.COM.BR parcela 3/12   89,90\n"
            "12 ABR   Estorno IFOOD   45,00\n"
            "15 ABR   BOOKING USD   250,00\n"
        )
        txs = service._extract_transactions_from_text(text, card_last4="4535", ref_year="2026")

        assert len(txs) == 4

        # First transaction
        assert txs[0].date == "2026-04-05"
        assert txs[0].description == "UBER *TRIP"
        assert txs[0].amount == 12.50
        assert txs[0].card_last4 == "4535"
        assert txs[0].is_refund is False

        # Second — installment
        assert txs[1].is_installment is True
        assert txs[1].installment_current == 3
        assert txs[1].installment_total == 12

        # Third — refund
        assert txs[2].is_refund is True

        # Fourth — foreign currency
        assert txs[3].original_currency == "USD"

    def test_extract_sections_multi_holder(self):
        """Validates: Requirement 5.7 — multi-holder section extraction."""
        service = ExtractionService(gemini_model=MagicMock())
        text = (
            "Fatura de cartão de crédito\n"
            "VICTOR ZORE - final 4535\n"
            "05 ABR   UBER *TRIP   12,50\n"
            "10 ABR   NETFLIX   55,90\n"
            "LARISSA SILVA - final 7890\n"
            "08 ABR   IFOOD   45,00\n"
            "12 ABR   SHOPEE   120,00\n"
        )
        sections = service._extract_sections(text)

        assert len(sections) == 2
        assert sections[0].owner_name == "Victor Zore"
        assert len(sections[0].transactions) == 2
        assert sections[1].owner_name == "Larissa Silva"
        assert len(sections[1].transactions) == 2

    def test_extract_sections_returns_empty_when_no_holders(self):
        """When no section headers found, returns empty list."""
        service = ExtractionService(gemini_model=MagicMock())
        text = "Some random text without card holder sections\n05 ABR   UBER   12,50\n"
        sections = service._extract_sections(text)
        assert sections == []

    def test_extract_holder_name(self):
        service = ExtractionService(gemini_model=MagicMock())
        text = "Olá, Victor Zore\nSua fatura de abril"
        assert service._extract_holder_name(text) == "Victor Zore"

    def test_extract_holder_name_fallback(self):
        service = ExtractionService(gemini_model=MagicMock())
        text = "Random header\nNo name here"
        # Should return default
        assert service._extract_holder_name(text) == "Titular"

    def test_extract_due_date(self):
        service = ExtractionService(gemini_model=MagicMock())
        text = "Vencimento: 04 de Maio de 2026\nOutra info"
        result = service._extract_due_date(text)
        assert result == "2026-05-04"

    def test_extract_due_date_slash_format(self):
        service = ExtractionService(gemini_model=MagicMock())
        text = "Vencimento: 04/05/2026\nOutra info"
        result = service._extract_due_date(text)
        assert result == "2026-05-04"

    def test_extract_due_date_not_found(self):
        service = ExtractionService(gemini_model=MagicMock())
        text = "No due date info here"
        assert service._extract_due_date(text) is None

    def test_extract_total_amount(self):
        service = ExtractionService(gemini_model=MagicMock())
        text = "Total da fatura: R$ 1.500,00\nOutra info"
        assert service._extract_total_amount(text) == 1500.00

    def test_extract_period(self):
        service = ExtractionService(gemini_model=MagicMock())
        text = "Período: 01 Abr 2026 a 30 Abr 2026\n"
        start, end = service._extract_period(text)
        assert start == "2026-04-01"
        assert end == "2026-04-30"


# ---------------------------------------------------------------------------
# Gemini prompt content
# ---------------------------------------------------------------------------

class TestGeminiPrompt:
    """Validates: Requirement 5.6 — structured prompt with JSON schema"""

    def test_prompt_requests_json_schema(self):
        assert "statement_type" in GEMINI_EXTRACTION_PROMPT
        assert "bank" in GEMINI_EXTRACTION_PROMPT
        assert "holder_name" in GEMINI_EXTRACTION_PROMPT
        assert "transactions" in GEMINI_EXTRACTION_PROMPT
        assert "card_last4" in GEMINI_EXTRACTION_PROMPT
        assert "is_refund" in GEMINI_EXTRACTION_PROMPT
        assert "is_installment" in GEMINI_EXTRACTION_PROMPT
        assert "original_currency" in GEMINI_EXTRACTION_PROMPT

    def test_prompt_specifies_json_only(self):
        assert "ONLY the JSON" in GEMINI_EXTRACTION_PROMPT

    def test_prompt_handles_installments(self):
        assert "parcela" in GEMINI_EXTRACTION_PROMPT

    def test_prompt_handles_multiple_holders(self):
        assert "multiple card holders" in GEMINI_EXTRACTION_PROMPT

    def test_prompt_handles_foreign_currency(self):
        assert "foreign currency" in GEMINI_EXTRACTION_PROMPT
