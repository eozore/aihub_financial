"""Unit tests for card_service.py — CRUD operations with tenant isolation.

Validates Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import importlib
import os
import sys
import uuid

import pytest

# Force SQLite mode before importing anything from the app
os.environ["USE_SQLITE"] = "true"
os.environ["USE_MOCK_DATA"] = "false"
os.environ["REQUIRE_AUTH_FOR_DATA"] = "false"
os.environ["TENANT_REQUIRED"] = "false"
os.environ["PROJECT_ID"] = "test-project"

# Ensure the backend directory is on sys.path so bare imports work
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import HTTPException
from pydantic import ValidationError

from card_service import (
    CardCreate,
    CardResponse,
    CardUpdate,
    create_card,
    delete_card,
    get_card,
    list_cards,
    update_card,
)
import database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Create a fresh in-memory-like SQLite DB for every test."""
    db_file = tmp_path / "test_cards.db"
    monkeypatch.setattr(database, "DB_PATH", db_file)

    # Initialise the base schema so the cards table exists
    database.init_db()

    # Apply migration 002 to create the cards table
    conn = database.get_db_connection()
    import importlib
    mig002 = importlib.import_module("migrations.002_create_saas_tables")
    mig002.apply(conn)
    conn.commit()
    conn.close()

    yield


WS_A = "workspace-a"
WS_B = "workspace-b"


def _make_card(**overrides) -> CardCreate:
    defaults = {
        "owner": "Alice",
        "last4": "1234",
        "card_type": "individual",
        "bank": "nubank",
    }
    defaults.update(overrides)
    return CardCreate(**defaults)


# ---------------------------------------------------------------------------
# Pydantic validation (Req 3.2, 3.7)
# ---------------------------------------------------------------------------

class TestCardCreateValidation:
    """Validates: Requirements 3.2, 3.7"""

    def test_valid_last4_accepted(self):
        card = CardCreate(owner="Bob", last4="0000", card_type="shared")
        assert card.last4 == "0000"

    def test_valid_last4_all_nines(self):
        card = CardCreate(owner="Bob", last4="9999", card_type="individual")
        assert card.last4 == "9999"

    @pytest.mark.parametrize("bad_last4", [
        "123",       # too short
        "12345",     # too long
        "abcd",      # letters
        "12a4",      # mixed
        "",          # empty
        "12 4",      # space
    ])
    def test_invalid_last4_rejected(self, bad_last4):
        with pytest.raises(ValidationError):
            CardCreate(owner="Bob", last4=bad_last4, card_type="individual")

    def test_valid_card_type_individual(self):
        card = CardCreate(owner="Bob", last4="1111", card_type="individual")
        assert card.card_type == "individual"

    def test_valid_card_type_shared(self):
        card = CardCreate(owner="Bob", last4="2222", card_type="shared")
        assert card.card_type == "shared"

    def test_invalid_card_type_rejected(self):
        with pytest.raises(ValidationError):
            CardCreate(owner="Bob", last4="1111", card_type="corporate")


# ---------------------------------------------------------------------------
# create_card (Req 3.1, 3.3, 3.8)
# ---------------------------------------------------------------------------

class TestCreateCard:
    """Validates: Requirements 3.1, 3.3, 3.8"""

    def test_create_card_returns_card_response(self):
        card = create_card(WS_A, _make_card())
        assert isinstance(card, CardResponse)
        assert card.workspace_id == WS_A
        assert card.last4 == "1234"
        assert card.owner == "Alice"
        assert card.card_type == "individual"
        assert card.bank == "nubank"
        assert card.is_active is True
        assert card.id.startswith("card-")

    def test_create_card_stores_all_fields(self):
        card = create_card(WS_A, _make_card(label="My Visa", bank="itau"))
        assert card.label == "My Visa"
        assert card.bank == "itau"
        assert card.created_at is not None
        assert card.updated_at is not None

    def test_duplicate_last4_same_workspace_returns_409(self):
        create_card(WS_A, _make_card(last4="5678"))
        with pytest.raises(HTTPException) as exc_info:
            create_card(WS_A, _make_card(last4="5678"))
        assert exc_info.value.status_code == 409

    def test_same_last4_different_workspaces_allowed(self):
        card_a = create_card(WS_A, _make_card(last4="9999"))
        card_b = create_card(WS_B, _make_card(last4="9999"))
        assert card_a.workspace_id == WS_A
        assert card_b.workspace_id == WS_B


