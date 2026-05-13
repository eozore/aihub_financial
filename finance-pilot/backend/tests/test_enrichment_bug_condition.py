"""Bug Condition Exploration Tests — Task 1 of bulk-edit-overwrite-fix spec.

These tests MUST FAIL on the unfixed code. Each failure documents a concrete
counterexample that proves the bug exists: enrich_card_data() unconditionally
overwrites non-NULL owner/type fields with card-derived values.

DO NOT fix the code or the test when it fails — the failure confirms the bug.

After the fix is applied (Task 3), re-running this file should produce
all PASSING results (Task 3.4).

Validates: Requirements 1.1, 1.2, 1.3, 1.4
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the backend directory is on sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from enrichment_service import CardInfo, EnrichmentService


# ---------------------------------------------------------------------------
# Strategies for property-based testing
# ---------------------------------------------------------------------------

# Non-empty owner names (simulating user-edited values)
non_null_owner = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Non-empty type values (simulating user-edited values)
non_null_type = st.sampled_from(["individual", "shared", "personal", "business"])

# Card last4 digits
card_last4_strategy = st.from_regex(r"[0-9]{4}", fullmatch=True)

# Card owner names (different from transaction owner to trigger the bug)
card_owner = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Card type values
card_type_strategy = st.sampled_from(["individual", "shared"])


# ---------------------------------------------------------------------------
# Property-based test: enrichment must preserve non-NULL owner/type
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    owner=non_null_owner,
    tx_type=non_null_type,
    card_last4=card_last4_strategy,
    card_owner_name=card_owner,
    card_type_val=card_type_strategy,
)
def test_property_enrichment_preserves_non_null_fields(
    owner: str,
    tx_type: str,
    card_last4: str,
    card_owner_name: str,
    card_type_val: str,
):
    """Property 1: Bug Condition — Enrichment Overwrites User-Edited Owner/Type Fields.

    For all transactions where card_last4 IN card_map AND (owner IS NOT NULL OR
    type IS NOT NULL), assert enrich_card_data(tx, card_map).owner == tx.owner
    and enrich_card_data(tx, card_map).type == tx.type.

    Also asserts card_type is always enriched from card data (unconditional).

    EXPECTED TO FAIL on unfixed code — this confirms the bug exists.

    **Validates: Requirements 1.1, 1.2**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 100.0,
        "merchant_clean": "Test Merchant",
        "owner": owner,
        "type": tx_type,
        "card_last4": card_last4,
    }

    card_map = {
        card_last4: CardInfo(owner=card_owner_name, card_type=card_type_val),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # Non-NULL owner must be preserved (not overwritten by card data)
    assert result["owner"] == owner, (
        f"Bug confirmed: owner was overwritten! "
        f"Expected owner='{owner}' (user edit) but got owner='{result['owner']}' "
        f"(card-derived from CardInfo.owner='{card_owner_name}')"
    )

    # Non-NULL type must be preserved (not overwritten by card data)
    assert result["type"] == tx_type, (
        f"Bug confirmed: type was overwritten! "
        f"Expected type='{tx_type}' (user edit) but got type='{result['type']}' "
        f"(card-derived from CardInfo.card_type='{card_type_val}')"
    )

    # card_type is always enriched from card data (unconditional — this is correct)
    assert result["card_type"] == card_type_val, (
        f"card_type should always be enriched from card data. "
        f"Expected card_type='{card_type_val}' but got '{result.get('card_type')}'"
    )


# ---------------------------------------------------------------------------
# Property-based test: enrichment preserves non-NULL owner (type may be NULL)
# ---------------------------------------------------------------------------

@settings(max_examples=50)
@given(
    owner=non_null_owner,
    card_last4=card_last4_strategy,
    card_owner_name=card_owner,
    card_type_val=card_type_strategy,
)
def test_property_enrichment_preserves_non_null_owner_only(
    owner: str,
    card_last4: str,
    card_owner_name: str,
    card_type_val: str,
):
    """Property: When only owner is non-NULL, it must be preserved.

    EXPECTED TO FAIL on unfixed code.

    **Validates: Requirements 1.1**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 50.0,
        "merchant_clean": "Test",
        "owner": owner,
        "type": None,
        "card_last4": card_last4,
    }

    card_map = {
        card_last4: CardInfo(owner=card_owner_name, card_type=card_type_val),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # Non-NULL owner must be preserved
    assert result["owner"] == owner, (
        f"Bug confirmed: owner was overwritten! "
        f"Expected owner='{owner}' but got owner='{result['owner']}' "
        f"(card-derived: '{card_owner_name}')"
    )


# ---------------------------------------------------------------------------
# Property-based test: enrichment preserves non-NULL type (owner may be NULL)
# ---------------------------------------------------------------------------

@settings(max_examples=50)
@given(
    tx_type=non_null_type,
    card_last4=card_last4_strategy,
    card_owner_name=card_owner,
    card_type_val=card_type_strategy,
)
def test_property_enrichment_preserves_non_null_type_only(
    tx_type: str,
    card_last4: str,
    card_owner_name: str,
    card_type_val: str,
):
    """Property: When only type is non-NULL, it must be preserved.

    EXPECTED TO FAIL on unfixed code.

    **Validates: Requirements 1.2**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 75.0,
        "merchant_clean": "Test",
        "owner": None,
        "type": tx_type,
        "card_last4": card_last4,
    }

    card_map = {
        card_last4: CardInfo(owner=card_owner_name, card_type=card_type_val),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # Non-NULL type must be preserved
    assert result["type"] == tx_type, (
        f"Bug confirmed: type was overwritten! "
        f"Expected type='{tx_type}' but got type='{result['type']}' "
        f"(card-derived: '{card_type_val}')"
    )


# ---------------------------------------------------------------------------
# Concrete deterministic test cases
# ---------------------------------------------------------------------------

def test_concrete_victor_owner_overwritten_by_maria():
    """Concrete case: owner='Victor', type='individual', card maps to Maria/shared.

    This is the exact example from the bug report. After enrichment, the user's
    edit (owner='Victor') should be preserved, but the bug causes it to be
    overwritten with 'Maria'.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: enrich_card_data({owner: 'Victor', card_last4: '1234'},
    {'1234': CardInfo('Maria', 'shared')}) returns owner='Maria' instead of 'Victor'

    **Validates: Requirements 1.1, 1.2, 1.3**
    """
    svc = EnrichmentService()

    transaction = {
        "date": "2026-04-05",
        "amount": 200.0,
        "merchant_clean": "Supermercado",
        "owner": "Victor",
        "type": "individual",
        "card_last4": "1234",
    }

    card_map = {
        "1234": CardInfo(owner="Maria", card_type="shared"),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # Owner must be preserved (user edit)
    assert result["owner"] == "Victor", (
        f"Bug confirmed: owner overwritten! "
        f"Expected owner='Victor' (user edit) but got owner='{result['owner']}' "
        f"(card-derived from CardInfo.owner='Maria')"
    )

    # Type must be preserved (user edit)
    assert result["type"] == "individual", (
        f"Bug confirmed: type overwritten! "
        f"Expected type='individual' (user edit) but got type='{result['type']}' "
        f"(card-derived from CardInfo.card_type='shared')"
    )

    # card_type is always enriched (this is correct behavior)
    assert result["card_type"] == "shared", (
        f"card_type should always be enriched. "
        f"Expected 'shared' but got '{result.get('card_type')}'"
    )


def test_concrete_card_update_retroactive_change():
    """Concrete case: card owner changes, historical transaction should keep old owner.

    Transaction was edited to owner='Ana'. Card is later updated to owner='Pedro'.
    Enrichment should NOT retroactively change the transaction's owner.

    EXPECTED TO FAIL on unfixed code.
    Counterexample: transaction with owner='Ana' becomes owner='Pedro' after card update.

    **Validates: Requirements 1.4**
    """
    svc = EnrichmentService()

    # Transaction was manually set to owner='Ana' (user edit)
    transaction = {
        "date": "2026-03-15",
        "amount": 150.0,
        "merchant_clean": "Farmacia",
        "owner": "Ana",
        "type": "individual",
        "card_last4": "4444",
    }

    # Card was updated: now owner='Pedro' (but transaction should keep 'Ana')
    card_map = {
        "4444": CardInfo(owner="Pedro", card_type="shared"),
    }

    result = svc.enrich_card_data(transaction, card_map)

    # Owner must be preserved (user's historical edit)
    assert result["owner"] == "Ana", (
        f"Bug confirmed: retroactive card update overwrote owner! "
        f"Expected owner='Ana' (user edit) but got owner='{result['owner']}' "
        f"(card-derived from updated CardInfo.owner='Pedro')"
    )

    # Type must be preserved
    assert result["type"] == "individual", (
        f"Bug confirmed: retroactive card update overwrote type! "
        f"Expected type='individual' (user edit) but got type='{result['type']}' "
        f"(card-derived from updated CardInfo.card_type='shared')"
    )
