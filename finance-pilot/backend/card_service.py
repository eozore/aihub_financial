"""Card management service — CRUD operations with tenant isolation.

Provides business logic for creating, listing, reading, updating and deleting
payment cards within a workspace.  Every operation enforces tenant isolation by
filtering on ``workspace_id``.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import re
import uuid
from typing import List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, field_validator

from database import get_db_connection
from helpers import utc_now_iso


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CardCreate(BaseModel):
    """Payload for creating a new card."""

    owner: str
    last4: str
    label: Optional[str] = None
    card_type: Literal["individual", "shared"]
    bank: str = "nubank"

    @field_validator("last4")
    @classmethod
    def validate_last4(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}", v):
            raise ValueError("last4 must be exactly 4 numeric digits")
        return v


class CardUpdate(BaseModel):
    """Payload for updating an existing card — all fields optional."""

    owner: Optional[str] = None
    label: Optional[str] = None
    card_type: Optional[Literal["individual", "shared"]] = None
    bank: Optional[str] = None
    is_active: Optional[bool] = None


class CardResponse(BaseModel):
    """Serialised card returned to the client."""

    id: str
    workspace_id: str
    owner: str
    last4: str
    label: Optional[str]
    card_type: Literal["individual", "shared"]
    bank: str
    is_active: bool
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_card(row) -> CardResponse:
    """Convert a sqlite3.Row (or dict) to a CardResponse."""
    d = dict(row)
    return CardResponse(
        id=d["id"],
        workspace_id=d["workspace_id"],
        owner=d["owner"],
        last4=d["last4"],
        label=d.get("label"),
        card_type=d["card_type"],
        bank=d["bank"],
        is_active=bool(d["is_active"]),
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
    )


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def create_card(workspace_id: str, data: CardCreate) -> CardResponse:
    """Create a new card in the given workspace.

    Raises:
        HTTPException 409 — if a card with the same ``last4`` already exists
            in the workspace.
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()

        # Check uniqueness of last4 within the workspace
        c.execute(
            "SELECT id FROM cards WHERE workspace_id = ? AND last4 = ?",
            (workspace_id, data.last4),
        )
        if c.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Card with last4 '{data.last4}' already exists in this workspace",
            )

        now = utc_now_iso()
        card_id = f"card-{uuid.uuid4().hex[:16]}"

        c.execute(
            """
            INSERT INTO cards (id, workspace_id, owner, last4, label, card_type, bank, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                card_id,
                workspace_id,
                data.owner,
                data.last4,
                data.label,
                data.card_type,
                data.bank,
                now,
                now,
            ),
        )
        conn.commit()

        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = c.fetchone()
        return _row_to_card(row)
    finally:
        conn.close()


def list_cards(workspace_id: str) -> List[CardResponse]:
    """Return all cards belonging to *workspace_id*."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM cards WHERE workspace_id = ? ORDER BY created_at ASC",
            (workspace_id,),
        )
        return [_row_to_card(row) for row in c.fetchall()]
    finally:
        conn.close()


def get_card(workspace_id: str, card_id: str) -> CardResponse:
    """Fetch a single card, enforcing tenant isolation.

    Raises:
        HTTPException 404 — card not found or belongs to another workspace.
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = c.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Card not found")

        if dict(row)["workspace_id"] != workspace_id:
            # Don't reveal that the card exists in another workspace
            raise HTTPException(status_code=404, detail="Card not found")

        return _row_to_card(row)
    finally:
        conn.close()


def update_card(workspace_id: str, card_id: str, data: CardUpdate) -> CardResponse:
    """Update a card, enforcing tenant isolation.

    Raises:
        HTTPException 404 — card not found or belongs to another workspace.
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = c.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Card not found")

        existing = dict(row)
        if existing["workspace_id"] != workspace_id:
            raise HTTPException(status_code=404, detail="Card not found")

        now = utc_now_iso()
        new_owner = data.owner if data.owner is not None else existing["owner"]
        new_label = data.label if data.label is not None else existing.get("label")
        new_card_type = data.card_type if data.card_type is not None else existing["card_type"]
        new_bank = data.bank if data.bank is not None else existing["bank"]
        new_is_active = (
            (1 if data.is_active else 0)
            if data.is_active is not None
            else existing["is_active"]
        )

        c.execute(
            """
            UPDATE cards
            SET owner = ?, label = ?, card_type = ?, bank = ?, is_active = ?, updated_at = ?
            WHERE id = ? AND workspace_id = ?
            """,
            (new_owner, new_label, new_card_type, new_bank, new_is_active, now, card_id, workspace_id),
        )
        conn.commit()

        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        return _row_to_card(c.fetchone())
    finally:
        conn.close()


def delete_card(workspace_id: str, card_id: str) -> None:
    """Delete a card, enforcing tenant isolation.

    Raises:
        HTTPException 404 — card not found or belongs to another workspace.
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = c.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Card not found")

        if dict(row)["workspace_id"] != workspace_id:
            raise HTTPException(status_code=404, detail="Card not found")

        c.execute(
            "DELETE FROM cards WHERE id = ? AND workspace_id = ?",
            (card_id, workspace_id),
        )
        conn.commit()
    finally:
        conn.close()