# ---------------------------------------------------------------------------
# list_cards (Req 3.4)
# ---------------------------------------------------------------------------

class TestListCards:
    """Validates: Requirement 3.4"""

    def test_list_cards_returns_only_workspace_cards(self):
        create_card(WS_A, _make_card(last4="1111"))
        create_card(WS_A, _make_card(last4="2222"))
        create_card(WS_B, _make_card(last4="3333"))

        cards_a = list_cards(WS_A)
        cards_b = list_cards(WS_B)

        assert len(cards_a) == 2
        assert len(cards_b) == 1
        assert all(c.workspace_id == WS_A for c in cards_a)
        assert all(c.workspace_id == WS_B for c in cards_b)

    def test_list_cards_empty_workspace(self):
        cards = list_cards("workspace-empty")
        assert cards == []


# ---------------------------------------------------------------------------
# get_card (Req 3.4)
# ---------------------------------------------------------------------------

class TestGetCard:
    """Validates: Requirement 3.4"""

    def test_get_card_own_workspace(self):
        created = create_card(WS_A, _make_card())
        fetched = get_card(WS_A, created.id)
        assert fetched.id == created.id

    def test_get_card_wrong_workspace_returns_404(self):
        created = create_card(WS_A, _make_card())
        with pytest.raises(HTTPException) as exc_info:
            get_card(WS_B, created.id)
        assert exc_info.value.status_code == 404

    def test_get_card_nonexistent_returns_404(self):
        with pytest.raises(HTTPException) as exc_info:
            get_card(WS_A, "card-does-not-exist")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# update_card (Req 3.5)
# ---------------------------------------------------------------------------

class TestUpdateCard:
    """Validates: Requirement 3.5"""

    def test_update_card_changes_fields(self):
        created = create_card(WS_A, _make_card())
        updated = update_card(WS_A, created.id, CardUpdate(owner="Bob", card_type="shared"))
        assert updated.owner == "Bob"
        assert updated.card_type == "shared"
        # Unchanged fields preserved
        assert updated.last4 == created.last4
        assert updated.bank == created.bank

    def test_update_card_wrong_workspace_returns_404(self):
        created = create_card(WS_A, _make_card())
        with pytest.raises(HTTPException) as exc_info:
            update_card(WS_B, created.id, CardUpdate(owner="Hacker"))
        assert exc_info.value.status_code == 404

    def test_update_card_nonexistent_returns_404(self):
        with pytest.raises(HTTPException) as exc_info:
            update_card(WS_A, "card-nope", CardUpdate(owner="X"))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# delete_card (Req 3.6)
# ---------------------------------------------------------------------------

class TestDeleteCard:
    """Validates: Requirement 3.6"""

    def test_delete_card_removes_it(self):
        created = create_card(WS_A, _make_card())
        delete_card(WS_A, created.id)
        with pytest.raises(HTTPException) as exc_info:
            get_card(WS_A, created.id)
        assert exc_info.value.status_code == 404

    def test_delete_card_wrong_workspace_returns_404(self):
        created = create_card(WS_A, _make_card())
        with pytest.raises(HTTPException) as exc_info:
            delete_card(WS_B, created.id)
        assert exc_info.value.status_code == 404
        # Card should still exist in WS_A
        assert get_card(WS_A, created.id).id == created.id

    def test_delete_card_nonexistent_returns_404(self):
        with pytest.raises(HTTPException) as exc_info:
            delete_card(WS_A, "card-ghost")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation (Req 3.4, 3.5, 3.6)
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Validates: Requirements 3.4, 3.5, 3.6"""

    def test_operations_across_workspaces_are_isolated(self):
        """Full lifecycle: cards in WS_A are invisible to WS_B."""
        card_a = create_card(WS_A, _make_card(last4="4444"))
        card_b = create_card(WS_B, _make_card(last4="5555"))

        # List isolation
        assert len(list_cards(WS_A)) == 1
        assert len(list_cards(WS_B)) == 1

        # Get isolation
        with pytest.raises(HTTPException):
            get_card(WS_B, card_a.id)
        with pytest.raises(HTTPException):
            get_card(WS_A, card_b.id)

        # Update isolation
        with pytest.raises(HTTPException):
            update_card(WS_B, card_a.id, CardUpdate(owner="Evil"))

        # Delete isolation
        with pytest.raises(HTTPException):
            delete_card(WS_B, card_a.id)

        # Original card untouched
        assert get_card(WS_A, card_a.id).owner == "Alice"
