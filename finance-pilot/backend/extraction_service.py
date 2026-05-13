"""Extraction Service — PDF statement extraction via Gemini Flash 2.5 with fallback.

Implements a 3-stage pipeline:
  1. In-memory cache lookup by SHA-256 hash of the PDF bytes
  2. Gemini Flash 2.5 structured extraction with retry + exponential backoff
  3. Fallback: pdfplumber + regex parser for Nubank credit card statements

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Literal, Optional

import pdfplumber
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("finance-pilot")


# ---------------------------------------------------------------------------
# Pydantic models — Task 9.1
# ---------------------------------------------------------------------------

class ExtractedTransaction(BaseModel):
    """A single transaction extracted from a bank statement."""
    date: str  # YYYY-MM-DD
    card_last4: Optional[str] = None
    description: str
    amount: float
    is_refund: bool = False
    is_installment: bool = False
    installment_current: Optional[int] = None
    installment_total: Optional[int] = None
    original_currency: Optional[str] = None


class ExtractedSection(BaseModel):
    """A section of transactions grouped by card holder / owner."""
    owner_name: str
    subtotal: float
    transactions: list[ExtractedTransaction]


class ExtractedStatement(BaseModel):
    """Top-level extraction result for a bank statement PDF."""
    statement_type: Literal["credit_card", "current_account"]
    bank: str
    holder_name: str
    due_date: Optional[str] = None
    period_start: str
    period_end: str
    total_amount: float
    sections: list[ExtractedSection]


# ---------------------------------------------------------------------------
# Raw (free-form) Pydantic models — Stage 1 output
# ---------------------------------------------------------------------------

class RawTransaction(BaseModel):
    """A transaction as returned by the free-form Gemini prompt (Stage 1)."""
    model_config = ConfigDict(extra="allow")
    date: Optional[str] = None
    description: Optional[str] = None
    card_last_digits: Optional[str] = None
    amount: Optional[float] = None


# ---------------------------------------------------------------------------
# Gemini prompts
# ---------------------------------------------------------------------------

# Stage 1 — simple free-form prompt that lets Gemini return its natural structure.
GEMINI_RAW_PROMPT = """\
Identify all fields of this bank statement document and return them as a structured JSON.
Include: document info (bank, customer name, dates, totals), summary section, limits,
future invoices if present, and ALL transactions with their dates, descriptions, amounts,
and card last digits when visible.
Return ONLY the JSON object, no markdown fences, no explanation.
"""

# Stage 2 (legacy) — strict schema prompt kept for the pdfplumber fallback path.
GEMINI_EXTRACTION_PROMPT = """\
You are a financial document parser specialized in Brazilian bank statements (Nubank).
Extract ONLY real purchase/expense transactions from the attached bank statement PDF
and return a single JSON object following the schema below.

IMPORTANT RULES FOR NUBANK STATEMENTS:

1. DETECT statement_type from content:
   - Presence of "fatura", "cartão", "vencimento", "limite", "parcela" → "credit_card"
   - Presence of "conta corrente", "extrato", "saldo anterior", "saldo final",
     "pix enviado", "pix recebido" → "current_account"

2. CREDIT CARD statements (fatura):
   - Dates are in Portuguese format: "05 ABR" or "05 ABR 2026"
   - Amounts are in BRL format: "1.234,56" (dot = thousands, comma = decimal)
   - Create ONE section per card holder. The primary holder has no suffix;
     additional cards show "NOME - final XXXX".
   - CRITICAL — card_last4: Each section header contains the last 4 digits of the card
     (e.g. "VICTOR ZORÉ - final 4535" → card_last4="4535"). You MUST set card_last4
     on EVERY transaction in that section to those 4 digits. If the primary holder
     section has no "final XXXX" suffix, look for the card number elsewhere in the
     document header or set card_last4=null only if truly not found.
   - EXCLUDE the following lines — they are NOT real transactions:
     * "Pagamento em DD MMM" or "Pagamento recebido" — these are bill payments, not purchases
     * "Saldo restante da fatura anterior" — this is a balance carry-over line
     * "Limite" lines — these are credit limit information
     * "Total de compras" or "Total a pagar" — these are summary lines
     * Any line with a NEGATIVE amount that starts with "Pagamento" — bill payment
   - INCLUDE refunds/estornos: lines with "Estorno de" or negative amounts that are
     actual merchant refunds should be included with is_refund=true.

3. CURRENT ACCOUNT statements (extrato conta corrente):
   - Create ONE section with owner_name = holder_name.
   - Include ALL movements EXCEPT:
     * "Pagamento de fatura" — this is a credit card bill payment, not an expense
     * "Saldo inicial" / "Saldo final" — these are balance lines, not transactions
   - is_refund=false for DEBITS (money going OUT: PIX enviado, pagamentos, boletos).
   - is_refund=true for CREDITS (money coming IN: PIX recebido, salário, transferências recebidas).
   - amount is ALWAYS the absolute positive value.

4. holder_name: extract the primary account holder's full name from the document.

5. period_start / period_end: derive from the actual transaction dates if not
   explicitly stated. Format: YYYY-MM-DD.

6. Return ONLY the JSON object, no markdown fences, no explanation.

EXAMPLES OF EXPECTED OUTPUT:

Example 1 — Credit card section "VICTOR ZORÉ - final 4535" with transaction "05 ABR  UBER *TRIP  12,50":
  {{"date": "2026-04-05", "description": "UBER *TRIP", "amount": 12.50, "is_refund": false, "card_last4": "4535"}}

Example 2 — Credit card primary holder section (no "final XXXX") with transaction "28 MAR  NETFLIX  55,90":
  {{"date": "2026-03-28", "description": "NETFLIX", "amount": 55.90, "is_refund": false, "card_last4": "2456"}}
  (use the card number found in the document header for the primary holder)

Example 3 — EXCLUDE this line: "06 ABR  Pagamento em 06 ABR  −1.500,00" → DO NOT include

Example 4 — EXCLUDE this line: "Saldo restante da fatura anterior  R$ 0,00" → DO NOT include

Example 5 — INCLUDE refund: "10 ABR  Estorno de UBER *TRIP  −12,50" → {{"is_refund": true, "amount": 12.50}}

Example 6 — Installment "10 ABR  AMAZON.COM.BR  parcela 3/12  89,90":
  {{"date": "2026-04-10", "description": "AMAZON.COM.BR", "amount": 89.90, "is_refund": false,
    "is_installment": true, "installment_current": 3, "installment_total": 12, "card_last4": "2456"}}

Example 7 — Current account debit "PIX enviado - João  -150,00":
  {{"date": "2026-04-05", "description": "PIX enviado - João", "amount": 150.00, "is_refund": false}}

Example 8 — Current account credit "PIX recebido - Empresa  +3.500,00":
  {{"date": "2026-04-05", "description": "PIX recebido - Empresa", "amount": 3500.00, "is_refund": true}}

