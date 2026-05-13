"""Preservation Property Tests — Task 2 of bulk-edit-overwrite-fix spec.

These tests capture the BASELINE enrichment behaviors that must NOT be broken
by the fix. They MUST PASS on the unfixed code. If any of these tests fail
after the fix is applied, the fix introduced a regression.

Observation-first methodology: We first observed the current behavior of
enrich_card_data() and compute_month_ref() for non-bug-condition inputs,
then encoded that behavior as property-based and concrete tests.

Observed behaviors on unfixed code:
- enrich_card_data({owner: None, type: None, card_last4: "1234"}, {"1234": CardInfo("Maria", "shared")})
  → {owner: "Maria", type: "shared", card_type: "shared"}
- enrich_card_data({owner: "Victor", type: "individual", card_last4: "9999"}, {"1234": CardInfo("Maria", "shared")})
  → {owner: "Victor", type: "individual"} (no matching card, no card_type added)
- enrich_card_data({owner: None, type: None, card_last4: None}, {"1234": CardInfo("Maria", "shared")})
  → unchanged transaction (no card_type added)
- compute_month_ref({date: "2026-04-05", month_ref: None}) → "2026-04"
- compute_month_ref({date: "2026-04-05", month_ref: "2026-03"}) → "2026-03"

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Ensure the backend directory is on sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from enrichment_service import CardInfo, EnrichmentService


# ---------------------------------------------------------------------------
# Strategies for property-based testing
# ---------------------------------------------------------------------------

# Card last4 digits (4 numeric characters)
card_last4_strategy = st.from_regex(r"[0-9]{4}", fullmatch=True)

# Card owner names
card_owner_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Card type values
card_type_strategy = st.sampled_from(["individual", "shared"])

# Valid date strings (YYYY-MM-DD format)
date_strategy = st.dates(
    min_value=__import__("datetime").date(2020, 1, 1),
    max_value=__import__("datetime").date(2030, 12, 31),
).map(lambda d: d.isoformat())

# Amount values
amount_strategy = st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False)

# Merchant names
merchant_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Property 1: NULL owner AND NULL type with matching card → enriched from card
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    card_last4=card_last4_strategy,
    card_owner_name=card_owner_strategy,
    card_type_val=card_type_strategy,
    date=date_strategy,
    amount=amount_strategy,
)
def test_property_null_owner_type_enriched_from_card(
    card_last4: str,
    card_owner_name: str,
    card_type_val: str,
    date: str,
    amount: float,
):
    """Property 2: Preservation — NULL Fields Still Enriched From Card Data.

    For all transactions where owner AND type are both NULL and card_last4
    matches a card in the map, enrich_card_data() sets owner, type, and
    card_type from the card data.

    This is the non-bug-condition case that must be preserved after the fix.

    **Validates: Requirements 3.1, 3.2**
    """
    svc = EnrichmentService()

    transaction = {
        "date": date,
        "amount": amount,
        "merchant_clean": "Test Merchant",
        "owner": None,
        "type": None,
        "card_last4": card_last4,
    }

    card_map = {
        card_last4: CardInfo(owner=card_owner_name, card_type=card_type_val),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # NULL owner must be enriched from card data
    assert result["owner"] == card_owner_name, (
        f"Preservation FAILED: NULL owner should be enriched from card. "
        f"Expected owner='{card_owner_name}' but got owner='{result['owner']}'"
    )

    # NULL type must be enriched from card data
    assert result["type"] == card_type_val, (
        f"Preservation FAILED: NULL type should be enriched from card. "
        f"Expected type='{card_type_val}' but got type='{result['type']}'"
    )

    # card_type must always be enriched from card data
    assert result["card_type"] == card_type_val, (
        f"Preservation FAILED: card_type should always be enriched. "
        f"Expected card_type='{card_type_val}' but got card_type='{result.get('card_type')}'"
    )


# ---------------------------------------------------------------------------
# Property 2: No matching card → transaction unchanged
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    card_last4=card_last4_strategy,
    card_owner_name=card_owner_strategy,
    card_type_val=card_type_strategy,
    tx_owner=st.one_of(st.none(), st.text(min_size=1, max_size=20).filter(lambda s: s.strip())),
    tx_type=st.one_of(st.none(), st.sampled_from(["individual", "shared", "personal"])),
    date=date_strategy,
    amount=amount_strategy,
)
def test_property_no_matching_card_preserves_all_fields(
    card_last4: str,
    card_owner_name: str,
    card_type_val: str,
    tx_owner,
    tx_type,
    date: str,
    amount: float,
):
    """Property 2: Preservation — No Matching Card Preserves All Fields.

    For all transactions where card_last4 is NOT in the card_map, the
    transaction is returned unchanged (no card_type added, owner/type preserved).

    **Validates: Requirements 3.3**
    """
    svc = EnrichmentService()

    # Use a card_last4 that does NOT match any card in the map
    non_matching_last4 = "9999" if card_last4 != "9999" else "8888"

    transaction = {
        "date": date,
        "amount": amount,
        "merchant_clean": "Test Merchant",
        "owner": tx_owner,
        "type": tx_type,
        "card_last4": non_matching_last4,
    }

    card_map = {
        card_last4: CardInfo(owner=card_owner_name, card_type=card_type_val),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # Owner must be preserved unchanged
    assert result["owner"] == tx_owner, (
        f"Preservation FAILED: owner should be unchanged when no matching card. "
        f"Expected owner={tx_owner!r} but got owner={result['owner']!r}"
    )

    # Type must be preserved unchanged
    assert result["type"] == tx_type, (
        f"Preservation FAILED: type should be unchanged when no matching card. "
        f"Expected type={tx_type!r} but got type={result['type']!r}"
    )

    # card_type should NOT be added when no matching card
    assert "card_type" not in result or result.get("card_type") == transaction.get("card_type"), (
        f"Preservation FAILED: card_type should not be added when no matching card. "
        f"Got card_type={result.get('card_type')!r}"
    )


# ---------------------------------------------------------------------------
# Property 3: card_type always enriched from card data (regardless of owner/type)
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    card_last4=card_last4_strategy,
    card_owner_name=card_owner_strategy,
    card_type_val=card_type_strategy,
    tx_owner=st.one_of(st.none(), st.text(min_size=1, max_size=20).filter(lambda s: s.strip())),
    tx_type=st.one_of(st.none(), st.sampled_from(["individual", "shared", "personal"])),
    date=date_strategy,
    amount=amount_strategy,
)
def test_property_card_type_always_enriched(
    card_last4: str,
    card_owner_name: str,
    card_type_val: str,
    tx_owner,
    tx_type,
    date: str,
    amount: float,
):
    """Property 2: Preservation — card_type Always Enriched From Card Data.

    For all transactions with a matching card_last4, card_type is ALWAYS set
    from card data regardless of owner/type values. This is metadata enrichment
    that should never be conditional.

    **Validates: Requirements 3.4**
    """
    svc = EnrichmentService()

    transaction = {
        "date": date,
        "amount": amount,
        "merchant_clean": "Test Merchant",
        "owner": tx_owner,
        "type": tx_type,
        "card_last4": card_last4,
    }

    card_map = {
        card_last4: CardInfo(owner=card_owner_name, card_type=card_type_val),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # card_type must always be enriched from card data when card matches
    assert result["card_type"] == card_type_val, (
        f"Preservation FAILED: card_type should always be enriched from card data. "
        f"Expected card_type='{card_type_val}' but got card_type='{result.get('card_type')}'"
    )


# ---------------------------------------------------------------------------
# Property 4: compute_month_ref derives month_ref from date when NULL
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(date=date_strategy, amount=amount_strategy)
def test_property_compute_month_ref_derives_from_date_when_null(
    date: str,
    amount: float,
):
    """Property 2: Preservation — Month_ref Derived From Date When NULL.

    For all transactions with NULL month_ref, compute_month_ref() derives
    month_ref from date[:7] (YYYY-MM format).

    **Validates: Requirements 3.5, 3.6**
    """
    svc = EnrichmentService()

    transaction = {
        "date": date,
        "amount": amount,
        "month_ref": None,
    }

    result = svc.compute_month_ref(transaction)

    expected_month_ref = date[:7]
    assert result == expected_month_ref, (
        f"Preservation FAILED: NULL month_ref should be derived from date[:7]. "
        f"Expected month_ref='{expected_month_ref}' but got month_ref='{result}'"
    )


# ---------------------------------------------------------------------------
# Property 5: NULL card_last4 → transaction unchanged
# ---------------------------------------------------------------------------

@settings(max_examples=50)
@given(
    card_owner_name=card_owner_strategy,
    card_type_val=card_type_strategy,
    tx_owner=st.one_of(st.none(), st.text(min_size=1, max_size=20).filter(lambda s: s.strip())),
    tx_type=st.one_of(st.none(), st.sampled_from(["individual", "shared", "personal"])),
    date=date_strategy,
    amount=amount_strategy,
)
def test_property_null_card_last4_preserves_transaction(
    card_owner_name: str,
    card_type_val: str,
    tx_owner,
    tx_type,
    date: str,
    amount: float,
):
    """Property 2: Preservation — NULL card_last4 Preserves Transaction.

    For all transactions where card_last4 is None, the transaction is returned
    unchanged regardless of what's in the card_map.

    **Validates: Requirements 3.3**
    """
    svc = EnrichmentService()

    transaction = {
        "date": date,
        "amount": amount,
        "merchant_clean": "Test Merchant",
        "owner": tx_owner,
        "type": tx_type,
        "card_last4": None,
    }

    card_map = {
        "1234": CardInfo(owner=card_owner_name, card_type=card_type_val),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # Owner must be preserved unchanged
    assert result["owner"] == tx_owner, (
        f"Preservation FAILED: owner should be unchanged when card_last4 is None. "
        f"Expected owner={tx_owner!r} but got owner={result['owner']!r}"
    )

    # Type must be preserved unchanged
    assert result["type"] == tx_type, (
        f"Preservation FAILED: type should be unchanged when card_last4 is None. "
        f"Expected type={tx_type!r} but got type={result['type']!r}"
    )


# ---------------------------------------------------------------------------
# Concrete observation cases
# ---------------------------------------------------------------------------

def test_concrete_null_owner_type_enriched_from_card():
    """Concrete observation: NULL owner/type with matching card gets enriched.

    Observed on unfixed code:
    enrich_card_data({owner: None, type: None, card_last4: "1234"},
                    {"1234": CardInfo("Maria", "shared")})
    → {owner: "Maria", type: "shared", card_type: "shared"}

    **Validates: Requirements 3.1, 3.2**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 100.0,
        "merchant_clean": "Supermercado",
        "owner": None,
        "type": None,
        "card_last4": "1234",
    }

    card_map = {
        "1234": CardInfo(owner="Maria", card_type="shared"),
    }

    result = svc.enrich_card_data(transaction, card_map)

    assert result["owner"] == "Maria", (
        f"Expected owner='Maria' (enriched from card) but got owner='{result['owner']}'"
    )
    assert result["type"] == "shared", (
        f"Expected type='shared' (enriched from card) but got type='{result['type']}'"
    )
    assert result["card_type"] == "shared", (
        f"Expected card_type='shared' but got card_type='{result.get('card_type')}'"
    )


