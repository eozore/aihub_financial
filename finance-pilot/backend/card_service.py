"""Card management service — CRUD operations with tenant isolation.

Supports both SQLite (local dev, USE_SQLITE=true) and Firestore (production).
Every operation enforces tenant isolation by filtering on ``workspace_id``.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import os
import re
import uuid
from typing import List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, field_validator

from helpers import utc_now_iso

USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() == "true"
CARDS_COLLECTION = "cards"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CardCreate(BaseModel):
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
    owner: Optional[str] = None
    label: Optional[str] = None
    card_type: Optional[Literal["individual", "shared"]] = None
    bank: Optional[str] = None
    is_active: Optional[bool] = None


class CardResponse(BaseModel):
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

def _dict_to_card(d: dict) -> CardResponse:
    return CardResponse(
        id=d["id"],
        workspace_id=d["workspace_id"],
        owner=d["owner"],
        last4=d["last4"],
        label=d.get("label"),
        card_type=d["card_type"],
        bank=d.get("bank", "nubank"),
        is_active=bool(d.get("is_active", True)),
        created_at=str(d.get("created_at", "")),
        updated_at=str(d.get("updated_at", "")),
    )


def _get_firestore():
    """Return the Firestore client from the already-initialised app module."""
    try:
        from google.cloud import firestore
        import os as _os
        return firestore.Client(project=_os.environ.get("PROJECT_ID", "aifin-project"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SQLite CRUD
# ---------------------------------------------------------------------------

def _sqlite_create(workspace_id: str, data: CardCreate) -> CardResponse:
    from database import get_db_connection
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM cards WHERE workspace_id = ? AND last4 = ?", (workspace_id, data.last4))
        if c.fetchone():
            raise HTTPException(status_code=409, detail=f"Card with last4 '{data.last4}' already exists in this workspace")
        now = utc_now_iso()
        card_id = f"card-{uuid.uuid4().hex[:16]}"
        c.execute(
            "INSERT INTO cards (id, workspace_id, owner, last4, label, card_type, bank, is_active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
            (card_id, workspace_id, data.owner, data.last4, data.label, data.card_type, data.bank, now, now),
        )
        conn.commit()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        return _dict_to_card(dict(c.fetchone()))
    finally:
        conn.close()


def _sqlite_list(workspace_id: str) -> List[CardResponse]:
    from database import get_db_connection
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM cards WHERE workspace_id = ? ORDER BY created_at ASC", (workspace_id,))
        return [_dict_to_card(dict(r)) for r in c.fetchall()]
    finally:
        conn.close()


def _sqlite_get(workspace_id: str, card_id: str) -> CardResponse:
    from database import get_db_connection
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Card not found")
        d = dict(row)
        if d["workspace_id"] != workspace_id:
            raise HTTPException(status_code=404, detail="Card not found")
        return _dict_to_card(d)
    finally:
        conn.close()


def _sqlite_update(workspace_id: str, card_id: str, data: CardUpdate) -> CardResponse:
    from database import get_db_connection
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Card not found")
        existing = dict(row)
        if existing["workspace_id"] != workspace_id:
            raise HTTPException(status_code=404, detail="Card not found")
        now = utc_now_iso()
        c.execute(
            "UPDATE cards SET owner=?, label=?, card_type=?, bank=?, is_active=?, updated_at=? WHERE id=? AND workspace_id=?",
            (
                data.owner if data.owner is not None else existing["owner"],
                data.label if data.label is not None else existing.get("label"),
                data.card_type if data.card_type is not None else existing["card_type"],
                data.bank if data.bank is not None else existing["bank"],
                (1 if data.is_active else 0) if data.is_active is not None else existing["is_active"],
                now, card_id, workspace_id,
            ),
        )
        conn.commit()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        return _dict_to_card(dict(c.fetchone()))
    finally:
        conn.close()


def _sqlite_delete(workspace_id: str, card_id: str) -> None:
    from database import get_db_connection
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Card not found")
        if dict(row)["workspace_id"] != workspace_id:
            raise HTTPException(status_code=404, detail="Card not found")
        c.execute("DELETE FROM cards WHERE id = ? AND workspace_id = ?", (card_id, workspace_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Firestore CRUD
# ---------------------------------------------------------------------------

def _fs_create(workspace_id: str, data: CardCreate) -> CardResponse:
    db = _get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Check uniqueness
    existing = list(
        db.collection(CARDS_COLLECTION)
        .where("workspace_id", "==", workspace_id)
        .where("last4", "==", data.last4)
        .limit(1)
        .stream()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Card with last4 '{data.last4}' already exists in this workspace")

    now = utc_now_iso()
    card_id = f"card-{uuid.uuid4().hex[:16]}"
    payload = {
        "id": card_id,
        "workspace_id": workspace_id,
        "owner": data.owner,
        "last4": data.last4,
        "label": data.label,
        "card_type": data.card_type,
        "bank": data.bank,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    db.collection(CARDS_COLLECTION).document(card_id).set(payload)
    return _dict_to_card(payload)


def _fs_list(workspace_id: str) -> List[CardResponse]:
    db = _get_firestore()
    if db is None:
        return []
    docs = (
        db.collection(CARDS_COLLECTION)
        .where("workspace_id", "==", workspace_id)
        .stream()
    )
    cards = [_dict_to_card({**doc.to_dict(), "id": doc.id}) for doc in docs]
    cards.sort(key=lambda c: c.created_at)
    return cards


def _fs_get(workspace_id: str, card_id: str) -> CardResponse:
    db = _get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    doc = db.collection(CARDS_COLLECTION).document(card_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Card not found")
    d = {**doc.to_dict(), "id": doc.id}
    if d["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Card not found")
    return _dict_to_card(d)


def _fs_update(workspace_id: str, card_id: str, data: CardUpdate) -> CardResponse:
    db = _get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    doc_ref = db.collection(CARDS_COLLECTION).document(card_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Card not found")
    existing = {**doc.to_dict(), "id": doc.id}
    if existing["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Card not found")

    now = utc_now_iso()
    updates: dict = {"updated_at": now}
    if data.owner is not None:
        updates["owner"] = data.owner
    if data.label is not None:
        updates["label"] = data.label
    if data.card_type is not None:
        updates["card_type"] = data.card_type
    if data.bank is not None:
        updates["bank"] = data.bank
    if data.is_active is not None:
        updates["is_active"] = data.is_active

    doc_ref.update(updates)
    updated = {**existing, **updates}
    return _dict_to_card(updated)


def _fs_delete(workspace_id: str, card_id: str) -> None:
    db = _get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    doc = db.collection(CARDS_COLLECTION).document(card_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Card not found")
    if doc.to_dict().get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Card not found")
    db.collection(CARDS_COLLECTION).document(card_id).delete()


# ---------------------------------------------------------------------------
# Public API — routes to SQLite or Firestore based on USE_SQLITE
# ---------------------------------------------------------------------------

def create_card(workspace_id: str, data: CardCreate) -> CardResponse:
    return _sqlite_create(workspace_id, data) if USE_SQLITE else _fs_create(workspace_id, data)


def list_cards(workspace_id: str) -> List[CardResponse]:
    return _sqlite_list(workspace_id) if USE_SQLITE else _fs_list(workspace_id)


def get_card(workspace_id: str, card_id: str) -> CardResponse:
    return _sqlite_get(workspace_id, card_id) if USE_SQLITE else _fs_get(workspace_id, card_id)


def update_card(workspace_id: str, card_id: str, data: CardUpdate) -> CardResponse:
    return _sqlite_update(workspace_id, card_id, data) if USE_SQLITE else _fs_update(workspace_id, card_id, data)


def delete_card(workspace_id: str, card_id: str) -> None:
    return _sqlite_delete(workspace_id, card_id) if USE_SQLITE else _fs_delete(workspace_id, card_id)
