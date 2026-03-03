"""Tests for helper/parsing functions."""
import os
os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("AUTO_JOIN_LEGACY_WORKSPACE", "false")

from helpers import (
    normalize_owner,
    parse_br_money,
    parse_br_percent,
    parse_month_ref,
    parse_ddmmyyyy_to_iso,
    parse_signed_amount,
    normalize_email,
    normalize_plan,
)
import pytest
from fastapi import HTTPException


class TestNormalizeOwner:
    def test_victor(self):
        assert normalize_owner("victor") == "Victor"
        assert normalize_owner("VICTOR") == "Victor"

    def test_larissa(self):
        assert normalize_owner("larissa") == "Larissa"
        assert normalize_owner("Larissa") == "Larissa"

    def test_invalid_raises(self):
        with pytest.raises(HTTPException):
            normalize_owner("unknown")


class TestParseBrMoney:
    def test_simple(self):
        assert parse_br_money("R$ 1.234,56") == 1234.56

    def test_none(self):
        assert parse_br_money(None) is None

    def test_nan(self):
        assert parse_br_money("nan") is None


class TestParseMonthRef:
    def test_valid(self):
        assert parse_month_ref("01/2025") == "2025-01"
        assert parse_month_ref("12/2024") == "2024-12"

    def test_invalid(self):
        assert parse_month_ref("13/2025") is None
        assert parse_month_ref(None) is None


class TestParseDdmmyyyy:
    def test_valid(self):
        assert parse_ddmmyyyy_to_iso("15/06/2025") == "2025-06-15"

    def test_invalid(self):
        assert parse_ddmmyyyy_to_iso("invalid") is None
        assert parse_ddmmyyyy_to_iso(None) is None
