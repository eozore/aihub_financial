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
from pydantic import BaseModel

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
# Gemini prompt
# ---------------------------------------------------------------------------

GEMINI_EXTRACTION_PROMPT = """\
You are a financial document parser. Extract ALL transactions from the attached \
bank statement PDF and return a single JSON object that strictly follows this schema:

{
  "statement_type": "credit_card" or "current_account",
  "bank": "<bank name, e.g. Nubank>",
  "holder_name": "<primary account holder name>",
  "due_date": "<YYYY-MM-DD or null>",
  "period_start": "<YYYY-MM-DD>",
  "period_end": "<YYYY-MM-DD>",
  "total_amount": <float, total invoice amount>,
  "sections": [
    {
      "owner_name": "<card holder name for this section>",
      "subtotal": <float, section subtotal>,
      "transactions": [
        {
          "date": "<YYYY-MM-DD>",
          "card_last4": "<last 4 digits of card or null>",
          "description": "<merchant / transaction description>",
          "amount": <float, positive value>,
          "is_refund": <bool>,
          "is_installment": <bool>,
          "installment_current": <int or null>,
          "installment_total": <int or null>,
          "original_currency": "<ISO currency code or null>"
        }
      ]
    }
  ]
}

Rules:
- Return ONLY the JSON object, no markdown fences, no explanation.
- Amounts are always positive floats. Use is_refund=true for credits/refunds.
- Dates must be in YYYY-MM-DD format.
- If the statement has multiple card holders (additional cards), create one section per holder.
- If a transaction shows installment info like "parcela 3/12", set is_installment=true, \
installment_current=3, installment_total=12.
- If a transaction is in a foreign currency, set original_currency to the ISO code (e.g. "USD").
- card_last4 should contain the last 4 digits of the card used, if visible in the statement.
"""


# ---------------------------------------------------------------------------
# ExtractionService — Tasks 9.2 & 9.3
# ---------------------------------------------------------------------------

class ExtractionService:
    """Extracts transactions from PDF statements using Gemini Flash 2.5 with cache and fallback."""

    def __init__(self, gemini_model=None):
        self._cache: dict[str, ExtractedStatement] = {}
        self._model = gemini_model  # Lazy-init if None

    def _get_model(self):
        """Lazy-initialise the Gemini model on first use."""
        if self._model is None:
            import google.generativeai as genai
            self._model = genai.GenerativeModel("gemini-2.5-flash")
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pdf_bytes: bytes) -> ExtractedStatement:
        """Pipeline: cache → Gemini (3 retries with exponential backoff) → pdfplumber fallback."""
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # 1. Cache lookup
        if file_hash in self._cache:
            logger.info("Cache hit for PDF hash %s", file_hash[:12])
            return self._cache[file_hash]

        # 2. Gemini extraction with retry
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                raw_json = self._call_gemini(pdf_bytes)
                validated = ExtractedStatement.model_validate_json(raw_json)
                self._cache[file_hash] = validated
                logger.info("Gemini extraction succeeded on attempt %d", attempt + 1)
                return validated
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 2 ** attempt  # 1s, 2s, 4s
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

    # ------------------------------------------------------------------
    # Gemini extraction — Task 9.2
    # ------------------------------------------------------------------

    def _call_gemini(self, pdf_bytes: bytes) -> str:
        """Send PDF to Gemini with a structured prompt requesting JSON output."""
        model = self._get_model()

        # Upload PDF as inline data
        response = model.generate_content(
            [
                GEMINI_EXTRACTION_PROMPT,
                {"mime_type": "application/pdf", "data": pdf_bytes},
            ]
        )

        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        return raw_text

    # ------------------------------------------------------------------
    # pdfplumber fallback for Nubank — Task 9.3
    # ------------------------------------------------------------------

    def _fallback_pdfplumber(self, pdf_bytes: bytes) -> ExtractedStatement:
        """Parse Nubank credit card statements using pdfplumber + regex."""
        import io

        full_text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"

        if not full_text.strip():
            raise ValueError("Could not extract any text from PDF")

        # --- Extract statement metadata ---
        holder_name = self._extract_holder_name(full_text)
        due_date = self._extract_due_date(full_text)
        period_start, period_end = self._extract_period(full_text)
        total_amount = self._extract_total_amount(full_text)

        # --- Extract sections (by card holder) ---
        sections = self._extract_sections(full_text)

        # If no sections found, create a single section with all transactions
        if not sections:
            transactions = self._extract_transactions_from_text(full_text)
            sections = [
                ExtractedSection(
                    owner_name=holder_name,
                    subtotal=total_amount,
                    transactions=transactions,
                )
            ]

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

    # ------------------------------------------------------------------
    # Nubank-specific helpers
    # ------------------------------------------------------------------

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
        """Extract the primary holder name from Nubank statement."""
        # Nubank statements typically have the holder name near the top
        # Pattern: name appears after "Fatura" or at the beginning
        m = re.search(r"(?:Olá|Oi|Fatura\s+de)\s*,?\s*([A-ZÀ-Ú][a-zà-ú]+(?:[ ]+[A-ZÀ-Ú][a-zà-ú]+)*)", text)
        if m:
            return m.group(1).strip()

        # Fallback: look for a name pattern in the first few lines
        lines = text.split("\n")[:20]
        for line in lines:
            # Match capitalized names (at least 2 words)
            m = re.match(r"^([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)+)\s*$", line.strip())
            if m:
                return m.group(1).strip()

        return "Titular"

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

    def _extract_period(self, text: str) -> tuple[str, str]:
        """Extract billing period from Nubank statement."""
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

        return "2026-01-01", "2026-01-31"

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
        """
        transactions: list[ExtractedTransaction] = []

        # Transaction line pattern:
        # DD MMM   DESCRIPTION   AMOUNT
        tx_pattern = re.compile(
            r"(\d{1,2})\s+([A-Za-zÀ-ú]{3})\s+"  # date: DD MMM
            r"(.+?)\s+"                             # description (non-greedy)
            r"(-?\s*[\d.,]+)\s*$",                  # amount at end of line
            re.MULTILINE,
        )

        for m in tx_pattern.finditer(text):
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
