"""Shared utility / parsing functions."""
import datetime
import os
import re
from typing import Optional

from fastapi import HTTPException

from config import PLAN_LIMITS


def normalize_owner(owner: Optional[str]) -> str:
    """Return the owner string stripped and title-cased.

    Previously this validated against a static OWNERS list from config.
    Validation against workspace members is now the caller's responsibility
    (see the dynamic ``GET /owners`` endpoint).
    """
    raw = (owner or "").strip()
    if not raw:
        raise HTTPException(
            status_code=400,
            detail="Owner name must not be empty",
        )
    return raw


def parse_br_money(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.lower() == "nan":
        return None
    normalized = raw.replace("R$", "").replace(" ", "")
    normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except Exception:
        return None


def parse_br_percent(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.lower() == "nan":
        return None
    normalized = raw.replace("%", "").replace(" ", "")
    normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized) / 100.0
    except Exception:
        return None


def parse_month_ref(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        month_str, year_str = raw.split("/", 1)
        month = int(month_str)
        year = int(year_str)
        if month < 1 or month > 12:
            return None
        if year < 1900 or year > 2100:
            return None
        return f"{year:04d}-{month:02d}"
    except Exception:
        return None


def parse_ddmmyyyy_to_iso(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        day_str, month_str, year_str = raw.split("/", 2)
        parsed = datetime.date(int(year_str), int(month_str), int(day_str))
        return parsed.isoformat()
    except Exception:
        return None


def parse_signed_amount(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("R$", "").replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except Exception:
        return None


def category_for_current_account(description: str, is_card_invoice_payment: bool) -> str:
    lowered = description.lower()
    if is_card_invoice_payment:
        return "Pagamento de fatura"
    if "boleto" in lowered:
        return "Boletos"
    if "imposto" in lowered or "receita federal" in lowered:
        return "Impostos"
    if "transfer" in lowered or "pix" in lowered:
        return "Transferências"
    return "Conta Corrente"


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def normalize_plan(plan_type: Optional[str]) -> str:
    normalized = (plan_type or "free").strip().lower()
    if normalized not in PLAN_LIMITS:
        raise HTTPException(status_code=400, detail=f"Invalid plan_type: {plan_type}")
    return normalized


def plan_limits(plan_type: Optional[str]) -> dict:
    return PLAN_LIMITS[normalize_plan(plan_type)]


def normalize_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()