JSON SCHEMA:
{{
  "statement_type": "credit_card" or "current_account",
  "bank": "<bank name, e.g. Nubank>",
  "holder_name": "<primary account holder full name>",
  "due_date": "<YYYY-MM-DD or null>",
  "period_start": "<YYYY-MM-DD>",
  "period_end": "<YYYY-MM-DD>",
  "total_amount": <float, total amount of real purchases only>,
  "sections": [
    {{
      "owner_name": "<card holder name for this section>",
      "subtotal": <float, section subtotal of real purchases>,
      "transactions": [
        {{
          "date": "<YYYY-MM-DD>",
          "card_last4": "<last 4 digits of card — REQUIRED for credit card, propagate from section header>",
          "description": "<merchant / transaction description>",
          "amount": <float, always positive>,
          "is_refund": <bool>,
          "is_installment": <bool>,
          "installment_current": <int or null>,
          "installment_total": <int or null>,
          "original_currency": "<ISO currency code or null>"
        }}
      ]
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# ExtractionService — Tasks 9.2 & 9.3
# ---------------------------------------------------------------------------

class ExtractionService:
    """Extracts transactions from PDF statements using Gemini Flash 2.5 with cache and fallback."""

    def __init__(self, gemini_model=None):
        self._cache: dict[str, ExtractedStatement] = {}
        self._raw_cache: dict[str, dict] = {}  # Stage 1 raw Gemini JSON keyed by file_hash
        self._model = gemini_model  # Lazy-init if None

    def _get_model(self):
        """Lazy-initialise the Gemini client via Vertex AI on first use.

        Uses google-genai SDK with vertexai=True, which authenticates via
        GCP Application Default Credentials (service account on Cloud Run).
        Project and location are read from environment variables with sensible
        defaults matching the ainewz-platform pattern.
        """
        if self._model is None:
            import os
            from google import genai
            project = os.environ.get("PROJECT_ID", "aifin-project")
            location = os.environ.get("GEMINI_LOCATION", "us-central1")
            self._model = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pdf_bytes: bytes) -> ExtractedStatement:
        """Pipeline: cache → Gemini 2-stage (3 retries with exponential backoff) → pdfplumber fallback.

        Stage 1: Call Gemini with a simple free-form prompt → raw JSON dict.
        Stage 2: Convert raw dict → ExtractedStatement via _parse_raw_to_extracted().
        The raw dict is stored in self._raw_cache for the caller to retrieve via get_raw().
        """
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # 1. Cache lookup
        if file_hash in self._cache:
            logger.info("Cache hit for PDF hash %s", file_hash[:12])
            return self._cache[file_hash]

        # 2. Gemini 2-stage extraction with retry
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                # Stage 1: free-form extraction
                raw_json_str = self._call_gemini(pdf_bytes, prompt=GEMINI_EXTRACTION_PROMPT)

                # Safety net: strip markdown fences if present (should not occur
                # with response_mime_type="application/json", but handles edge cases)
                if raw_json_str.startswith("```"):
                    lines = raw_json_str.split("\n")
                    # Remove only the first and last lines if they are fence markers
                    if lines[0].strip().startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip().startswith("```"):
                        lines = lines[:-1]
                    raw_json_str = "\n".join(lines).strip()

                raw_dict = json.loads(raw_json_str)

                # Try direct schema validation first (handles well-structured responses)
                try:
                    from pydantic import ValidationError
                    validated = ExtractedStatement.model_validate(raw_dict)
                    if validated.sections and any(
                        len(s.transactions) > 0 for s in validated.sections
                    ):
                        # Direct validation succeeded with non-empty transactions
                        self._raw_cache[file_hash] = raw_dict
                        self._cache[file_hash] = validated
                        logger.info("Gemini direct validation succeeded on attempt %d", attempt + 1)
                        return validated
                except (ValidationError, Exception):
                    pass  # Fall through to heuristic parser

                # Stage 2: convert to internal schema via heuristic parser
                validated = self._parse_raw_to_extracted(raw_dict)

                # Reject semantically empty results so the retry loop can try again
                if not validated.sections or not any(
                    len(s.transactions) > 0 for s in validated.sections
                ):
                    raise ValueError(
                        f"Gemini returned empty transactions "
                        f"(statement_type={validated.statement_type})"
                    )

                self._raw_cache[file_hash] = raw_dict
                self._cache[file_hash] = validated
                logger.info("Gemini 2-stage extraction succeeded on attempt %d", attempt + 1)
                return validated
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 2 ** attempt  # 1s, 2s
                    logger.warning(
                        "Gemini attempt %d failed (%s), retrying in %ds…",
                        attempt + 1, e, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.warning(
                        "Gemini failed after 3 attempts: %s", e,
                    )

        # 3. Fallback: pdfplumber + regex
        logger.info("Falling back to pdfplumber extraction")
        result = self._fallback_pdfplumber(pdf_bytes)
        self._cache[file_hash] = result
        return result

    def get_raw(self, file_hash: str) -> Optional[dict]:
        """Return the cached raw Gemini JSON dict for the given file hash, or None."""
        return self._raw_cache.get(file_hash)

    # ------------------------------------------------------------------
    # Gemini extraction — Task 9.2
    # ------------------------------------------------------------------

    def _call_gemini(self, pdf_bytes: bytes, prompt: str = GEMINI_RAW_PROMPT) -> str:
        """Send PDF to Gemini via Vertex AI with the given prompt, returning raw text."""
        from google.genai import types
        import os

        client = self._get_model()
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=65535,
                temperature=0,
                response_mime_type="application/json",
            ),
        )

        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        return raw_text

    # ------------------------------------------------------------------
    # Stage 2: convert free-form Gemini JSON → ExtractedStatement
    # ------------------------------------------------------------------

    def _parse_raw_to_extracted(self, raw_dict: dict) -> ExtractedStatement:
        """Convert the free-form Gemini JSON (Stage 1) into an ExtractedStatement.

        Handles both credit card and current account PDFs.  The raw_dict may
        have any structure Gemini chose; this method is defensive throughout.
        """
        import datetime

        # ---- Detect statement type ----------------------------------------
        raw_str = json.dumps(raw_dict, ensure_ascii=False).lower()
        cc_signals = ["fatura", "cartão", "vencimento", "limite", "parcela", "invoice"]
        ca_signals = ["conta corrente", "extrato", "saldo anterior", "saldo final",
                      "pix enviado", "pix recebido", "current account"]
        cc_score = sum(1 for s in cc_signals if s in raw_str)
        ca_score = sum(1 for s in ca_signals if s in raw_str)
        statement_type: Literal["credit_card", "current_account"] = (
            "current_account" if ca_score > cc_score else "credit_card"
        )

        # ---- document_info helpers ----------------------------------------
        doc_info: dict = raw_dict.get("document_info", {})
        summary: dict = raw_dict.get("summary", {})

        # bank
        bank: str = (
            doc_info.get("bank")
            or raw_dict.get("bank")
            or "Nubank"
        )

        # holder_name
        holder_name: str = (
            doc_info.get("customer_name")
            or doc_info.get("holder_name")
            or raw_dict.get("holder_name")
            or "Unknown"
        )

        # ---- Billing year (used to expand "DD MMM" dates) -----------------
        billing_year: str = "2026"
        due_date_raw: str = (
            doc_info.get("due_date")
            or doc_info.get("vencimento")
            or ""
        )
        due_date_iso: Optional[str] = None
        if due_date_raw:
            parsed_due = self._parse_pt_date(due_date_raw)
            if len(parsed_due) == 10:
                due_date_iso = parsed_due
                billing_year = parsed_due[:4]

        # ---- total_amount: prefer total_purchases over total_to_pay -------
        # Priority: summary.total_purchases > summary.total_to_pay > doc_info.invoice_total
        # NEVER use future_invoices.outstanding_balance (that's a different thing)
        total_amount: float = 0.0
        _total_candidates = [
            summary.get("total_purchases"),
            summary.get("total_compras"),
            summary.get("total_purchases_brl"),
            summary.get("total_to_pay"),
            doc_info.get("invoice_total"),
            raw_dict.get("total_amount"),
        ]
        for candidate in _total_candidates:
            if candidate is not None:
                try:
                    val = float(candidate)
                    if val > 0:
                        total_amount = val
                        break
                except (TypeError, ValueError):
                    continue

        # ---- Transactions -------------------------------------------------
        raw_transactions: list[dict] = raw_dict.get("transactions", [])

        # Search for transactions at multiple nesting levels if top-level is empty
        if not raw_transactions:
            # Try inside "sections"
            for section in raw_dict.get("sections", []):
                if isinstance(section, dict):
                    txns = section.get("transactions", [])
                    if txns:
                        raw_transactions.extend(txns)
            # Try inside "card_holders"
            if not raw_transactions:
                for holder in raw_dict.get("card_holders", []):
                    if isinstance(holder, dict):
                        txns = holder.get("transactions", [])
                        if txns:
                            raw_transactions.extend(txns)
            # Try "movements"
            if not raw_transactions:
                raw_transactions = raw_dict.get("movements", [])

        # Exclusion keywords for bill payments / summary lines
        _EXCLUDE_PATTERNS = [
            r"pagamento\s+em\b",
            r"pagamento\s+recebido",
            r"saldo\s+restante",
            r"^limite\b",
            r"total\s+de\s+compras",
            r"total\s+a\s+pagar",
            r"total\s+de\s+saídas",
            r"total\s+de\s+entradas",
        ]
        _EXCLUDE_RE = re.compile("|".join(_EXCLUDE_PATTERNS), re.IGNORECASE)

        # Group transactions by card_last_digits for credit card sections
        sections_map: dict[str, list[ExtractedTransaction]] = {}

        for raw_tx in raw_transactions:
            if not isinstance(raw_tx, dict):
                continue

            description: str = str(
                raw_tx.get("description")
                or raw_tx.get("descricao")
                or raw_tx.get("merchant")
                or raw_tx.get("name")
                or ""
            ).strip()
            if not description:
                continue

            # Exclude bill payments and summary lines
            if _EXCLUDE_RE.search(description):
                continue

            amount_raw = (
                raw_tx.get("amount")
                if raw_tx.get("amount") is not None
                else raw_tx.get("value")
                if raw_tx.get("value") is not None
                else raw_tx.get("valor")
                if raw_tx.get("valor") is not None
                else raw_tx.get("total")
            )
            try:
                amount_val = float(amount_raw) if amount_raw is not None else 0.0
            except (TypeError, ValueError):
                amount_val = 0.0

            # Exclude very large negative amounts (bill payments)
            if amount_val < -500:
                continue

            # is_refund: negative amounts that are NOT bill payments
            is_refund = amount_val < 0
            amount_abs = abs(amount_val)

            # Parse date
            date_raw: str = str(
                raw_tx.get("date")
                or raw_tx.get("data")
                or raw_tx.get("transaction_date")
                or ""
            ).strip()
            date_iso: str = self._parse_pt_date(date_raw, ref_year=billing_year)
            if not date_iso or len(date_iso) < 8:
                date_iso = f"{billing_year}-01-01"

            # card_last_digits — Gemini may use "card_last_digits", "card_last4", or "card"
            card_last4: Optional[str] = None
            for _card_key in ("card_last_digits", "card_last4", "card_last_4", "card"):
                _card_val = raw_tx.get(_card_key)
                if _card_val is not None:
                    _card_str = str(_card_val).strip()
                    if _card_str and _card_str != "None" and len(_card_str) <= 4:
                        card_last4 = _card_str
                        break

            # Installments: detect "Parcela X/Y" in description
            is_installment = False
            installment_current: Optional[int] = None
            installment_total: Optional[int] = None
            inst_m = re.search(r"[Pp]arcela\s+(\d{1,2})/(\d{1,2})", description)
            if inst_m:
                is_installment = True
                installment_current = int(inst_m.group(1))
                installment_total = int(inst_m.group(2))

            tx = ExtractedTransaction(
                date=date_iso,
                card_last4=card_last4,
                description=description,
                amount=amount_abs,
                is_refund=is_refund,
                is_installment=is_installment,
                installment_current=installment_current,
                installment_total=installment_total,
            )

            section_key = card_last4 or "__primary__"
            sections_map.setdefault(section_key, []).append(tx)

        # ---- Build sections -----------------------------------------------
        sections: list[ExtractedSection] = []
        for key, txns in sections_map.items():
            subtotal = sum(
                t.amount if not t.is_refund else -t.amount for t in txns
            )
            owner = holder_name if key == "__primary__" else f"Card *{key}"
            sections.append(ExtractedSection(
                owner_name=owner,
                subtotal=round(subtotal, 2),
                transactions=txns,
            ))

        # If no sections were built, create an empty primary section
        if not sections:
            sections = [ExtractedSection(
                owner_name=holder_name,
                subtotal=0.0,
                transactions=[],
            )]

        # ---- period_start / period_end ------------------------------------
        billing_period: dict = doc_info.get("billing_period", {})
        period_start_iso: str = ""
        period_end_iso: str = ""

        if billing_period:
            start_raw = billing_period.get("start", "")
            end_raw = billing_period.get("end", "")
            if start_raw:
                period_start_iso = self._parse_pt_date(str(start_raw), ref_year=billing_year)
            if end_raw:
                period_end_iso = self._parse_pt_date(str(end_raw), ref_year=billing_year)

        # Fallback: derive from transaction dates
        if not period_start_iso or not period_end_iso:
            all_dates = [
                t.date for s in sections for t in s.transactions
                if t.date and len(t.date) == 10
            ]
            if all_dates:
                period_start_iso = period_start_iso or min(all_dates)
                period_end_iso = period_end_iso or max(all_dates)

        # Last resort: use current month
        if not period_start_iso or not period_end_iso:
            today = datetime.date.today()
            period_start_iso = period_start_iso or today.replace(day=1).isoformat()
            period_end_iso = period_end_iso or today.isoformat()

        return ExtractedStatement(
            statement_type=statement_type,
            bank=bank,
            holder_name=holder_name,
            due_date=due_date_iso,
            period_start=period_start_iso,
            period_end=period_end_iso,
            total_amount=round(total_amount, 2),
            sections=sections,
        )

    # ------------------------------------------------------------------
    # pdfplumber fallback for Nubank — Task 9.3
    # ------------------------------------------------------------------

    def _detect_statement_type(self, text: str) -> Literal["credit_card", "current_account"]:
        """Detect whether a PDF is a credit card statement or current account statement.

        Scores the text against known signal words for each type and returns
        the winner. Ties default to "credit_card" (conservative).
        """
        text_lower = text.lower()
        cc_signals = ["fatura", "cartão", "vencimento", "limite", "parcela"]
        ca_signals = ["conta corrente", "extrato", "saldo anterior", "saldo final", "pix enviado", "pix recebido"]
        cc_score = sum(1 for s in cc_signals if s in text_lower)
        ca_score = sum(1 for s in ca_signals if s in text_lower)
        return "current_account" if ca_score > cc_score else "credit_card"

    def _parse_ddmmyyyy(self, date_str: str) -> str:
        """Convert DD/MM/YYYY to YYYY-MM-DD."""
        parts = date_str.strip().split("/")
        if len(parts) == 3:
            day, month, year = parts
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return date_str

    def _fallback_pdfplumber(self, pdf_bytes: bytes) -> ExtractedStatement:
        """Parse Nubank statements using pdfplumber + regex.

        Detects the statement type dynamically and delegates to the appropriate
        parser: credit card or current account.
        """
        import io

        full_text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"

        if not full_text.strip():
            raise ValueError("Could not extract any text from PDF")

        statement_type = self._detect_statement_type(full_text)

        if statement_type == "current_account":
            return self._fallback_pdfplumber_current_account(full_text)
        else:
            return self._fallback_pdfplumber_credit_card(full_text)

    def _fallback_pdfplumber_credit_card(self, full_text: str) -> ExtractedStatement:
        """Parse Nubank credit card statements using pdfplumber text + regex."""
        # --- Extract statement metadata ---
        holder_name = self._extract_holder_name(full_text)
        due_date = self._extract_due_date(full_text)

        # --- Extract sections (by card holder) ---
        sections = self._extract_sections(full_text)

        # If no sections found, create a single section with all transactions
        if not sections:
            transactions = self._extract_transactions_from_text(full_text)
            total_amount = self._extract_total_amount(full_text)
            sections = [
                ExtractedSection(
                    owner_name=holder_name,
                    subtotal=total_amount,
                    transactions=transactions,
                )
            ]

        # Derive period from extracted transactions (5.4 fix)
        all_transactions = [t for s in sections for t in s.transactions]
        period_start, period_end = self._extract_period(full_text, transactions=all_transactions)
        total_amount = self._extract_total_amount(full_text)

        return ExtractedStatement(
            statement_type="credit_card",
            bank="Nubank",
            holder_name=holder_name,
            due_date=due_date,
            period_start=period_start,
            period_end=period_end,
            total_amount=total_amount,
            sections=sections,
        )

    def _fallback_pdfplumber_current_account(self, full_text: str) -> ExtractedStatement:
        """Parse Nubank current account statements using pdfplumber + regex.

        Handles two date formats:
        1. DD/MM/YYYY  DESCRIPTION  [+-]AMOUNT  (generic format)
        2. DD MMM YYYY  (Nubank extrato format, e.g. "01 ABR 2026")
           followed by individual transaction lines like:
           "Transferência enviada pelo Pix NOME  150,00"
        """
        import datetime

        holder_name = self._extract_holder_name(full_text)

        # Pattern: DD/MM/YYYY  DESCRIPTION  [+-]AMOUNT
        ca_pattern = re.compile(
            r"(\d{2}/\d{2}/\d{4})\s+"
            r"(.+?)\s{2,}"
            r"([+-]?\s*[\d.,]+)\s*$",
            re.MULTILINE,
        )
        # Alternative pattern with less strict spacing
        ca_pattern_alt = re.compile(
            r"(\d{2}/\d{2}/\d{4})\s+"
            r"(.+?)\s+"
            r"([+-]?[\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*$",
            re.MULTILINE,
        )

        transactions = []
        seen: set[tuple[str, str]] = set()

        for pattern in (ca_pattern, ca_pattern_alt):
            for m in pattern.finditer(full_text):
                key = (m.group(1), m.group(3).strip())
                if key in seen:
                    continue
                seen.add(key)

                date_str, description, amount_str = m.groups()
                date_iso = self._parse_ddmmyyyy(date_str)
                amount_clean = amount_str.replace("+", "").strip()
                amount_raw = self._parse_brl_amount(amount_clean)
                is_credit = "+" in amount_str or (amount_raw > 0 and "-" not in amount_str)

                transactions.append(ExtractedTransaction(
                    date=date_iso,
                    description=description.strip(),
                    amount=abs(amount_raw),
                    # is_refund=False for DEBITS (money out), is_refund=True for CREDITS (money in)
                    is_refund=is_credit,
                ))
            if transactions:
                break

        # Nubank extrato format: "DD MMM YYYY" date headers followed by transaction lines
        # e.g. "01 ABR 2026 Total de saídas - 15,00"
        # and  "Transferência enviada pelo Pix NOME  150,00"
        if not transactions:
            transactions = self._parse_nubank_extrato_format(full_text)

        dates = [t.date for t in transactions if t.date and len(t.date) == 10]
        period_start = min(dates) if dates else datetime.date.today().replace(day=1).isoformat()
        period_end = max(dates) if dates else datetime.date.today().isoformat()
        total = sum(t.amount for t in transactions if not t.is_refund)

        return ExtractedStatement(
            statement_type="current_account",
            bank="Nubank",
            holder_name=holder_name,
            period_start=period_start,
            period_end=period_end,
            total_amount=round(total, 2),
            sections=[ExtractedSection(
                owner_name=holder_name,
                subtotal=round(total, 2),
                transactions=transactions,
            )],
        )

    # ------------------------------------------------------------------
    # Nubank-specific helpers
    # ------------------------------------------------------------------

    def _parse_nubank_extrato_format(self, full_text: str) -> list:
        """Parse Nubank current account extrato format.

        The Nubank extrato PDF uses date headers like "01 ABR 2026" followed by
        individual transaction lines. Each transaction line has a description and
        an amount at the end.

        Example:
            01 ABR 2026 Total de saídas - 15,00
            Transferência enviada pelo Pix NOME - BANK  15,00
            02 ABR 2026 Total de saídas - 1.000,00
            Transferência enviada pelo Pix NOME - BANK  600,00
            ...
        """
        transactions = []
        seen: set[tuple[str, str]] = set()

        # Match date headers: "DD MMM YYYY Total de [entradas/saídas] [+/-] AMOUNT"
        date_header_pattern = re.compile(
            r"^(\d{1,2})\s+([A-Za-zÀ-ú]{3})\s+(\d{4})\s+Total de (entradas|saídas)\s*[+-]?\s*([\d.,]+)",
            re.MULTILINE | re.IGNORECASE,
        )

        # Match individual transaction lines (description + amount at end of line)
        # These appear after a date header and before the next date header
        tx_line_pattern = re.compile(
            r"^(.+?)\s+([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*$",
            re.MULTILINE,
        )

        # Find all date headers and their positions
        date_headers = list(date_header_pattern.finditer(full_text))

        for i, header_match in enumerate(date_headers):
            day = header_match.group(1)
            month_abbr = header_match.group(2)
            year = header_match.group(3)
            movement_type = header_match.group(4).lower()  # "entradas" or "saídas"

            date_iso = self._parse_pt_date(f"{day} {month_abbr} {year}")

            # Text between this header and the next (or end of text)
            start_pos = header_match.end()
            end_pos = date_headers[i + 1].start() if i + 1 < len(date_headers) else len(full_text)
            block_text = full_text[start_pos:end_pos]

            # Extract individual transactions from this block
            for tx_match in tx_line_pattern.finditer(block_text):
                description = tx_match.group(1).strip()
                amount_str = tx_match.group(2).strip()

                # Skip summary/header lines
                skip_keywords = [
                    "total de", "saldo", "rendimento", "valores em",
                    "tem alguma dúvida", "atendimento", "extrato gerado",
                    "agência", "conta:", "cpf", "nubank",
                ]
                if any(kw in description.lower() for kw in skip_keywords):
                    continue

                # Skip very short descriptions (likely noise)
                if len(description) < 5:
                    continue

                amount = self._parse_brl_amount(amount_str)
                if amount <= 0:
                    continue

                key = (date_iso, description[:40], amount_str)
                if key in seen:
                    continue
                seen.add(key)

                # is_refund=True for CREDITS (entradas), False for DEBITS (saídas)
                is_credit = movement_type == "entradas"

                transactions.append(ExtractedTransaction(
                    date=date_iso,
                    description=description,
                    amount=amount,
                    is_refund=is_credit,
                ))

        return transactions

    # Month name → number mapping for Portuguese dates
    _MONTH_MAP: dict[str, str] = {
        "jan": "01", "fev": "02", "mar": "03", "abr": "04",
        "mai": "05", "jun": "06", "jul": "07", "ago": "08",
        "set": "09", "out": "10", "nov": "11", "dez": "12",
    }

    def _parse_pt_date(self, date_str: str, ref_year: str = "") -> str:
        """Convert Portuguese date like '05 ABR' or '05 ABR 2026' to YYYY-MM-DD."""
        date_str = date_str.strip().lower()

        # Try DD MMM YYYY
        m = re.match(r"(\d{1,2})\s+([a-zç]{3})\s+(\d{4})", date_str)
        if m:
            day, month_abbr, year = m.groups()
            month_num = self._MONTH_MAP.get(month_abbr[:3], "01")
            return f"{year}-{month_num}-{day.zfill(2)}"

        # Try DD MMM (use ref_year)
        m = re.match(r"(\d{1,2})\s+([a-zç]{3})", date_str)
        if m:
            day, month_abbr = m.groups()
            month_num = self._MONTH_MAP.get(month_abbr[:3], "01")
            year = ref_year or "2026"
            return f"{year}-{month_num}-{day.zfill(2)}"

        return date_str

    def _extract_holder_name(self, text: str) -> str:
        """Extract the primary holder name from Nubank statement.

        Tries multiple regex patterns in order of specificity, then falls back
        to scanning the first 20 lines for a capitalized name pattern.
        Returns "Nubank" as a safe fallback (not "Titular" which is ambiguous).
        """
        patterns = [
            r"(?:Olá|Oi),?[^\S\n]+([A-ZÀ-Ú][a-zà-ú]+(?:[ ]+[A-ZÀ-Ú][a-zà-ú]+)+)",
            r"(?:Olá|Oi|Fatura\s+de)\s*,?[^\S\n]*([A-ZÀ-Ú][a-zà-ú]+(?:[ ]+[A-ZÀ-Ú][a-zà-ú]+)*)",
            r"Fatura\s+de[^\S\n]+([A-ZÀ-Ú][a-zà-ú]+(?:[ ]+[A-ZÀ-Ú][a-zà-ú]+)+)",
            r"Titular[:\s]+([A-ZÀ-Ú][a-zà-ú]+(?:[ ]+[A-ZÀ-Ú][a-zà-ú]+)+)",
            r"^([A-ZÀ-Ú]{2,}(?:[ ]+[A-ZÀ-Ú]{2,})+)\s*$",  # ALL CAPS name
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.MULTILINE)
            if m:
                return m.group(1).strip().title()

        # Fallback: look for a name pattern in the first few lines
        lines = text.split("\n")[:20]
        for line in lines:
            # Match capitalized names (at least 2 words)
            m = re.match(r"^([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)+)\s*$", line.strip())
            if m:
                return m.group(1).strip()

        return "Nubank"  # safe fallback (not "Titular" which is ambiguous)

    def _extract_due_date(self, text: str) -> Optional[str]:
        """Extract due date from Nubank statement."""
        # Pattern: "Vencimento" or "vencimento" followed by a date
        m = re.search(
            r"[Vv]encimento\s*:?\s*(\d{1,2})\s+(?:de\s+)?([A-Za-zÀ-ú]{3})\w*\s+(?:de\s+)?(\d{4})",
            text,
        )
        if m:
            day, month_abbr, year = m.groups()
            month_num = self._MONTH_MAP.get(month_abbr[:3].lower(), "01")
            return f"{year}-{month_num}-{day.zfill(2)}"

        # Try DD/MM/YYYY pattern
        m = re.search(r"[Vv]encimento\s*:?\s*(\d{2})/(\d{2})/(\d{4})", text)
        if m:
            day, month, year = m.groups()
            return f"{year}-{month}-{day}"

        return None

    def _extract_period(self, text: str, transactions: list | None = None) -> tuple[str, str]:
        """Extract billing period from Nubank statement.

        Tries regex patterns first, then falls back to deriving the period from
        already-extracted transactions, and finally uses the current month as a
        last resort (never returns hardcoded 2026 dates).
        """
        import datetime

        # Pattern: "01 ABR 2026" to "30 ABR 2026" or similar
        m = re.search(
            r"(\d{1,2})\s+([A-Za-zÀ-ú]{3})\w*\s+(\d{4})\s+(?:a|até|[-–])\s+(\d{1,2})\s+([A-Za-zÀ-ú]{3})\w*\s+(\d{4})",
            text,
        )
        if m:
            d1, m1, y1, d2, m2, y2 = m.groups()
            start = self._parse_pt_date(f"{d1} {m1} {y1}")
            end = self._parse_pt_date(f"{d2} {m2} {y2}")
            return start, end

        # Fallback: look for month/year references
        months_found = re.findall(r"(\d{1,2})\s+([A-Za-zÀ-ú]{3})\w*\s+(\d{4})", text[:500])
        if len(months_found) >= 2:
            first = months_found[0]
            last = months_found[-1]
            start = self._parse_pt_date(f"{first[0]} {first[1]} {first[2]}")
            end = self._parse_pt_date(f"{last[0]} {last[1]} {last[2]}")
            return start, end

        # New fallback: derive from already-extracted transactions
        if transactions:
            dates = [t.date for t in transactions if t.date and len(t.date) == 10]
            if dates:
                return min(dates), max(dates)

        # Last resort: use current month (not hardcoded 2026 dates)
        today = datetime.date.today()
        first = today.replace(day=1).isoformat()
        last = today.replace(day=28).isoformat()
        return first, last

    def _extract_total_amount(self, text: str) -> float:
        """Extract total invoice amount from Nubank statement."""
        # Pattern: "Total" or "TOTAL" followed by R$ amount
        m = re.search(
            r"[Tt]otal\s*(?:da\s+fatura)?\s*:?\s*R?\$?\s*([\d.,]+)",
            text,
        )
        if m:
            return self._parse_brl_amount(m.group(1))

        # Pattern: "R$ 1.234,56" near "total"
        m = re.search(r"R\$\s*([\d.,]+)", text)
        if m:
            return self._parse_brl_amount(m.group(1))

        return 0.0

    def _parse_brl_amount(self, amount_str: str) -> float:
        """Parse Brazilian currency format: 1.234,56 → 1234.56"""
        cleaned = amount_str.strip()
        # Brazilian format: dots as thousands separator, comma as decimal
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return abs(float(cleaned))
        except ValueError:
            return 0.0

    def _extract_sections(self, text: str) -> list[ExtractedSection]:
        """Extract sections separated by card holder names in Nubank statements.

        Nubank statements for additional cards have sections like:
        - "Cartão de <Name> - final <last4>"
        - Or simply a name header followed by transactions

        The PRIMARY holder does NOT have a "- final XXXX" suffix, so their
        transactions appear BEFORE the first section match and would otherwise
        be lost. This method captures that primary block as the first section.
        """
        sections: list[ExtractedSection] = []

        # Pattern for Nubank additional card sections
        # e.g., "VICTOR ZORE - final 4535" or "Cartão final 4535"
        section_pattern = re.compile(
            r"(?:Cartão\s+(?:de\s+)?)?([A-ZÀ-Ú][A-ZÀ-Ú ]+?)\s*[-–]\s*final\s+(\d{4})",
            re.IGNORECASE,
        )

        matches = list(section_pattern.finditer(text))

        if not matches:
            return []

        # Extract ref year from text
        year_match = re.search(r"(\d{4})", text[:500])
        ref_year = year_match.group(1) if year_match else "2026"

        # NEW (5.7): Capture primary holder transactions (before the first "- final XXXX" section)
        # The primary holder has no "- final XXXX" suffix, so their transactions appear
        # in the text BEFORE the first additional-card section match.
        primary_text = text[:matches[0].start()]
        primary_transactions = self._extract_transactions_from_text(
            primary_text, card_last4=None, ref_year=ref_year,
        )
        if primary_transactions:
            holder_name = self._extract_holder_name(text)
            subtotal = sum(
                t.amount if not t.is_refund else -t.amount
                for t in primary_transactions
            )
            sections.insert(0, ExtractedSection(
                owner_name=holder_name,
                subtotal=round(subtotal, 2),
                transactions=primary_transactions,
            ))

        for i, match in enumerate(matches):
            owner_name = match.group(1).strip().title()
            card_last4 = match.group(2)

            # Get text between this section header and the next one (or end)
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start_pos:end_pos]

            transactions = self._extract_transactions_from_text(
                section_text, card_last4=card_last4, ref_year=ref_year,
            )

            subtotal = sum(
                t.amount if not t.is_refund else -t.amount
                for t in transactions
            )

            sections.append(
                ExtractedSection(
                    owner_name=owner_name,
                    subtotal=round(subtotal, 2),
                    transactions=transactions,
                )
            )

        return sections

    def _extract_transactions_from_text(
        self,
        text: str,
        card_last4: Optional[str] = None,
        ref_year: str = "2026",
    ) -> list[ExtractedTransaction]:
        """Extract individual transactions from a block of text using regex.

        Nubank transaction lines typically look like:
          05 ABR   UBER *TRIP              12,50
          10 ABR   AMAZON.COM.BR  parcela 3/12   89,90

        Tries the primary pattern (2+ spaces before amount) first, then falls
        back to an alternative pattern that matches explicit BRL format values.
        """
        transactions: list[ExtractedTransaction] = []

        # Primary pattern: description ends in 2+ spaces before the value
        # (more tolerant of multiple spaces in Nubank PDF layout)
        tx_pattern = re.compile(
            r"^(\d{1,2})\s+([A-Za-zÀ-ú]{3})\s+"   # DD MMM
            r"(.+?)\s{2,}"                            # description (ends in 2+ spaces)
            r"(-?\s*[\d.,]+)\s*$",                    # value at end of line
            re.MULTILINE,
        )
        # Alternative pattern: value with explicit BRL format (X.XXX,XX or XXX,XX)
        tx_pattern_alt = re.compile(
            r"^(\d{1,2})\s+([A-Za-zÀ-ú]{3})\s+"
            r"(.+?)\s+"
            r"(-?[\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*$",
            re.MULTILINE,
        )

        # Try primary pattern first; if no matches, try alternative
        matches = list(tx_pattern.finditer(text))
        if not matches:
            matches = list(tx_pattern_alt.finditer(text))

        for m in matches:
            day = m.group(1)
            month_abbr = m.group(2)
            description = m.group(3).strip()
            amount_str = m.group(4).strip()

            date = self._parse_pt_date(f"{day} {month_abbr}", ref_year=ref_year)
            amount = self._parse_brl_amount(amount_str)

            # Detect refunds
            is_refund = False
            if any(kw in description.lower() for kw in ["estorno", "crédito", "devolução", "refund"]):
                is_refund = True

            # Detect installments: "parcela 3/12" or "3/12"
            is_installment = False
            installment_current = None
            installment_total = None
            inst_match = re.search(r"(?:parcela\s+)?(\d{1,2})/(\d{1,2})", description)
            if inst_match:
                is_installment = True
                installment_current = int(inst_match.group(1))
                installment_total = int(inst_match.group(2))

            # Detect foreign currency
            original_currency = None
            curr_match = re.search(r"\b(USD|EUR|GBP|ARS|CLP|MXN)\b", description, re.IGNORECASE)
            if curr_match:
                original_currency = curr_match.group(1).upper()

            transactions.append(
                ExtractedTransaction(
                    date=date,
                    card_last4=card_last4,
                    description=description,
                    amount=amount,
                    is_refund=is_refund,
                    is_installment=is_installment,
                    installment_current=installment_current,
                    installment_total=installment_total,
                    original_currency=original_currency,
                )
            )

        return transactions