def test_concrete_no_matching_card_preserves_values():
    """Concrete observation: Non-NULL owner/type with no matching card preserved.

    Observed on unfixed code:
    enrich_card_data({owner: "Victor", type: "individual", card_last4: "9999"},
                    {"1234": CardInfo("Maria", "shared")})
    → {owner: "Victor", type: "individual"} (no card_type added)

    **Validates: Requirements 3.3**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 50.0,
        "merchant_clean": "Farmacia",
        "owner": "Victor",
        "type": "individual",
        "card_last4": "9999",
    }

    card_map = {
        "1234": CardInfo(owner="Maria", card_type="shared"),
    }

    result = svc.enrich_card_data(transaction, card_map)

    assert result["owner"] == "Victor", (
        f"Expected owner='Victor' (preserved) but got owner='{result['owner']}'"
    )
    assert result["type"] == "individual", (
        f"Expected type='individual' (preserved) but got type='{result['type']}'"
    )
    # No card_type should be added when no matching card
    assert result.get("card_type") is None, (
        f"Expected no card_type when no matching card, but got card_type='{result.get('card_type')}'"
    )


def test_concrete_null_card_last4_unchanged():
    """Concrete observation: NULL card_last4 leaves transaction unchanged.

    Observed on unfixed code:
    enrich_card_data({owner: None, type: None, card_last4: None},
                    {"1234": CardInfo("Maria", "shared")})
    → unchanged transaction (no card_type added)

    **Validates: Requirements 3.3**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 75.0,
        "merchant_clean": "Padaria",
        "owner": None,
        "type": None,
        "card_last4": None,
    }

    card_map = {
        "1234": CardInfo(owner="Maria", card_type="shared"),
    }

    result = svc.enrich_card_data(transaction, card_map)

    assert result["owner"] is None, (
        f"Expected owner=None (unchanged) but got owner='{result['owner']}'"
    )
    assert result["type"] is None, (
        f"Expected type=None (unchanged) but got type='{result['type']}'"
    )
    assert result.get("card_type") is None, (
        f"Expected no card_type when card_last4 is None, but got card_type='{result.get('card_type')}'"
    )


def test_concrete_compute_month_ref_null_derives_from_date():
    """Concrete observation: NULL month_ref is derived from date[:7].

    Observed on unfixed code:
    compute_month_ref({date: "2026-04-05", month_ref: None}) → "2026-04"

    **Validates: Requirements 3.5, 3.6**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 100.0,
        "month_ref": None,
    }

    result = svc.compute_month_ref(transaction)

    assert result == "2026-04", (
        f"Expected month_ref='2026-04' (derived from date) but got month_ref='{result}'"
    )


def test_concrete_compute_month_ref_existing_preserved():
    """Concrete observation: Existing month_ref is preserved (not overwritten).

    Observed on unfixed code:
    compute_month_ref({date: "2026-04-05", month_ref: "2026-03"}) → "2026-03"

    **Validates: Requirements 3.5**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 100.0,
        "month_ref": "2026-03",
    }

    result = svc.compute_month_ref(transaction)

    assert result == "2026-03", (
        f"Expected month_ref='2026-03' (preserved) but got month_ref='{result}'"
    )
