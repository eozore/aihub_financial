from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage, bigquery, firestore
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
import datetime
import os
import json
import sqlite3
import re
import uuid
import hashlib
import logging
from pydantic import BaseModel
from typing import Optional, List, Literal
from processor import TransactionProcessor, TABLE_GOLD, TABLE_SILVER
from pathlib import Path
from config import (
    PROJECT_ID, FIREBASE_PROJECT_ID, BUCKET_RAW, FIRESTORE_COLLECTION,
    TENANT_HEADER_NAME, DEFAULT_TENANT_ID, TENANT_REQUIRED,
    USERS_COLLECTION, WORKSPACES_COLLECTION, WORKSPACE_MEMBERS_COLLECTION,
    WORKSPACE_INVITES_COLLECTION, NET_WORTH_COLLECTION, CURRENT_ACCOUNT_COLLECTION,
    PREMIUM_EMAILS, ADMIN_EMAILS, PLAN_LIMITS,
    CORS_ORIGINS, CORS_ALLOWED_METHODS, CORS_ALLOWED_HEADERS,
    USE_SQLITE, USE_MOCK, MOCK_DATA_PATH, REQUIRE_AUTH_FOR_DATA,
)

# --- Dedicated module imports (deduplication - Phase 5) ---
from helpers import (
    normalize_owner as _normalize_owner,
    parse_br_money as _parse_br_money,
    parse_br_percent as _parse_br_percent,
    parse_month_ref as _parse_month_ref,
    parse_ddmmyyyy_to_iso as _parse_ddmmyyyy_to_iso,
    parse_signed_amount as _parse_signed_amount,
    category_for_current_account as _category_for_current_account,
    utc_now_iso as _utc_now_iso,
    normalize_plan as _normalize_plan,
    plan_limits as _plan_limits,
    normalize_email as _normalize_email,
)
from auth import (
    sanitize_tenant_id as _sanitize_tenant_id,
    extract_tenant_from_claims as _extract_tenant_from_claims,
    require_authenticated_user as _require_authenticated_user,
    require_data_access as _require_data_access,
    require_tenant_id as _require_tenant_id,
)
from models import (
    TenantContext,
    TransactionUpdate,
    TransactionCreate,
    PlanUpdate,
    UserProfileUpdate,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceInviteCreate,
    NetWorthRowUpdate,
)
from upload_validation import validate_and_read_upload as _validate_and_read_upload, detect_file_type as _detect_file_type
from extraction_service import ExtractionService as _ExtractionService
from card_service import (
    CardCreate as _CardCreate,
    CardUpdate as _CardUpdate,
    CardResponse as _CardResponse,
    create_card as _create_card,
    list_cards as _list_cards,
    update_card as _update_card,
    delete_card as _delete_card,
)
from categories import (
    create_rule as _create_rule,
    list_rules as _list_rules,
    update_rule as _update_rule,
    delete_rule as _delete_rule,
)
from billing_service import (
    BillingService as _BillingService,
    CreateSubscriptionRequest as _CreateSubscriptionRequest,
    CreateSubscriptionResponse as _CreateSubscriptionResponse,
    BillingStatusResponse as _BillingStatusResponse,
)

logger = logging.getLogger("finance-pilot")

# ---------------------------------------------------------------------------
# Singleton ExtractionService instance (in-memory cache across requests)
# ---------------------------------------------------------------------------
_extraction_service = _ExtractionService()

# ---------------------------------------------------------------------------
# Singleton BillingService instance
# ---------------------------------------------------------------------------
_billing_service = _BillingService()


# ---------------------------------------------------------------------------
# Upload preview / confirm Pydantic models (Task 10.2 / 10.3)
# ---------------------------------------------------------------------------

class PreviewTransaction(BaseModel):
    date: str
    card_last4: Optional[str] = None
    description: str
    amount: float
    is_refund: bool = False
    suggested_category: str
    suggested_type: Optional[str] = None
    needs_review: bool = False


class UploadPreviewResponse(BaseModel):
    file_hash: str
    statement_type: Literal["credit_card", "current_account"]
    bank: str
    holder_name: str
    period_start: str
    period_end: str
    total_amount: float
    transactions: List[PreviewTransaction]
    unregistered_cards: List[str]


class ConfirmedTransaction(BaseModel):
    date: str
    card_last4: Optional[str] = None
    description: str
    amount: float
    is_refund: bool = False
    category: str
    owner: str


class UploadConfirmRequest(BaseModel):
    file_hash: str
    transactions: List[ConfirmedTransaction]

def _parse_email_list(value: str) -> List[str]:
    return [
        item.strip().lower()
        for item in (value or "").split(",")
        if item.strip()
    ]


app = FastAPI(
    title="Finance Pilot API",
    description="Personal finance management API with multi-tenant workspace support.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=CORS_ALLOWED_METHODS,
    allow_headers=CORS_ALLOWED_HEADERS,
)

from rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

GOOGLE_AUTH_REQUEST = google_requests.Request()

# Initialize clients
db_firestore = None
bq_client = None

if USE_SQLITE:
    logger.info("Using Local SQLite Database")
    from database import get_db_connection, init_db
else:
    try:
        # Firestore for CRUD operations
        db_firestore = firestore.Client(project=PROJECT_ID)
        logger.info("Firestore client initialized for project: %s", PROJECT_ID)
        
        # BigQuery for analytics
        bq_client = bigquery.Client(project=PROJECT_ID)
        logger.info("BigQuery client initialized for project: %s", PROJECT_ID)
    except Exception as e:
        logger.warning("Could not initialize cloud clients: %s", e)
        USE_MOCK = True


def get_tenant_context(request: Request) -> TenantContext:
    header_tenant = _sanitize_tenant_id(request.headers.get(TENANT_HEADER_NAME))
    token_tenant = None
    user_id = None
    user_email = None

    auth_header = request.headers.get("Authorization")
    if auth_header:
        try:
            scheme, token = auth_header.split(" ", 1)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid Authorization header format") from exc

        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status_code=401, detail="Invalid Authorization header")

        try:
            claims = google_id_token.verify_firebase_token(
                token.strip(),
                GOOGLE_AUTH_REQUEST,
                audience=FIREBASE_PROJECT_ID,
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid Firebase token") from exc

        if not claims:
            raise HTTPException(status_code=401, detail="Invalid Firebase token")

        user_id = claims.get("uid") or claims.get("sub")
        user_email = claims.get("email")
        token_tenant = _sanitize_tenant_id(_extract_tenant_from_claims(claims))

    if token_tenant and header_tenant and token_tenant != header_tenant:
        raise HTTPException(status_code=403, detail="Tenant mismatch between token and header")

    tenant_id = None
    if user_id:
        profile = ensure_user_profile(user_id=user_id, email=user_email)
        workspaces = _list_user_workspaces(user_id)
        workspace_ids = {ws["id"] for ws in workspaces}
        requested_workspace = token_tenant or header_tenant

        if requested_workspace:
            if requested_workspace in workspace_ids:
                tenant_id = requested_workspace
            else:
                fallback_workspace_id = profile.get("active_workspace_id")
                if fallback_workspace_id not in workspace_ids:
                    fallback_workspace_id = workspaces[0]["id"] if workspaces else None

                if not fallback_workspace_id:
                    raise HTTPException(status_code=403, detail="User does not have access to this workspace")

                tenant_id = fallback_workspace_id

            if profile.get("active_workspace_id") != tenant_id:
                _upsert_user_profile(
                    user_id=user_id,
                    email=user_email,
                    plan_type=profile.get("plan_type", "free"),
                    active_workspace_id=tenant_id,
                )
        else:
            active_workspace_id = profile.get("active_workspace_id")
            if active_workspace_id and active_workspace_id in workspace_ids:
                tenant_id = active_workspace_id
            elif workspaces:
                tenant_id = workspaces[0]["id"]
                _upsert_user_profile(
                    user_id=user_id,
                    email=user_email,
                    plan_type=profile.get("plan_type", "free"),
                    active_workspace_id=tenant_id,
                )

    if not tenant_id:
        tenant_id = token_tenant or header_tenant or _sanitize_tenant_id(DEFAULT_TENANT_ID)

    if TENANT_REQUIRED and not tenant_id:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant is required. Provide {TENANT_HEADER_NAME} or configure DEFAULT_TENANT_ID.",
        )

    return TenantContext(
        tenant_id=tenant_id or "default",
        user_id=user_id,
        user_email=user_email,
    )

def ensure_sqlite_tenant_column():
    if not USE_SQLITE:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(transactions_gold)")
    cols = {row[1] for row in c.fetchall()}

    if "tenant_id" not in cols:
        c.execute("ALTER TABLE transactions_gold ADD COLUMN tenant_id TEXT")

    c.execute(
        "UPDATE transactions_gold SET tenant_id = ? WHERE tenant_id IS NULL OR tenant_id = ''",
        (DEFAULT_TENANT_ID,),
    )
    conn.commit()
    conn.close()

def ensure_sqlite_financial_tables():
    if not USE_SQLITE:
        return

    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='net_worth_monthly'")
    has_net_worth_table = c.fetchone() is not None
    if has_net_worth_table:
        c.execute("PRAGMA table_info(net_worth_monthly)")
        net_worth_info = c.fetchall()
        pk_columns = [row[1] for row in net_worth_info if row[5] > 0]
        needs_migration = pk_columns == ["tenant_id", "month_ref"]
        if needs_migration:
            c.execute("ALTER TABLE net_worth_monthly RENAME TO net_worth_monthly_legacy")
            c.execute(
                """
                CREATE TABLE net_worth_monthly (
                    tenant_id TEXT NOT NULL,
                    owner TEXT NOT NULL DEFAULT 'Victor',
                    month_ref TEXT NOT NULL,
                    salary REAL,
                    other_income REAL,
                    income_total REAL,
                    expense_fixed REAL,
                    expense_variable REAL,
                    expense_total REAL,
                    cash_end_balance REAL,
                    net_worth_total REAL,
                    debt_ratio REAL,
                    notes TEXT,
                    updated_at TIMESTAMP
                )
                """
            )
            c.execute(
                """
                INSERT INTO net_worth_monthly (
                    tenant_id,
                    owner,
                    month_ref,
                    salary,
                    other_income,
                    income_total,
                    expense_fixed,
                    expense_variable,
                    expense_total,
                    cash_end_balance,
                    net_worth_total,
                    debt_ratio,
                    notes,
                    updated_at
                )
                SELECT
                    tenant_id,
                    'Victor' AS owner,
                    month_ref,
                    salary,
                    other_income,
                    income_total,
                    expense_fixed,
                    expense_variable,
                    expense_total,
                    cash_end_balance,
                    net_worth_total,
                    debt_ratio,
                    notes,
                    updated_at
                FROM net_worth_monthly_legacy
                """
            )
            c.execute("DROP TABLE net_worth_monthly_legacy")
    else:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS net_worth_monthly (
                tenant_id TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT 'Victor',
                month_ref TEXT NOT NULL,
                salary REAL,
                other_income REAL,
                income_total REAL,
                expense_fixed REAL,
                expense_variable REAL,
                expense_total REAL,
                cash_end_balance REAL,
                net_worth_total REAL,
                debt_ratio REAL,
                notes TEXT,
                updated_at TIMESTAMP
            )
            """
        )
    c.execute("PRAGMA table_info(net_worth_monthly)")
    net_worth_cols = {row[1] for row in c.fetchall()}
    if "owner" not in net_worth_cols:
        c.execute("ALTER TABLE net_worth_monthly ADD COLUMN owner TEXT NOT NULL DEFAULT 'Victor'")

    c.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_net_worth_tenant_owner_month
        ON net_worth_monthly (tenant_id, owner, month_ref)
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS current_account_movements (
            tenant_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            movement_id TEXT NOT NULL,
            date DATE,
            month_ref TEXT,
            amount_signed REAL,
            description TEXT,
            source_file TEXT,
            is_card_invoice_payment INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP
        )
        """
    )
    c.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_current_account_movement_id
        ON current_account_movements (tenant_id, owner, movement_id)
        """
    )

    conn.commit()
    conn.close()

if USE_SQLITE:
    init_db()
    ensure_sqlite_tenant_column()
    ensure_sqlite_financial_tables()

    # Run reversible schema migrations (replaces inline ensure_sqlite_* for SaaS tables).
    from migrations.runner import run_pending as _run_pending_migrations
    _mig_conn = get_db_connection()
    try:
        _applied = _run_pending_migrations(_mig_conn)
        if _applied:
            logger.info("Applied %d migration(s): %s", len(_applied), ", ".join(_applied))
    except Exception as _mig_exc:
        logger.error("Migration runner failed: %s", _mig_exc)
    finally:
        _mig_conn.close()

def ensure_bigquery_tenant_columns():
    if USE_SQLITE or USE_MOCK or not bq_client:
        return

    for table_name in [TABLE_GOLD, TABLE_SILVER]:
        try:
            table = bq_client.get_table(table_name)
            field_names = {field.name for field in table.schema}
            if "tenant_id" in field_names:
                continue

            table.schema = list(table.schema) + [bigquery.SchemaField("tenant_id", "STRING")]
            bq_client.update_table(table, ["schema"])
            logger.info("Added tenant_id column to %s", table_name)
        except Exception as exc:
            logger.warning("Could not ensure tenant_id column on %s: %s", table_name, exc)

ensure_bigquery_tenant_columns()

def ensure_sqlite_workspace_tables():
    if not USE_SQLITE:
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT,
            plan_type TEXT NOT NULL DEFAULT 'free',
            is_admin INTEGER NOT NULL DEFAULT 0,
            active_workspace_id TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            member_limit INTEGER,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_members (
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP,
            PRIMARY KEY (workspace_id, user_id)
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_invites (
            id TEXT PRIMARY KEY,
            workspace_id TEXT,
            inviter_user_id TEXT NOT NULL,
            invitee_email TEXT NOT NULL,
            invite_mode TEXT NOT NULL,
            target_workspace_name TEXT,
            status TEXT NOT NULL,
            created_at TIMESTAMP,
            accepted_at TIMESTAMP
        )
        """
    )
    c.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in c.fetchall()}
    if "is_admin" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()

def _sqlite_row_to_dict(row):
    if row is None:
        return None
    return dict(row)

def _get_user_profile(user_id: str):
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = _sqlite_row_to_dict(c.fetchone())
        conn.close()
        if row is not None:
            row["is_admin"] = bool(row.get("is_admin"))
        return row

    if not db_firestore:
        return None
    doc = db_firestore.collection(USERS_COLLECTION).document(user_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["user_id"] = user_id
    data["is_admin"] = bool(data.get("is_admin", False))
    return data

def _upsert_user_profile(
    user_id: str,
    email: Optional[str] = None,
    plan_type: Optional[str] = None,
    is_admin: Optional[bool] = None,
    active_workspace_id: Optional[str] = None,
    display_name: Optional[str] = None,
    short_name: Optional[str] = None,
    photo_url: Optional[str] = None,
    birth_date: Optional[str] = None,  # YYYY-MM-DD
    cpf: Optional[str] = None,
    address: Optional[str] = None,
):
    existing = _get_user_profile(user_id) or {}
    now = _utc_now_iso()
    payload = {
        "user_id": user_id,
        "email": email if email is not None else existing.get("email"),
        "plan_type": _normalize_plan(plan_type if plan_type is not None else existing.get("plan_type", "free")),
        "is_admin": bool(is_admin if is_admin is not None else existing.get("is_admin", False)),
        "active_workspace_id": active_workspace_id if active_workspace_id is not None else existing.get("active_workspace_id"),
        "display_name": display_name if display_name is not None else existing.get("display_name"),
        "short_name": short_name if short_name is not None else existing.get("short_name"),
        "photo_url": photo_url if photo_url is not None else existing.get("photo_url"),
        "birth_date": birth_date if birth_date is not None else existing.get("birth_date"),
        "cpf": cpf if cpf is not None else existing.get("cpf"),
        "address": address if address is not None else existing.get("address"),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO users
            (user_id, email, plan_type, is_admin, active_workspace_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["user_id"],
                payload["email"],
                payload["plan_type"],
                1 if payload["is_admin"] else 0,
                payload["active_workspace_id"],
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        conn.commit()
        conn.close()
        return payload

    if not db_firestore:
        return payload
    db_firestore.collection(USERS_COLLECTION).document(user_id).set(payload)
    return payload

def _get_workspace(workspace_id: str):
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        row = _sqlite_row_to_dict(c.fetchone())
        conn.close()
        return row

    if not db_firestore:
        return None
    doc = db_firestore.collection(WORKSPACES_COLLECTION).document(workspace_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["id"] = workspace_id
    return data

def _create_workspace(workspace_id: str, name: str, owner_user_id: str, member_limit: Optional[int] = None):
    now = _utc_now_iso()
    payload = {
        "id": workspace_id,
        "name": name.strip(),
        "owner_user_id": owner_user_id,
        "member_limit": member_limit,
        "created_at": now,
        "updated_at": now,
    }

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO workspaces
            (id, name, owner_user_id, member_limit, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["name"],
                payload["owner_user_id"],
                payload["member_limit"],
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        conn.commit()
        conn.close()
        return payload

    if db_firestore:
        db_firestore.collection(WORKSPACES_COLLECTION).document(workspace_id).set(payload)
    return payload


def _update_workspace(workspace_id: str, *, name: Optional[str] = None, member_limit: Optional[int] = None):
    workspace = _get_workspace(workspace_id)
    if not workspace:
        return None

    now = _utc_now_iso()
    next_name = name.strip() if isinstance(name, str) else workspace.get("name")
    next_member_limit = member_limit if member_limit is not None else workspace.get("member_limit")

    payload = {
        "id": workspace_id,
        "name": next_name,
        "owner_user_id": workspace.get("owner_user_id"),
        "member_limit": next_member_limit,
        "created_at": workspace.get("created_at") or now,
        "updated_at": now,
    }

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            UPDATE workspaces
            SET name = ?, member_limit = ?, updated_at = ?
            WHERE id = ?
            """,
            (payload["name"], payload["member_limit"], payload["updated_at"], workspace_id),
        )
        conn.commit()
        conn.close()
        return payload

    if db_firestore:
        db_firestore.collection(WORKSPACES_COLLECTION).document(workspace_id).update(
            {
                "name": payload["name"],
                "member_limit": payload["member_limit"],
                "updated_at": payload["updated_at"],
            }
        )
    return payload

def _get_workspace_member(workspace_id: str, user_id: str):
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        )
        row = _sqlite_row_to_dict(c.fetchone())
        conn.close()
        return row

    if not db_firestore:
        return None
    doc_id = f"{workspace_id}:{user_id}"
    doc = db_firestore.collection(WORKSPACE_MEMBERS_COLLECTION).document(doc_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["id"] = doc_id
    return data

def _add_workspace_member(workspace_id: str, user_id: str, role: str):
    existing = _get_workspace_member(workspace_id, user_id)
    if existing:
        return existing

    payload = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role": role,
        "created_at": _utc_now_iso(),
    }

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO workspace_members
            (workspace_id, user_id, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (payload["workspace_id"], payload["user_id"], payload["role"], payload["created_at"]),
        )
        conn.commit()
        conn.close()
        return payload

    if db_firestore:
        doc_id = f"{workspace_id}:{user_id}"
        db_firestore.collection(WORKSPACE_MEMBERS_COLLECTION).document(doc_id).set(payload)
    return payload


def _delete_workspace_member(workspace_id: str, user_id: str):
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "DELETE FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        )
        deleted = c.rowcount
        conn.commit()
        conn.close()
        return deleted > 0

    if db_firestore:
        doc_id = f"{workspace_id}:{user_id}"
        db_firestore.collection(WORKSPACE_MEMBERS_COLLECTION).document(doc_id).delete()
        return True

    return False

def _count_workspace_members(workspace_id: str) -> int:
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id = ?", (workspace_id,))
        count = c.fetchone()[0]
        conn.close()
        return count

    if not db_firestore:
        return 0
    docs = db_firestore.collection(WORKSPACE_MEMBERS_COLLECTION).where("workspace_id", "==", workspace_id).stream()
    return sum(1 for _ in docs)

def _list_workspace_members(workspace_id: str) -> List[dict]:
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT m.workspace_id, m.user_id, m.role, m.created_at, u.email
            FROM workspace_members m
            LEFT JOIN users u ON u.user_id = m.user_id
            WHERE m.workspace_id = ?
            ORDER BY m.created_at ASC
            """,
            (workspace_id,),
        )
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return rows

    if not db_firestore:
        return []

    rows = []
    docs = db_firestore.collection(WORKSPACE_MEMBERS_COLLECTION).where("workspace_id", "==", workspace_id).stream()
    for doc in docs:
        row = doc.to_dict() or {}
        profile = _get_user_profile(row.get("user_id"))
        row["email"] = profile.get("email") if profile else None
        rows.append(row)
    rows.sort(key=lambda x: x.get("created_at") or "")
    return rows


def _get_workspace_owner_names(workspace_id: str) -> List[str]:
    """Return the display names of all members in a workspace.

    Priority: display_name → short_name → email → user_id → "unknown".
    This replaces the old static ``OWNERS`` list from config.py.
    """
    members = _list_workspace_members(workspace_id)
    names: List[str] = []
    for m in members:
        # Try display_name first, then short_name, then email, then user_id
        profile = _get_user_profile(m.get("user_id")) or {}
        name = (
            profile.get("display_name")
            or profile.get("short_name")
            or m.get("email")
            or m.get("user_id")
            or "unknown"
        )
        names.append(name)
    return names if names else ["default"]


def _list_user_workspaces(user_id: str) -> List[dict]:
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT w.id, w.name, w.owner_user_id, w.member_limit, w.created_at, w.updated_at, m.role
            FROM workspace_members m
            INNER JOIN workspaces w ON w.id = m.workspace_id
            WHERE m.user_id = ?
            ORDER BY w.created_at ASC
            """,
            (user_id,),
        )
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
    else:
        rows = []
        if db_firestore:
            member_docs = db_firestore.collection(WORKSPACE_MEMBERS_COLLECTION).where("user_id", "==", user_id).stream()
            for member_doc in member_docs:
                member_data = member_doc.to_dict() or {}
                workspace = _get_workspace(member_data.get("workspace_id"))
                if not workspace:
                    continue
                workspace["role"] = member_data.get("role")
                rows.append(workspace)

    for row in rows:
        row["member_count"] = _count_workspace_members(row["id"])
    return rows


def _delete_workspace(workspace_id: str):
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        deleted = c.rowcount
        c.execute("DELETE FROM workspace_members WHERE workspace_id = ?", (workspace_id,))
        conn.commit()
        conn.close()
        return deleted > 0

    if db_firestore:
        workspace_member_docs = db_firestore.collection(WORKSPACE_MEMBERS_COLLECTION).where(
            "workspace_id", "==", workspace_id
        ).stream()
        for member_doc in workspace_member_docs:
            member_doc.reference.delete()
        db_firestore.collection(WORKSPACES_COLLECTION).document(workspace_id).delete()
        return True

    return False


def _personal_workspace_id_for_user(user_id: str) -> str:
    return f"ws-u-{uuid.uuid5(uuid.NAMESPACE_DNS, user_id).hex[:12]}"

def _create_workspace_invite(
    workspace_id: Optional[str],
    inviter_user_id: str,
    invitee_email: str,
    invite_mode: str,
    target_workspace_name: Optional[str] = None,
):
    invite_id = f"inv-{uuid.uuid4().hex[:16]}"
    payload = {
        "id": invite_id,
        "workspace_id": workspace_id,
        "inviter_user_id": inviter_user_id,
        "invitee_email": invitee_email.strip().lower(),
        "invite_mode": invite_mode,
        "target_workspace_name": target_workspace_name,
        "status": "pending",
        "created_at": _utc_now_iso(),
        "accepted_at": None,
    }

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO workspace_invites
            (id, workspace_id, inviter_user_id, invitee_email, invite_mode, target_workspace_name, status, created_at, accepted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["workspace_id"],
                payload["inviter_user_id"],
                payload["invitee_email"],
                payload["invite_mode"],
                payload["target_workspace_name"],
                payload["status"],
                payload["created_at"],
                payload["accepted_at"],
            ),
        )
        conn.commit()
        conn.close()
        return payload

    if db_firestore:
        db_firestore.collection(WORKSPACE_INVITES_COLLECTION).document(invite_id).set(payload)
    return payload

def _get_workspace_invite(invite_id: str):
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM workspace_invites WHERE id = ?", (invite_id,))
        row = _sqlite_row_to_dict(c.fetchone())
        conn.close()
        return row

    if not db_firestore:
        return None
    doc = db_firestore.collection(WORKSPACE_INVITES_COLLECTION).document(invite_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["id"] = invite_id
    return data

def _update_workspace_invite(invite_id: str, status: str, accepted_at: Optional[str] = None):
    invite = _get_workspace_invite(invite_id)
    if not invite:
        return None

    invite["status"] = status
    invite["accepted_at"] = accepted_at

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE workspace_invites SET status = ?, accepted_at = ? WHERE id = ?",
            (status, accepted_at, invite_id),
        )
        conn.commit()
        conn.close()
        return invite

    if db_firestore:
        db_firestore.collection(WORKSPACE_INVITES_COLLECTION).document(invite_id).update(
            {"status": status, "accepted_at": accepted_at}
        )
    return invite

def _list_pending_invites_for_email(email: str) -> List[dict]:
    normalized_email = email.strip().lower()
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM workspace_invites
            WHERE invitee_email = ? AND status = 'pending'
            ORDER BY created_at DESC
            """,
            (normalized_email,),
        )
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return rows

    if not db_firestore:
        return []
    docs = db_firestore.collection(WORKSPACE_INVITES_COLLECTION).where("invitee_email", "==", normalized_email).where(
        "status", "==", "pending"
    ).stream()
    rows = [doc.to_dict() or {} for doc in docs]
    rows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return rows

def _list_sent_invites(inviter_user_id: str) -> List[dict]:
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM workspace_invites
            WHERE inviter_user_id = ?
            ORDER BY created_at DESC
            """,
            (inviter_user_id,),
        )
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return rows

    if not db_firestore:
        return []
    docs = db_firestore.collection(WORKSPACE_INVITES_COLLECTION).where("inviter_user_id", "==", inviter_user_id).stream()
    rows = [doc.to_dict() or {} for doc in docs]
    rows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return rows

def ensure_default_workspace_exists(owner_user_id: Optional[str] = None):
    workspace = _get_workspace(DEFAULT_TENANT_ID)
    if workspace:
        return workspace

    owner_id = owner_user_id or "legacy-owner"
    return _create_workspace(
        workspace_id=DEFAULT_TENANT_ID,
        name="Painel Principal",
        owner_user_id=owner_id,
        member_limit=2,
    )


def _tenant_has_data(tenant_id: Optional[str]) -> bool:
    if not tenant_id:
        return False

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT 1 FROM transactions_gold WHERE tenant_id = ? LIMIT 1",
            (tenant_id,),
        )
        has_data = c.fetchone() is not None
        conn.close()
        return has_data

    if USE_MOCK:
        mock_data = load_mock_data()
        return any((row.get("tenant_id") or DEFAULT_TENANT_ID) == tenant_id for row in mock_data)

    if not bq_client:
        return False

    query = f"""
        SELECT 1
        FROM `{TABLE_GOLD}`
        WHERE tenant_id = @tenant_id
        LIMIT 1
    """
    job = bq_client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id)]
        ),
    )
    return any(True for _ in job.result())


def _is_premium_email(email: Optional[str]) -> bool:
    return _normalize_email(email) in PREMIUM_EMAILS


def _is_admin_email(email: Optional[str]) -> bool:
    return _normalize_email(email) in ADMIN_EMAILS


def _can_auto_join_legacy(email: Optional[str]) -> bool:
    """Legacy auto-join is disabled — workspace membership is now managed explicitly."""
    return False


def _list_all_user_profiles() -> List[dict]:
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        for row in rows:
            row["is_admin"] = bool(row.get("is_admin"))
        return rows

    if not db_firestore:
        return []

    rows = []
    for doc in db_firestore.collection(USERS_COLLECTION).stream():
        data = doc.to_dict() or {}
        data["user_id"] = doc.id
        data["is_admin"] = bool(data.get("is_admin", False))
        rows.append(data)
    return rows


def bootstrap_configured_accounts():
    if not PREMIUM_EMAILS and not ADMIN_EMAILS:
        return

    default_workspace = ensure_default_workspace_exists()
    default_has_data = _tenant_has_data(DEFAULT_TENANT_ID)
    configured_emails = PREMIUM_EMAILS | ADMIN_EMAILS
    if not configured_emails:
        return

    for profile in _list_all_user_profiles():
        email = _normalize_email(profile.get("email"))
        if email not in configured_emails:
            continue

        user_id = profile["user_id"]
        current_plan = profile.get("plan_type", "free")
        desired_plan = "paid" if _is_premium_email(email) else current_plan
        desired_admin = bool(profile.get("is_admin")) or _is_admin_email(email)
        desired_active_workspace = profile.get("active_workspace_id")

        _upsert_user_profile(
            user_id=user_id,
            email=email or profile.get("email"),
            plan_type=desired_plan,
            is_admin=desired_admin,
            active_workspace_id=desired_active_workspace,
        )


def ensure_user_profile(user_id: str, email: Optional[str]) -> dict:
    normalized_email = _normalize_email(email)
    profile = _get_user_profile(user_id)
    desired_plan = "paid" if _is_premium_email(normalized_email) else "free"
    desired_admin = _is_admin_email(normalized_email)

    if not profile:
        profile = _upsert_user_profile(
            user_id=user_id,
            email=normalized_email or email,
            plan_type=desired_plan,
            is_admin=desired_admin,
        )
    elif email and profile.get("email") != email:
        profile = _upsert_user_profile(
            user_id=user_id,
            email=normalized_email or email,
            plan_type=profile.get("plan_type", "free"),
            is_admin=bool(profile.get("is_admin", False)) or desired_admin,
            active_workspace_id=profile.get("active_workspace_id"),
        )
    elif (
        _is_premium_email(normalized_email)
        and profile.get("plan_type") != "paid"
    ) or (_is_admin_email(normalized_email) and not profile.get("is_admin", False)):
        profile = _upsert_user_profile(
            user_id=user_id,
            email=normalized_email or profile.get("email"),
            plan_type="paid" if _is_premium_email(normalized_email) else profile.get("plan_type", "free"),
            is_admin=bool(profile.get("is_admin", False)) or _is_admin_email(normalized_email),
            active_workspace_id=profile.get("active_workspace_id"),
        )

    can_auto_join_legacy = _can_auto_join_legacy(normalized_email or profile.get("email"))
    if can_auto_join_legacy:
        ensure_default_workspace_exists(owner_user_id=user_id)
        legacy_membership = _get_workspace_member(DEFAULT_TENANT_ID, user_id)
        if not legacy_membership:
            legacy_members = _count_workspace_members(DEFAULT_TENANT_ID)
            role = "owner" if legacy_members == 0 else "member"
            _add_workspace_member(DEFAULT_TENANT_ID, user_id, role)

    workspaces = _list_user_workspaces(user_id)
    if not workspaces:
        active_workspace_id = None

        # Create a personal workspace for the user
        personal_workspace_id = _personal_workspace_id_for_user(user_id)
        personal_limit = _plan_limits(profile.get("plan_type", "free"))["max_members_per_workspace"]
        _create_workspace(
            workspace_id=personal_workspace_id,
            name="Meu Painel",
            owner_user_id=user_id,
            member_limit=personal_limit,
        )
        _add_workspace_member(personal_workspace_id, user_id, "owner")
        active_workspace_id = personal_workspace_id

        profile = _upsert_user_profile(
            user_id=user_id,
            email=normalized_email or email,
            plan_type=profile.get("plan_type", "free"),
            is_admin=bool(profile.get("is_admin", False)),
            active_workspace_id=active_workspace_id,
        )
        return profile

    workspace_ids = {ws["id"] for ws in workspaces}
    if not profile.get("active_workspace_id") or profile.get("active_workspace_id") not in workspace_ids:
        profile = _upsert_user_profile(
            user_id=user_id,
            email=profile.get("email"),
            plan_type=profile.get("plan_type", "free"),
            is_admin=bool(profile.get("is_admin", False)),
            active_workspace_id=workspaces[0]["id"],
        )

    return profile

if USE_SQLITE:
    ensure_sqlite_workspace_tables()

try:
    bootstrap_configured_accounts()
except Exception as exc:
    logger.warning("Failed to bootstrap configured accounts: %s", exc)

def load_mock_data() -> List[dict]:
    """Load mock data from JSON file and normalize it."""
    if not MOCK_DATA_PATH.exists():
        logger.warning("Mock data not found at %s", MOCK_DATA_PATH)
        return []
    
    with open(MOCK_DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Normalize data - parse dates and map legacy fields
    for tx in data:
        # Parse date from "DD/MM/YYYY HH:MM:SS" to "YYYY-MM-DD"
        if 'date' in tx and '/' in tx['date']:
            try:
                parts = tx['date'].split(' ')[0].split('/')
                tx['date'] = f"{parts[2]}-{parts[1]}-{parts[0]}"
            except:
                pass
        
        # Map type_legacy to type
        if 'type_legacy' in tx and 'type' not in tx:
            tx['type'] = 'Shared' if tx['type_legacy'] == 'Casal' else 'Individual'
        
        # Map group_legacy to category if category is empty
        if not tx.get('category') and tx.get('group_legacy'):
            tx['category'] = tx['group_legacy']
        
        # Create month_ref from date
        if 'date' in tx and '-' in tx['date']:
            tx['month_ref'] = tx['date'][:7]  # YYYY-MM
        
        # Normalize owner (Lala -> Larissa)
        if tx.get('owner') == 'Lala':
            tx['owner'] = 'Larissa'

        # Default tenant for legacy/mock records
        tx['tenant_id'] = tx.get('tenant_id') or DEFAULT_TENANT_ID
    
    return data


@app.get("/")
def read_root():
    mode = "sqlite" if USE_SQLITE else ("mock" if USE_MOCK else "bigquery")
    return {
        "status": "Finance API is running",
        "mode": mode,
        "tenant_header": TENANT_HEADER_NAME,
    }

@app.get("/owners")
def list_owners(tenant: TenantContext = Depends(get_tenant_context)):
    """Returns the members of the current workspace as owners (dynamic, not static config)."""
    owners = _get_workspace_owner_names(tenant.tenant_id)
    return {"owners": owners}


# ---------------------------------------------------------------------------
# Cards CRUD — Requirements 3.1, 3.4, 3.5, 3.6
# ---------------------------------------------------------------------------

@app.post("/cards", response_model=_CardResponse, status_code=201)
def create_card_endpoint(
    payload: _CardCreate,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Create a new card in the current workspace."""
    _require_tenant_id(tenant)

    # --- Plan limit check: cards ---
    if not _billing_service.check_limit(tenant.tenant_id, "cards"):
        limit_val = _billing_service.get_plan_limit(tenant.tenant_id, "cards")
        raise HTTPException(
            status_code=402,
            detail=f"Card limit reached ({limit_val} cards). Upgrade your plan to add more cards.",
        )

    return _create_card(tenant.tenant_id, payload)


@app.get("/cards", response_model=List[_CardResponse])
def list_cards_endpoint(tenant: TenantContext = Depends(get_tenant_context)):
    """List all cards belonging to the current workspace."""
    _require_tenant_id(tenant)
    return _list_cards(tenant.tenant_id)


@app.put("/cards/{card_id}", response_model=_CardResponse)
def update_card_endpoint(
    card_id: str,
    payload: _CardUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Update a card (only if it belongs to the current workspace)."""
    _require_tenant_id(tenant)
    return _update_card(tenant.tenant_id, card_id, payload)


@app.delete("/cards/{card_id}", status_code=204)
def delete_card_endpoint(
    card_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Remove a card (only if it belongs to the current workspace)."""
    _require_tenant_id(tenant)
    _delete_card(tenant.tenant_id, card_id)


# ---------------------------------------------------------------------------
# Category Rules CRUD — Requirement 4.5
# ---------------------------------------------------------------------------

class CategoryRuleCreate(BaseModel):
    merchant_pattern: str
    category: str


class CategoryRuleResponse(BaseModel):
    id: str
    workspace_id: str
    merchant_pattern: str
    category: str
    created_by: Optional[str] = None
    created_at: str


@app.post("/category-rules", response_model=CategoryRuleResponse, status_code=201)
def create_category_rule_endpoint(
    payload: CategoryRuleCreate,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Create a custom category rule for the current workspace."""
    tenant_id = _require_tenant_id(tenant)
    try:
        rule = _create_rule(
            workspace_id=tenant_id,
            merchant_pattern=payload.merchant_pattern,
            category=payload.category,
            created_by=tenant.user_id,
        )
        return rule
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/category-rules", response_model=List[CategoryRuleResponse])
def list_category_rules_endpoint(
    tenant: TenantContext = Depends(get_tenant_context),
):
    """List all category rules belonging to the current workspace."""
    tenant_id = _require_tenant_id(tenant)
    return _list_rules(tenant_id)


@app.put("/category-rules/{rule_id}", response_model=CategoryRuleResponse)
def update_category_rule_endpoint(
    rule_id: str,
    payload: CategoryRuleCreate,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Update a category rule (only if it belongs to the current workspace)."""
    tenant_id = _require_tenant_id(tenant)
    try:
        rule = _update_rule(
            workspace_id=tenant_id,
            rule_id=rule_id,
            merchant_pattern=payload.merchant_pattern,
            category=payload.category,
        )
        return rule
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/category-rules/{rule_id}", status_code=204)
def delete_category_rule_endpoint(
    rule_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Remove a category rule (only if it belongs to the current workspace)."""
    tenant_id = _require_tenant_id(tenant)
    try:
        _delete_rule(tenant_id, rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Billing — Mercado Pago integration (Requirements 8.1–8.8)
# ---------------------------------------------------------------------------

@app.post("/billing/create-subscription", response_model=_CreateSubscriptionResponse)
def create_subscription_endpoint(
    payload: _CreateSubscriptionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Create a Mercado Pago subscription and return the checkout URL."""
    _require_authenticated_user(tenant)
    _require_tenant_id(tenant)
    result = _billing_service.create_subscription(tenant.tenant_id, payload.plan_type)
    return _CreateSubscriptionResponse(**result)


@app.post("/billing/webhook")
def billing_webhook_endpoint(request: Request, payload: dict):
    """Receive IPN notifications from Mercado Pago (no auth required)."""
    _billing_service.process_webhook(payload)
    return {"status": "ok"}


@app.get("/billing/status", response_model=_BillingStatusResponse)
def billing_status_endpoint(
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Return the current subscription status for the workspace."""
    _require_authenticated_user(tenant)
    _require_tenant_id(tenant)
    return _billing_service.get_status(tenant.tenant_id)


@app.post("/billing/cancel")
def billing_cancel_endpoint(
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Cancel the active subscription for the workspace."""
    _require_authenticated_user(tenant)
    _require_tenant_id(tenant)
    return _billing_service.cancel_subscription(tenant.tenant_id)


@app.get("/me")
def get_me(tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    workspaces = _list_user_workspaces(user_id)
    limits = _plan_limits(profile.get("plan_type", "free"))
    billing_status = _billing_service.get_status(tenant.tenant_id)
    return {
        "user_id": user_id,
        "email": profile.get("email"),
        "plan_type": profile.get("plan_type"),
        "is_admin": bool(profile.get("is_admin", False)),
        "limits": limits,
        "active_workspace_id": profile.get("active_workspace_id"),
        "workspace_count": len(workspaces),
        "billing_plan": billing_status.plan_type,
        "display_name": profile.get("display_name"),
        "short_name": profile.get("short_name"),
        "photo_url": profile.get("photo_url"),
    }

@app.put("/me/plan")
def update_my_plan(payload: PlanUpdate, tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    profile_email = _normalize_email(profile.get("email") or tenant.user_email)
    if _is_premium_email(profile_email) and payload.plan_type != "paid":
        raise HTTPException(
            status_code=403,
            detail="This account is managed as premium and cannot downgrade from this screen.",
        )
    next_plan = _normalize_plan(payload.plan_type)
    current_plan = _normalize_plan(profile.get("plan_type", "free"))

    if current_plan == next_plan:
        return {"status": "unchanged", "plan_type": current_plan}

    workspaces = _list_user_workspaces(user_id)
    owned_workspaces = [ws for ws in workspaces if ws.get("owner_user_id") == user_id]
    next_limits = _plan_limits(next_plan)

    if len(owned_workspaces) > next_limits["max_workspaces"]:
        raise HTTPException(
            status_code=400,
            detail=f"Plan {next_plan} allows only {next_limits['max_workspaces']} workspace(s).",
        )

    for ws in owned_workspaces:
        if ws.get("member_count", 0) > next_limits["max_members_per_workspace"]:
            raise HTTPException(
                status_code=400,
                detail=f"Workspace {ws['name']} has {ws['member_count']} members, above plan limit.",
            )

    updated = _upsert_user_profile(
        user_id=user_id,
        email=profile.get("email"),
        plan_type=next_plan,
        is_admin=bool(profile.get("is_admin", False)),
        active_workspace_id=profile.get("active_workspace_id"),
    )
    return {"status": "updated", "plan_type": updated.get("plan_type")}


@app.put("/me/profile")
def update_my_profile(payload: UserProfileUpdate, tenant: TenantContext = Depends(get_tenant_context)):
    """Update the authenticated user's profile fields (display_name, short_name, etc.)."""
    user_id = _require_authenticated_user(tenant)
    profile = _upsert_user_profile(
        user_id=user_id,
        display_name=payload.display_name,
        short_name=payload.short_name,
        photo_url=payload.photo_url,
        birth_date=payload.birth_date,
        cpf=payload.cpf,
        address=payload.address,
    )
    return profile

@app.get("/workspaces")
def list_workspaces(tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    workspaces = _list_user_workspaces(user_id)
    return {
        "active_workspace_id": profile.get("active_workspace_id"),
        "workspaces": workspaces,
    }

@app.post("/workspaces")
def create_workspace(payload: WorkspaceCreate, tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    workspace_name = payload.name.strip()
    if not workspace_name:
        raise HTTPException(status_code=400, detail="Workspace name is required")

    limits = _plan_limits(profile.get("plan_type", "free"))
    owned_workspaces = [ws for ws in _list_user_workspaces(user_id) if ws.get("owner_user_id") == user_id]
    if len(owned_workspaces) >= limits["max_workspaces"]:
        raise HTTPException(
            status_code=400,
            detail=f"Plan {profile.get('plan_type')} allows up to {limits['max_workspaces']} workspace(s).",
        )

    workspace_id = f"ws-{uuid.uuid4().hex[:12]}"
    workspace = _create_workspace(
        workspace_id=workspace_id,
        name=workspace_name,
        owner_user_id=user_id,
        member_limit=limits["max_members_per_workspace"],
    )
    _add_workspace_member(workspace_id=workspace_id, user_id=user_id, role="owner")
    _upsert_user_profile(
        user_id=user_id,
        email=profile.get("email"),
        plan_type=profile.get("plan_type", "free"),
        active_workspace_id=workspace_id,
    )
    workspace["member_count"] = 1
    workspace["role"] = "owner"
    return {"status": "created", "workspace": workspace}


@app.put("/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
):
    user_id = _require_authenticated_user(tenant)
    workspace = _get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    membership = _get_workspace_member(workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=403, detail="User does not have access to this workspace")
    if membership.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only workspace owner can update workspace")

    workspace_name = payload.name.strip()
    if not workspace_name:
        raise HTTPException(status_code=400, detail="Workspace name is required")
    if len(workspace_name) > 80:
        raise HTTPException(status_code=400, detail="Workspace name is too long")

    updated = _update_workspace(workspace_id, name=workspace_name)
    if not updated:
        raise HTTPException(status_code=404, detail="Workspace not found")

    updated["member_count"] = _count_workspace_members(workspace_id)
    updated["role"] = membership.get("role")
    return {"status": "updated", "workspace": updated}


@app.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str, tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    workspace = _get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    membership = _get_workspace_member(workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=403, detail="User does not have access to this workspace")
    if membership.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only workspace owner can delete workspace")
    if workspace.get("owner_user_id") != user_id:
        raise HTTPException(status_code=403, detail="Only workspace creator can delete workspace")
    if workspace_id == DEFAULT_TENANT_ID:
        raise HTTPException(status_code=400, detail="Default workspace cannot be deleted")
    if _count_workspace_members(workspace_id) > 1:
        raise HTTPException(
            status_code=400,
            detail="Remove all other members before deleting this workspace.",
        )
    if _tenant_has_data(workspace_id):
        raise HTTPException(
            status_code=400,
            detail="Workspace has transactions and cannot be deleted.",
        )

    _delete_workspace(workspace_id)

    remaining_workspaces = _list_user_workspaces(user_id)
    if not remaining_workspaces:
        fallback_workspace_id = _personal_workspace_id_for_user(user_id)
        fallback_limits = _plan_limits(profile.get("plan_type", "free"))
        _create_workspace(
            workspace_id=fallback_workspace_id,
            name="Meu Painel",
            owner_user_id=user_id,
            member_limit=fallback_limits["max_members_per_workspace"],
        )
        _add_workspace_member(fallback_workspace_id, user_id, "owner")
        next_active = fallback_workspace_id
    else:
        next_active = remaining_workspaces[0]["id"]

    _upsert_user_profile(
        user_id=user_id,
        email=profile.get("email"),
        plan_type=profile.get("plan_type", "free"),
        is_admin=bool(profile.get("is_admin", False)),
        active_workspace_id=next_active,
    )
    return {"status": "deleted", "active_workspace_id": next_active}


@app.post("/workspaces/{workspace_id}/activate")
def activate_workspace(workspace_id: str, tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    memberships = _list_user_workspaces(user_id)
    if workspace_id not in {ws["id"] for ws in memberships}:
        raise HTTPException(status_code=403, detail="User does not have access to this workspace")

    updated = _upsert_user_profile(
        user_id=user_id,
        email=profile.get("email"),
        plan_type=profile.get("plan_type", "free"),
        active_workspace_id=workspace_id,
    )
    return {"status": "activated", "active_workspace_id": updated.get("active_workspace_id")}

@app.get("/workspaces/{workspace_id}/members")
def list_workspace_members(workspace_id: str, tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    membership = _get_workspace_member(workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=403, detail="User does not have access to this workspace")

    return {"workspace_id": workspace_id, "members": _list_workspace_members(workspace_id)}


@app.delete("/workspaces/{workspace_id}/members/{member_user_id}")
def remove_workspace_member(
    workspace_id: str,
    member_user_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Remove a member from a workspace.

    Behavior when a member is deleted:
    - Their past transactions remain intact (the ``owner`` field keeps their display name).
    - They immediately lose access to the workspace.
    - The dashboard continues to show their historical transactions under their owner name.
    This is intentional: transaction history is preserved for financial accuracy.
    """
    user_id = _require_authenticated_user(tenant)
    owner_membership = _get_workspace_member(workspace_id, user_id)
    if not owner_membership:
        raise HTTPException(status_code=403, detail="User does not have access to this workspace")
    if owner_membership.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only workspace owner can remove members")
    if member_user_id == user_id:
        raise HTTPException(status_code=400, detail="Owner cannot remove themselves from workspace")

    target_membership = _get_workspace_member(workspace_id, member_user_id)
    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found")
    if target_membership.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove workspace owner")

    _delete_workspace_member(workspace_id, member_user_id)

    target_profile = _get_user_profile(member_user_id)
    if target_profile and target_profile.get("active_workspace_id") == workspace_id:
        remaining = _list_user_workspaces(member_user_id)
        next_active = remaining[0]["id"] if remaining else None
        _upsert_user_profile(
            user_id=member_user_id,
            email=target_profile.get("email"),
            plan_type=target_profile.get("plan_type", "free"),
            is_admin=bool(target_profile.get("is_admin", False)),
            active_workspace_id=next_active,
        )

    return {"status": "removed"}

@app.post("/workspaces/{workspace_id}/invites")
def create_workspace_invite(
    workspace_id: str,
    payload: WorkspaceInviteCreate,
    tenant: TenantContext = Depends(get_tenant_context),
):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    workspace = _get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    membership = _get_workspace_member(workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=403, detail="User does not have access to this workspace")

    if membership.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only workspace owner can invite users")

    invitee_email = payload.invitee_email.strip().lower()
    if not invitee_email or "@" not in invitee_email:
        raise HTTPException(status_code=400, detail="Invalid invitee email")

    if profile.get("email") and invitee_email == profile.get("email").strip().lower():
        raise HTTPException(status_code=400, detail="Cannot invite yourself")

    invite_mode = payload.invite_mode
    if invite_mode != "shared":
        raise HTTPException(
            status_code=400,
            detail="Isolated invites are currently disabled. Use shared workspace invites.",
        )

    limits = _plan_limits(profile.get("plan_type", "free"))
    member_count = _count_workspace_members(workspace_id)

    # --- Plan limit check: members (via billing service) ---
    if not _billing_service.check_limit(workspace_id, "members"):
        billing_limit = _billing_service.get_plan_limit(workspace_id, "members")
        raise HTTPException(
            status_code=402,
            detail=f"Member limit reached ({billing_limit} members). Upgrade your plan to invite more members.",
        )

    if member_count >= limits["max_members_per_workspace"]:
        raise HTTPException(
            status_code=402,
            detail=f"Plan {profile.get('plan_type')} supports up to {limits['max_members_per_workspace']} members per workspace. Upgrade your plan.",
        )
    invite = _create_workspace_invite(
        workspace_id=workspace_id,
        inviter_user_id=user_id,
        invitee_email=invitee_email,
        invite_mode=invite_mode,
    )

    return {"status": "created", "invite": invite}

@app.get("/invites")
def list_invites(tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    my_email = (profile.get("email") or "").strip().lower()

    if not my_email:
        return {"received": [], "sent": _list_sent_invites(user_id)}

    return {
        "received": _list_pending_invites_for_email(my_email),
        "sent": _list_sent_invites(user_id),
    }

@app.post("/invites/{invite_id}/accept")
def accept_invite(invite_id: str, tenant: TenantContext = Depends(get_tenant_context)):
    user_id = _require_authenticated_user(tenant)
    profile = ensure_user_profile(user_id=user_id, email=tenant.user_email)
    invite = _get_workspace_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invite is not pending")

    invitee_email = (invite.get("invitee_email") or "").strip().lower()
    current_email = (profile.get("email") or "").strip().lower()
    if not current_email or invitee_email != current_email:
        raise HTTPException(status_code=403, detail="Invite does not belong to this user")

    invite_mode = invite.get("invite_mode")
    accepted_workspace_id = None

    if invite_mode == "shared":
        workspace_id = invite.get("workspace_id")
        if not workspace_id:
            raise HTTPException(status_code=400, detail="Invalid shared invite")

        workspace = _get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        owner_profile = ensure_user_profile(workspace.get("owner_user_id"), None)
        owner_limits = _plan_limits(owner_profile.get("plan_type", "free"))
        member_count = _count_workspace_members(workspace_id)
        existing_member = _get_workspace_member(workspace_id, user_id)

        # --- Plan limit check: members (via billing service) ---
        if not existing_member and not _billing_service.check_limit(workspace_id, "members"):
            billing_limit = _billing_service.get_plan_limit(workspace_id, "members")
            raise HTTPException(
                status_code=402,
                detail=f"Workspace member limit reached ({billing_limit} members). Upgrade the workspace plan.",
            )

        if not existing_member and member_count >= owner_limits["max_members_per_workspace"]:
            raise HTTPException(status_code=402, detail="Workspace member limit reached. Upgrade the workspace plan.")

        _add_workspace_member(workspace_id, user_id, "member")
        accepted_workspace_id = workspace_id
    else:
        my_workspaces = _list_user_workspaces(user_id)
        my_plan_limits = _plan_limits(profile.get("plan_type", "free"))
        if len(my_workspaces) >= my_plan_limits["max_workspaces"]:
            raise HTTPException(
                status_code=400,
                detail=f"Your plan allows only {my_plan_limits['max_workspaces']} workspace(s).",
            )

        workspace_name = (invite.get("target_workspace_name") or "Meu Painel").strip() or "Meu Painel"
        new_workspace_id = f"ws-{uuid.uuid4().hex[:12]}"
        _create_workspace(
            workspace_id=new_workspace_id,
            name=workspace_name,
            owner_user_id=user_id,
            member_limit=my_plan_limits["max_members_per_workspace"],
        )
        _add_workspace_member(new_workspace_id, user_id, "owner")
        accepted_workspace_id = new_workspace_id

    _update_workspace_invite(invite_id, status="accepted", accepted_at=_utc_now_iso())
    _upsert_user_profile(
        user_id=user_id,
        email=profile.get("email"),
        plan_type=profile.get("plan_type", "free"),
        active_workspace_id=accepted_workspace_id,
    )
    return {"status": "accepted", "workspace_id": accepted_workspace_id}


@app.post("/upload")
async def upload_preview(
    file: UploadFile = File(...),
    owner: Optional[str] = Form(None),
    month_ref: Optional[str] = Form(None),  # Format: YYYY-MM (optional — extracted from PDF)
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Return a preview of extracted transactions without saving to the database.

    Supports both PDF and CSV files.  For PDFs the ExtractionService is used;
    for CSVs the existing TransactionProcessor parsing flow is kept.

    The response includes suggested categories, card_type lookups and a list
    of unregistered card last4 values so the frontend can prompt onboarding.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)

    # --- Plan limit check: uploads/month ---
    if not _billing_service.check_limit(tenant.tenant_id, "uploads_month"):
        limit_val = _billing_service.get_plan_limit(tenant.tenant_id, "uploads_month")
        raise HTTPException(
            status_code=402,
            detail=f"Upload limit reached ({limit_val}/month). Upgrade your plan for unlimited uploads.",
        )

    try:
        # 1. Validate file
        contents = await _validate_and_read_upload(file, "invoice")
        file_type = _detect_file_type(file.filename or "unknown.csv")
        file_hash = hashlib.sha256(contents).hexdigest()

        # 2. Build a card lookup from registered cards
        workspace_id = tenant.tenant_id
        registered_cards = _list_cards(workspace_id)
        card_map: dict[str, str] = {}  # last4 -> card_type
        card_owner_map: dict[str, str] = {}  # last4 -> owner
        for card in registered_cards:
            card_map[card.last4] = card.card_type
            card_owner_map[card.last4] = card.owner

        # 3. Classification service
        from categories import ClassificationService as _ClassSvc
        cls_svc = _ClassSvc()

        if file_type == "pdf":
            # --- PDF path: use ExtractionService ---
            extracted = _extraction_service.extract(contents)

            preview_txns: List[PreviewTransaction] = []
            unregistered_cards_set: set[str] = set()

            for section in extracted.sections:
                for tx in section.transactions:
                    card_last4 = tx.card_last4
                    suggested_type: Optional[str] = None
                    needs_review = False

                    if card_last4 and card_last4 in card_map:
                        suggested_type = card_map[card_last4]
                    elif card_last4:
                        unregistered_cards_set.add(card_last4)
                        needs_review = True

                    # Classify using the new SaaS ClassificationService
                    from normalization import normalize_merchant as _norm_merchant
                    merchant_clean = _norm_merchant(tx.description)
                    classification = cls_svc.classify(merchant_clean, workspace_id)
                    if classification.needs_review:
                        needs_review = True

                    preview_txns.append(PreviewTransaction(
                        date=tx.date,
                        card_last4=card_last4,
                        description=tx.description,
                        amount=tx.amount,
                        is_refund=tx.is_refund,
                        suggested_category=classification.category,
                        suggested_type=suggested_type,
                        needs_review=needs_review,
                    ))

            # Extract holder_name from first section owner or statement holder
            holder_name = extracted.holder_name

            return UploadPreviewResponse(
                file_hash=file_hash,
                statement_type=extracted.statement_type,
                bank=extracted.bank,
                holder_name=holder_name,
                period_start=extracted.period_start,
                period_end=extracted.period_end,
                total_amount=extracted.total_amount,
                transactions=preview_txns,
                unregistered_cards=sorted(unregistered_cards_set),
            )

        else:
            # --- CSV path: parse with pandas, return preview ---
            import io
            import pandas as pd
            from normalization import normalize_merchant as _norm_merchant

            df = pd.read_csv(io.BytesIO(contents))

            # Detect columns
            date_col = "date" if "date" in df.columns else ("Data" if "Data" in df.columns else None)
            amt_col = "amount" if "amount" in df.columns else ("Valor" if "Valor" in df.columns else None)
            merch_col = "title" if "title" in df.columns else ("Observações" if "Observações" in df.columns else None)

            if not all([date_col, amt_col, merch_col]):
                raise HTTPException(status_code=422, detail="CSV must contain date/Data, amount/Valor, and title/Observações columns")

            # Derive month_ref from first row if not provided
            effective_month_ref = month_ref
            if not effective_month_ref and len(df) > 0:
                first_date = str(df.iloc[0][date_col])
                try:
                    if "-" in first_date:
                        parts = first_date.split("-")
                        effective_month_ref = f"{parts[0]}-{parts[1]}"
                    elif "/" in first_date:
                        parts = first_date.split("/")
                        effective_month_ref = f"{parts[2]}-{parts[1]}"
                except Exception:
                    effective_month_ref = datetime.datetime.now().strftime("%Y-%m")
            if not effective_month_ref:
                effective_month_ref = datetime.datetime.now().strftime("%Y-%m")

            preview_txns = []
            unregistered_cards_set: set[str] = set()

            for _, row in df.iterrows():
                description = str(row[merch_col]).strip()
                if description.lower() == "nan" or "Pagamento recebido" in description:
                    continue

                val_str = str(row[amt_col]).strip()
                if "," in val_str:
                    val_str = val_str.replace(".", "").replace(",", ".")
                try:
                    amount = abs(float(val_str))
                except Exception:
                    amount = 0.0

                date_str = str(row[date_col]).strip()

                merchant_clean = _norm_merchant(description)
                classification = cls_svc.classify(merchant_clean, workspace_id)

                # CSV rows don't have card_last4 by default
                card_last4 = str(row.get("card_last4", "")).strip() if "card_last4" in df.columns else None
                if card_last4 and card_last4.lower() == "nan":
                    card_last4 = None

                suggested_type: Optional[str] = None
                needs_review = classification.needs_review

                if card_last4 and card_last4 in card_map:
                    suggested_type = card_map[card_last4]
                elif card_last4:
                    unregistered_cards_set.add(card_last4)
                    needs_review = True

                preview_txns.append(PreviewTransaction(
                    date=date_str,
                    card_last4=card_last4,
                    description=description,
                    amount=amount,
                    is_refund=False,
                    suggested_category=classification.category,
                    suggested_type=suggested_type,
                    needs_review=needs_review,
                ))

            # Derive period from data
            period_start = effective_month_ref + "-01"
            try:
                import calendar
                y, m = map(int, effective_month_ref.split("-"))
                last_day = calendar.monthrange(y, m)[1]
                period_end = f"{effective_month_ref}-{last_day:02d}"
            except Exception:
                period_end = effective_month_ref + "-31"

            total_amount = sum(t.amount for t in preview_txns)

            return UploadPreviewResponse(
                file_hash=file_hash,
                statement_type="credit_card",
                bank="CSV Import",
                holder_name=owner or "Unknown",
                period_start=period_start,
                period_end=period_end,
                total_amount=round(total_amount, 2),
                transactions=preview_txns,
                unregistered_cards=sorted(unregistered_cards_set),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload preview error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/confirm")
async def upload_confirm(
    body: UploadConfirmRequest,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Save confirmed (and possibly user-edited) transactions to the database.

    Cross-references ``card_last4`` with registered cards to determine
    ``card_type``, classifies categories via ``ClassificationService``,
    and records the upload in ``upload_history``.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    try:
        workspace_id = tenant.tenant_id
        user_id = tenant.user_id or "anonymous"

        # 1. Build card lookup
        registered_cards = _list_cards(workspace_id)
        card_map: dict[str, str] = {}  # last4 -> card_type
        for card in registered_cards:
            card_map[card.last4] = card.card_type

        # 2. Classification service
        from categories import ClassificationService as _ClassSvc
        from normalization import normalize_merchant as _norm_merchant
        cls_svc = _ClassSvc()

        upload_id = f"upload-{uuid.uuid4().hex[:16]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        saved_count = 0
        warnings: List[str] = []

        if USE_SQLITE:
            conn = get_db_connection()
            c = conn.cursor()

            for tx in body.transactions:
                tx_id = f"tx-{uuid.uuid4().hex[:16]}"

                # Determine card_type from registered cards
                card_type: Optional[str] = None
                needs_review = False
                if tx.card_last4 and tx.card_last4 in card_map:
                    card_type = card_map[tx.card_last4]
                elif tx.card_last4:
                    needs_review = True
                    warnings.append(f"Card {tx.card_last4} not registered")

                # Classify category using ClassificationService
                merchant_clean = _norm_merchant(tx.description)
                classification = cls_svc.classify(merchant_clean, workspace_id)

                # Use user-provided category if available, otherwise use classification
                final_category = tx.category if tx.category else classification.category
                if classification.needs_review and not tx.category:
                    needs_review = True

                # Derive month_ref from date
                try:
                    date_parts = tx.date.split("-")
                    month_ref = f"{date_parts[0]}-{date_parts[1]}"
                except Exception:
                    month_ref = datetime.datetime.now().strftime("%Y-%m")

                try:
                    c.execute(
                        """
                        INSERT OR REPLACE INTO transactions_gold
                        (id, tenant_id, date, month_ref, amount, merchant_clean,
                         category, subcategory, owner, type, created_at,
                         card_last4, card_type, is_refund, transaction_source,
                         upload_id, needs_review)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tx_id,
                            workspace_id,
                            tx.date,
                            month_ref,
                            tx.amount,
                            merchant_clean,
                            final_category,
                            None,  # subcategory
                            tx.owner,
                            card_type,  # type = card_type
                            now,
                            tx.card_last4,
                            card_type,
                            1 if tx.is_refund else 0,
                            "pdf_extraction",
                            upload_id,
                            1 if needs_review else 0,
                        ),
                    )
                    saved_count += 1
                except Exception as e:
                    logger.error("Error inserting transaction: %s", e)
                    warnings.append(f"Failed to save transaction: {tx.description}")

            # 3. Register in upload_history
            # Derive period from transactions
            dates = [tx.date for tx in body.transactions if tx.date]
            period_start = min(dates) if dates else ""
            period_end = max(dates) if dates else ""

            upload_history_id = f"uh-{uuid.uuid4().hex[:16]}"
            c.execute(
                """
                INSERT INTO upload_history
                (id, workspace_id, user_id, filename, file_hash, file_size_bytes,
                 statement_type, bank, period_start, period_end,
                 transactions_count, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_history_id,
                    workspace_id,
                    user_id,
                    f"upload_{body.file_hash[:8]}",
                    body.file_hash,
                    None,  # file_size_bytes — not available at confirm time
                    "credit_card",  # default; could be refined
                    None,  # bank — not available at confirm time
                    period_start,
                    period_end,
                    saved_count,
                    "completed",
                    None,
                    now,
                ),
            )

            conn.commit()
            conn.close()
        else:
            # Cloud mode — Firestore + BigQuery
            if db_firestore is not None:
                batch = db_firestore.batch()
                op_count = 0

                for tx in body.transactions:
                    tx_id = f"tx-{uuid.uuid4().hex[:16]}"

                    card_type = None
                    needs_review = False
                    if tx.card_last4 and tx.card_last4 in card_map:
                        card_type = card_map[tx.card_last4]
                    elif tx.card_last4:
                        needs_review = True

                    merchant_clean = _norm_merchant(tx.description)
                    classification = cls_svc.classify(merchant_clean, workspace_id)
                    final_category = tx.category if tx.category else classification.category
                    if classification.needs_review and not tx.category:
                        needs_review = True

                    try:
                        date_parts = tx.date.split("-")
                        month_ref = f"{date_parts[0]}-{date_parts[1]}"
                    except Exception:
                        month_ref = datetime.datetime.now().strftime("%Y-%m")

                    payload = {
                        "id": tx_id,
                        "tenant_id": workspace_id,
                        "date": tx.date,
                        "month_ref": month_ref,
                        "amount": tx.amount,
                        "merchant_clean": merchant_clean,
                        "category": final_category,
                        "subcategory": None,
                        "owner": tx.owner,
                        "type": card_type,
                        "created_at": now,
                        "card_last4": tx.card_last4,
                        "card_type": card_type,
                        "is_refund": tx.is_refund,
                        "transaction_source": "pdf_extraction",
                        "upload_id": upload_id,
                        "needs_review": needs_review,
                    }

                    ref = db_firestore.collection(FIRESTORE_COLLECTION).document(tx_id)
                    batch.set(ref, payload, merge=True)
                    op_count += 1
                    saved_count += 1

                    if op_count % 400 == 0:
                        batch.commit()
                        batch = db_firestore.batch()

                if op_count % 400 != 0:
                    batch.commit()

        # Invalidate dashboard cache
        dashboard_cache.invalidate_prefix(f"dashboard:{workspace_id}:")

        return {
            "status": "success",
            "upload_id": upload_id,
            "saved_count": saved_count,
            "warnings": warnings,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload confirm error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/net-worth/upload")
async def upload_net_worth(
    file: UploadFile = File(...),
    owner: str = Form("default"),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Upload a monthly summary CSV (e.g. Controle Financeiro - Mensal.csv) and store it as
    net worth/cashflow snapshots by month.
    This is currently treated as a manual input source (one snapshot per month).
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)

    owner_name = _normalize_owner(owner)

    contents = await _validate_and_read_upload(file, "net_worth")

    try:
        import io
        import pandas as pd

        df = pd.read_csv(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read CSV file") from exc

    required_cols = {"Data", "Guardado"}
    missing = required_cols - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(sorted(missing))}",
        )

    now_iso = datetime.datetime.utcnow().isoformat()
    snapshots: list[dict] = []

    for _, row in df.iterrows():
        month_ref = _parse_month_ref(row.get("Data"))
        if not month_ref:
            continue

        net_worth_total = _parse_br_money(row.get("Guardado"))
        if net_worth_total is None:
            continue

        raw_notes = row.get("Obs")
        notes = None
        if raw_notes is not None:
            notes_str = str(raw_notes).strip()
            if notes_str and notes_str.lower() != "nan":
                notes = notes_str

        snapshots.append(
            {
                "tenant_id": tenant.tenant_id,
                "owner": owner_name,
                "month_ref": month_ref,
                "salary": _parse_br_money(row.get("Salário")),
                "other_income": _parse_br_money(row.get("Outros")),
                "income_total": _parse_br_money(row.get("Entrada")),
                "expense_fixed": _parse_br_money(row.get("CustoFixo")),
                "expense_variable": _parse_br_money(row.get("CustoMês")),
                "expense_total": _parse_br_money(row.get("Saída")),
                "cash_end_balance": _parse_br_money(row.get("Final")),
                "net_worth_total": net_worth_total,
                "debt_ratio": _parse_br_percent(row.get("Endividamento")),
                "notes": notes,
                "updated_at": now_iso,
                "source_file": file.filename,
            }
        )

    if not snapshots:
        return {"status": "success", "imported_months": 0, "message": "No valid rows found."}

    snapshots.sort(key=lambda x: x["month_ref"])

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        for s in snapshots:
            c.execute(
                """
                INSERT INTO net_worth_monthly (
                    tenant_id,
                    owner,
                    month_ref,
                    salary,
                    other_income,
                    income_total,
                    expense_fixed,
                    expense_variable,
                    expense_total,
                    cash_end_balance,
                    net_worth_total,
                    debt_ratio,
                    notes,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, owner, month_ref) DO UPDATE SET
                    salary=excluded.salary,
                    other_income=excluded.other_income,
                    income_total=excluded.income_total,
                    expense_fixed=excluded.expense_fixed,
                    expense_variable=excluded.expense_variable,
                    expense_total=excluded.expense_total,
                    cash_end_balance=excluded.cash_end_balance,
                    net_worth_total=excluded.net_worth_total,
                    debt_ratio=excluded.debt_ratio,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (
                    s["tenant_id"],
                    s["owner"],
                    s["month_ref"],
                    s.get("salary"),
                    s.get("other_income"),
                    s.get("income_total"),
                    s.get("expense_fixed"),
                    s.get("expense_variable"),
                    s.get("expense_total"),
                    s.get("cash_end_balance"),
                    s.get("net_worth_total"),
                    s.get("debt_ratio"),
                    s.get("notes"),
                    s.get("updated_at"),
                ),
            )
        conn.commit()
        conn.close()
    else:
        if USE_MOCK or db_firestore is None:
            return {"status": "success", "imported_months": 0, "message": "Firestore not available (mock mode)."}

        try:
            batch = db_firestore.batch()
            op_count = 0
            for s in snapshots:
                doc_id = f"{tenant.tenant_id}_{s['owner']}_{s['month_ref']}"
                ref = db_firestore.collection(NET_WORTH_COLLECTION).document(doc_id)
                batch.set(ref, s, merge=True)
                op_count += 1
                if op_count % 400 == 0:
                    batch.commit()
                    batch = db_firestore.batch()
            batch.commit()
        except Exception as exc:
            logger.error("Error writing net worth snapshots: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to store snapshots") from exc

    return {
        "status": "success",
        "imported_months": len(snapshots),
        "first_month": snapshots[0]["month_ref"],
        "last_month": snapshots[-1]["month_ref"],
    }

@app.get("/net-worth")
def get_net_worth(
    start: str = None,
    end: str = None,
    owner: str = None,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Returns monthly net worth snapshots for the active tenant/workspace.
    Params start/end are optional (YYYY-MM).
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    start_month = start
    end_month = end
    owner_name = _normalize_owner(owner) if owner else None

    if USE_SQLITE:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = "SELECT * FROM net_worth_monthly WHERE tenant_id = ?"
        params: list[object] = [tenant.tenant_id]
        if owner_name:
            query += " AND owner = ?"
            params.append(owner_name)
        if start_month:
            query += " AND month_ref >= ?"
            params.append(start_month)
        if end_month:
            query += " AND month_ref <= ?"
            params.append(end_month)
        query += " ORDER BY month_ref ASC"
        c.execute(query, params)
        results = [dict(row) for row in c.fetchall()]
        conn.close()
        return {"data": results}

    if USE_MOCK or db_firestore is None:
        return {"data": []}

    try:
        docs = (
            db_firestore.collection(NET_WORTH_COLLECTION)
            .where("tenant_id", "==", tenant.tenant_id)
            .stream()
        )
        results: list[dict] = []
        for doc in docs:
            data = doc.to_dict() or {}
            month_ref = (data.get("month_ref") or "").strip()
            if not month_ref:
                continue
            row_owner = data.get("owner")
            default_owner = _get_workspace_owner_names(tenant.tenant_id)[0]
            if owner_name:
                if not row_owner:
                    # Legacy rows (before owner field) default to first configured owner.
                    if owner_name != default_owner:
                        continue
                    data["owner"] = default_owner
                elif row_owner != owner_name:
                    continue
            elif not row_owner:
                data["owner"] = default_owner
            if start_month and month_ref < start_month:
                continue
            if end_month and month_ref > end_month:
                continue
            results.append(data)

        results.sort(key=lambda x: x.get("month_ref") or "")
        return {"data": results}
    except Exception as exc:
        logger.error("Error fetching net worth snapshots: %s", exc)
        return {"data": []}

@app.put("/net-worth/{month_ref}")
def update_net_worth_row(
    month_ref: str,
    payload: NetWorthRowUpdate,
    owner: str = "default",
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Manual editor for one month row in patrimônio.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    if not re.fullmatch(r"\d{4}-\d{2}", month_ref):
        raise HTTPException(status_code=400, detail="month_ref must be in YYYY-MM format")

    owner_name = _normalize_owner(owner)
    now_iso = datetime.datetime.utcnow().isoformat()
    fields = {
        "salary": payload.salary,
        "other_income": payload.other_income,
        "income_total": payload.income_total,
        "expense_fixed": payload.expense_fixed,
        "expense_variable": payload.expense_variable,
        "expense_total": payload.expense_total,
        "cash_end_balance": payload.cash_end_balance,
        "net_worth_total": payload.net_worth_total,
        "debt_ratio": payload.debt_ratio,
        "notes": payload.notes,
    }
    changed_fields = {k: v for k, v in fields.items() if v is not None}
    if not changed_fields:
        return {"status": "no_changes"}

    if USE_SQLITE:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM net_worth_monthly
            WHERE tenant_id = ? AND owner = ? AND month_ref = ?
            """,
            (tenant.tenant_id, owner_name, month_ref),
        )
        existing = c.fetchone()
        merged = dict(existing) if existing else {
            "tenant_id": tenant.tenant_id,
            "owner": owner_name,
            "month_ref": month_ref,
        }
        merged.update(changed_fields)
        merged["updated_at"] = now_iso

        c.execute(
            """
            INSERT INTO net_worth_monthly (
                tenant_id,
                owner,
                month_ref,
                salary,
                other_income,
                income_total,
                expense_fixed,
                expense_variable,
                expense_total,
                cash_end_balance,
                net_worth_total,
                debt_ratio,
                notes,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, owner, month_ref) DO UPDATE SET
                salary=excluded.salary,
                other_income=excluded.other_income,
                income_total=excluded.income_total,
                expense_fixed=excluded.expense_fixed,
                expense_variable=excluded.expense_variable,
                expense_total=excluded.expense_total,
                cash_end_balance=excluded.cash_end_balance,
                net_worth_total=excluded.net_worth_total,
                debt_ratio=excluded.debt_ratio,
                notes=excluded.notes,
                updated_at=excluded.updated_at
            """,
            (
                tenant.tenant_id,
                owner_name,
                month_ref,
                merged.get("salary"),
                merged.get("other_income"),
                merged.get("income_total"),
                merged.get("expense_fixed"),
                merged.get("expense_variable"),
                merged.get("expense_total"),
                merged.get("cash_end_balance"),
                merged.get("net_worth_total"),
                merged.get("debt_ratio"),
                merged.get("notes"),
                now_iso,
            ),
        )
        conn.commit()
        conn.close()
        return {"status": "updated", "month_ref": month_ref, "owner": owner_name}

    if USE_MOCK or db_firestore is None:
        return {"status": "updated (mock)", "month_ref": month_ref, "owner": owner_name}

    doc_id = f"{tenant.tenant_id}_{owner_name}_{month_ref}"
    document = {
        "tenant_id": tenant.tenant_id,
        "owner": owner_name,
        "month_ref": month_ref,
        "updated_at": now_iso,
    }
    document.update(changed_fields)
    db_firestore.collection(NET_WORTH_COLLECTION).document(doc_id).set(document, merge=True)
    return {"status": "updated", "month_ref": month_ref, "owner": owner_name}

@app.get("/net-worth/validation")
def get_net_worth_validation(
    start: str = None,
    end: str = None,
    owner: str = "default",
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Returns monthly validation data:
    - income from current-account credits
    - expenses from card transactions + current-account debits (excluding card bill payment)
    - manual patrimônio row values (when available)
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    owner_name = _normalize_owner(owner)

    def month_allowed(month_ref: str) -> bool:
        if not month_ref:
            return False
        if start and month_ref < start:
            return False
        if end and month_ref > end:
            return False
        return True

    aggregates: dict[str, dict] = {}

    def ensure_row(month_ref: str) -> dict:
        if month_ref not in aggregates:
            aggregates[month_ref] = {
                "month_ref": month_ref,
                "owner": owner_name,
                "income_bank": 0.0,
                "expense_bank": 0.0,
                "expense_card": 0.0,
                "manual_income_total": None,
                "manual_expense_total": None,
                "manual_net_worth_total": None,
            }
        return aggregates[month_ref]

    if USE_SQLITE:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """
            SELECT month_ref,
                   SUM(CASE WHEN amount_signed > 0 THEN amount_signed ELSE 0 END) AS income_bank,
                   SUM(CASE WHEN amount_signed < 0 AND is_card_invoice_payment = 0 THEN -amount_signed ELSE 0 END) AS expense_bank
            FROM current_account_movements
            WHERE tenant_id = ? AND owner = ?
            GROUP BY month_ref
            """,
            (tenant.tenant_id, owner_name),
        )
        for row in c.fetchall():
            month_ref = row["month_ref"]
            if not month_allowed(month_ref):
                continue
            target = ensure_row(month_ref)
            target["income_bank"] = float(row["income_bank"] or 0)
            target["expense_bank"] = float(row["expense_bank"] or 0)

        c.execute(
            """
            SELECT month_ref, SUM(amount) AS expense_card
            FROM transactions_gold
            WHERE tenant_id = ? AND owner = ? AND id NOT LIKE 'cc-%'
            GROUP BY month_ref
            """,
            (tenant.tenant_id, owner_name),
        )
        for row in c.fetchall():
            month_ref = row["month_ref"]
            if not month_allowed(month_ref):
                continue
            target = ensure_row(month_ref)
            target["expense_card"] = float(row["expense_card"] or 0)

        c.execute(
            """
            SELECT month_ref, income_total, expense_total, net_worth_total
            FROM net_worth_monthly
            WHERE tenant_id = ? AND owner = ?
            """,
            (tenant.tenant_id, owner_name),
        )
        for row in c.fetchall():
            month_ref = row["month_ref"]
            if not month_allowed(month_ref):
                continue
            target = ensure_row(month_ref)
            target["manual_income_total"] = row["income_total"]
            target["manual_expense_total"] = row["expense_total"]
            target["manual_net_worth_total"] = row["net_worth_total"]

        conn.close()
    elif not USE_MOCK and db_firestore is not None:
        movement_docs = (
            db_firestore.collection(CURRENT_ACCOUNT_COLLECTION)
            .where("tenant_id", "==", tenant.tenant_id)
            .where("owner", "==", owner_name)
            .stream()
        )
        for doc in movement_docs:
            data = doc.to_dict() or {}
            month_ref = data.get("month_ref")
            if not month_allowed(month_ref):
                continue
            amount_signed = float(data.get("amount_signed") or 0)
            target = ensure_row(month_ref)
            if amount_signed > 0:
                target["income_bank"] += amount_signed
            elif amount_signed < 0 and not bool(data.get("is_card_invoice_payment", False)):
                target["expense_bank"] += abs(amount_signed)

        tx_docs = (
            db_firestore.collection(FIRESTORE_COLLECTION)
            .where("tenant_id", "==", tenant.tenant_id)
            .where("owner", "==", owner_name)
            .stream()
        )
        for doc in tx_docs:
            tx = doc.to_dict() or {}
            month_ref = tx.get("month_ref")
            if not month_allowed(month_ref):
                continue
            if doc.id.startswith("cc-"):
                continue
            target = ensure_row(month_ref)
            target["expense_card"] += float(tx.get("amount") or 0)

        manual_docs = (
            db_firestore.collection(NET_WORTH_COLLECTION)
            .where("tenant_id", "==", tenant.tenant_id)
            .where("owner", "==", owner_name)
            .stream()
        )
        for doc in manual_docs:
            row = doc.to_dict() or {}
            month_ref = row.get("month_ref")
            if not month_allowed(month_ref):
                continue
            target = ensure_row(month_ref)
            target["manual_income_total"] = row.get("income_total")
            target["manual_expense_total"] = row.get("expense_total")
            target["manual_net_worth_total"] = row.get("net_worth_total")

    rows = []
    for month_ref in sorted(aggregates.keys()):
        row = aggregates[month_ref]
        suggested_income = round(float(row["income_bank"] or 0), 2)
        suggested_expense = round(float(row["expense_bank"] or 0) + float(row["expense_card"] or 0), 2)
        row["suggested_income_total"] = suggested_income
        row["suggested_expense_total"] = suggested_expense
        row["suggested_saved"] = round(suggested_income - suggested_expense, 2)
        row["is_partial"] = row["manual_income_total"] is None or row["manual_expense_total"] is None
        rows.append(row)

    return {"owner": owner_name, "data": rows}

@app.post("/current-account/upload")
async def upload_current_account(
    file: UploadFile = File(...),
    owner: str = Form(...),
    month_ref: str = Form(...),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Upload current-account CSV and:
    1) store signed movements
    2) generate spending transactions from outgoing movements (excluding card bill payment)
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    owner_name = _normalize_owner(owner)
    if not re.fullmatch(r"\d{4}-\d{2}", month_ref):
        raise HTTPException(status_code=400, detail="month_ref must be in YYYY-MM format")

    contents = await _validate_and_read_upload(file, "current_account")

    try:
        import io
        import pandas as pd

        df = pd.read_csv(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read CSV file") from exc

    required = {"Data", "Valor", "Descrição"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(sorted(missing))}")

    source_file = file.filename
    now_iso = datetime.datetime.utcnow().isoformat()
    movement_rows: list[dict] = []
    transaction_rows: list[dict] = []
    skipped_other_month = 0

    for _, row in df.iterrows():
        date_iso = _parse_ddmmyyyy_to_iso(row.get("Data"))
        if not date_iso:
            continue
        parsed_month = date_iso[:7]
        if parsed_month != month_ref:
            skipped_other_month += 1
            continue

        amount_signed = _parse_signed_amount(row.get("Valor"))
        if amount_signed is None or amount_signed == 0:
            continue

        description = str(row.get("Descrição") or "").strip()
        if not description:
            continue

        identifier_raw = str(row.get("Identificador") or "").strip()
        if not identifier_raw:
            digest = hashlib.md5(f"{tenant.tenant_id}|{owner_name}|{date_iso}|{amount_signed}|{description}".encode("utf-8")).hexdigest()[:20]
            identifier_raw = f"auto-{digest}"
        movement_id = re.sub(r"[^A-Za-z0-9_.-]", "-", identifier_raw)[:120]

        is_card_invoice_payment = "pagamento de fatura" in description.lower()
        movement = {
            "tenant_id": tenant.tenant_id,
            "owner": owner_name,
            "movement_id": movement_id,
            "date": date_iso,
            "month_ref": parsed_month,
            "amount_signed": float(amount_signed),
            "description": description,
            "source_file": source_file,
            "is_card_invoice_payment": bool(is_card_invoice_payment),
            "created_at": now_iso,
        }
        movement_rows.append(movement)

        if amount_signed < 0 and not is_card_invoice_payment:
            tx_id = f"cc-{tenant.tenant_id}-{owner_name.lower()}-{movement_id}"
            transaction_rows.append(
                {
                    "id": tx_id,
                    "tenant_id": tenant.tenant_id,
                    "date": date_iso,
                    "month_ref": parsed_month,
                    "amount": round(abs(float(amount_signed)), 2),
                    "merchant_clean": description[:255],
                    "category": _category_for_current_account(description, is_card_invoice_payment=False),
                    "subcategory": "Conta Corrente",
                    "owner": owner_name,
                    "type": "Individual",
                    "created_at": now_iso,
                }
            )

    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        for movement in movement_rows:
            c.execute(
                """
                INSERT OR REPLACE INTO current_account_movements (
                    tenant_id,
                    owner,
                    movement_id,
                    date,
                    month_ref,
                    amount_signed,
                    description,
                    source_file,
                    is_card_invoice_payment,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    movement["tenant_id"],
                    movement["owner"],
                    movement["movement_id"],
                    movement["date"],
                    movement["month_ref"],
                    movement["amount_signed"],
                    movement["description"],
                    movement["source_file"],
                    1 if movement["is_card_invoice_payment"] else 0,
                    movement["created_at"],
                ),
            )

        for tx in transaction_rows:
            c.execute(
                """
                INSERT OR REPLACE INTO transactions_gold
                (id, tenant_id, date, month_ref, amount, merchant_clean, category, subcategory, owner, type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx["id"],
                    tx["tenant_id"],
                    tx["date"],
                    tx["month_ref"],
                    tx["amount"],
                    tx["merchant_clean"],
                    tx["category"],
                    tx["subcategory"],
                    tx["owner"],
                    tx["type"],
                    tx["created_at"],
                ),
            )
        conn.commit()
        conn.close()
    elif not USE_MOCK and db_firestore is not None:
        batch = db_firestore.batch()
        op_count = 0
        for movement in movement_rows:
            doc_id = f"{tenant.tenant_id}_{owner_name}_{movement['movement_id']}"
            ref = db_firestore.collection(CURRENT_ACCOUNT_COLLECTION).document(doc_id)
            batch.set(ref, movement, merge=True)
            op_count += 1
            if op_count % 400 == 0:
                batch.commit()
                batch = db_firestore.batch()
        for tx in transaction_rows:
            tx_ref = db_firestore.collection(FIRESTORE_COLLECTION).document(tx["id"])
            batch.set(tx_ref, tx, merge=True)
            op_count += 1
            if op_count % 400 == 0:
                batch.commit()
                batch = db_firestore.batch()
        batch.commit()

    return {
        "status": "success",
        "owner": owner_name,
        "month_ref": month_ref,
        "processed_movements": len(movement_rows),
        "generated_transactions": len(transaction_rows),
        "skipped_other_month": skipped_other_month,
    }

@app.get("/transactions")
def get_transactions(
    start: str,
    end: str = None,
    owner: str = None,
    tx_type: str = None,
    limit: int = 200,
    offset: int = 0,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Get transactions for a date range (YYYY-MM to YYYY-MM).
    Optional filters: owner, tx_type.
    Supports pagination via limit/offset (default: 200 per page).
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    end_month = end or start
    limit = max(1, min(limit, 1000))  # clamp between 1 and 1000
    offset = max(0, offset)
    
    # SQLITE MODE
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Count query
        count_query = "SELECT COUNT(*) FROM transactions_gold WHERE tenant_id = ? AND month_ref >= ? AND month_ref <= ?"
        params = [tenant.tenant_id, start, end_month]
        
        if owner:
            count_query += " AND owner = ?"
            params.append(owner)
        if tx_type:
            count_query += " AND type = ?"
            params.append(tx_type)
        
        c.execute(count_query, params)
        total = c.fetchone()[0]
        
        # Data query with pagination
        data_query = count_query.replace("SELECT COUNT(*)", "SELECT *") + " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        c.execute(data_query, params)
        results = [dict(row) for row in c.fetchall()]
        conn.close()
        return {"data": results, "total": total, "limit": limit, "offset": offset}

    # MOCK MODE
    if USE_MOCK or db_firestore is None:
        logger.debug("Using mock data")
        data = load_mock_data()
        filtered = [
            tx for tx in data
            if tx.get("tenant_id") == tenant.tenant_id and start <= tx.get('month_ref', '') <= end_month
        ]
        
        if owner:
            filtered = [tx for tx in filtered if tx.get('owner') == owner]
        if tx_type:
            filtered = [tx for tx in filtered if tx.get('type') == tx_type]
        
        filtered.sort(key=lambda x: x.get('date', ''), reverse=True)
        total = len(filtered)
        page = filtered[offset:offset + limit]
        return {"data": page, "total": total, "limit": limit, "offset": offset}
    
    def _query_transactions_bigquery(fetch_all: bool = False):
        if bq_client is None:
            return {"data": [], "total": 0, "limit": limit, "offset": offset}

        where = "tenant_id = @tenant_id AND month_ref >= @start AND month_ref <= @end"
        params = [
            bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant.tenant_id),
            bigquery.ScalarQueryParameter("start", "STRING", start),
            bigquery.ScalarQueryParameter("end", "STRING", end_month),
        ]
        if owner:
            where += " AND owner = @owner"
            params.append(bigquery.ScalarQueryParameter("owner", "STRING", owner))
        if tx_type:
            where += " AND type = @tx_type"
            params.append(bigquery.ScalarQueryParameter("tx_type", "STRING", tx_type))

        count_query = f"SELECT COUNT(*) AS total FROM `{TABLE_GOLD}` WHERE {where}"
        count_config = bigquery.QueryJobConfig(query_parameters=params)
        count_rows = list(bq_client.query(count_query, job_config=count_config))
        total = int(count_rows[0]["total"]) if count_rows else 0

        data_query = f"""
            SELECT id, date, month_ref, amount, merchant_clean, category, subcategory, owner, type, tenant_id, created_at
            FROM `{TABLE_GOLD}`
            WHERE {where}
            ORDER BY date DESC
        """
        data_params = list(params)
        if not fetch_all:
            data_query += "\nLIMIT @limit OFFSET @offset"
            data_params.extend(
                [
                    bigquery.ScalarQueryParameter("limit", "INT64", limit),
                    bigquery.ScalarQueryParameter("offset", "INT64", offset),
                ]
            )
        data_config = bigquery.QueryJobConfig(query_parameters=data_params)
        rows = [dict(row) for row in bq_client.query(data_query, job_config=data_config)]
        return {"data": rows, "total": total, "limit": limit, "offset": offset}

    # FIRESTORE MODE (Cloud)
    try:
        query = db_firestore.collection(FIRESTORE_COLLECTION)
        query = query.where("tenant_id", "==", tenant.tenant_id)
        query = query.where("month_ref", ">=", start).where("month_ref", "<=", end_month)

        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            data["tenant_id"] = tenant.tenant_id

            if owner and data.get("owner") != owner:
                continue
            if tx_type and data.get("type") != tx_type:
                continue

            results.append(data)

        if not results:
            logger.info("No Firestore transactions found for tenant %s; falling back to BigQuery.", tenant.tenant_id)
            return _query_transactions_bigquery()

        bq_result = _query_transactions_bigquery(fetch_all=True)
        bq_rows = bq_result.get("data", [])
        if not bq_rows:
            results.sort(key=lambda x: x.get("date", ""), reverse=True)
            total = len(results)
            page = results[offset:offset + limit]
            return {"data": page, "total": total, "limit": limit, "offset": offset}

        merged_by_id = {row.get("id"): row for row in bq_rows if row.get("id")}
        for row in results:
            row_id = row.get("id")
            if not row_id:
                continue
            merged_by_id[row_id] = {**merged_by_id.get(row_id, {}), **row}

        merged_rows = list(merged_by_id.values())
        merged_rows.sort(key=lambda x: x.get("date", ""), reverse=True)
        total = len(merged_rows)
        page = merged_rows[offset:offset + limit]
        return {"data": page, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.warning("Firestore transaction query failed; falling back to BigQuery: %s", e)
        return _query_transactions_bigquery()

@app.put("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: str,
    update_data: TransactionUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Update any field of a transaction.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    # SQLITE MODE
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        
        set_clauses = []
        params = []
        
        if update_data.date is not None:
            set_clauses.append("date = ?")
            params.append(update_data.date)
            # Also update month_ref
            set_clauses.append("month_ref = ?")
            params.append(update_data.date[:7] if update_data.date else None)
        if update_data.amount is not None:
            set_clauses.append("amount = ?")
            params.append(update_data.amount)
        if update_data.merchant_clean is not None:
            set_clauses.append("merchant_clean = ?")
            params.append(update_data.merchant_clean)
        if update_data.category is not None:
            set_clauses.append("category = ?")
            params.append(update_data.category)
        if update_data.subcategory is not None:
            set_clauses.append("subcategory = ?")
            params.append(update_data.subcategory)
        if update_data.owner is not None:
            set_clauses.append("owner = ?")
            params.append(update_data.owner)
        if update_data.type is not None:
            set_clauses.append("type = ?")
            params.append(update_data.type)
            
        if not set_clauses:
            return {"status": "no changes"}
            
        params.extend([transaction_id, tenant.tenant_id])
        c.execute(
            f"UPDATE transactions_gold SET {', '.join(set_clauses)} WHERE id = ? AND tenant_id = ?",
            params,
        )
        affected = c.rowcount
        conn.commit()
        conn.close()
        if affected == 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
        dashboard_cache.invalidate_prefix(f"dashboard:{tenant.tenant_id}:")
        return {"status": "updated", "id": transaction_id}

    # MOCK MODE - just return success (no persistence)
    if USE_MOCK or db_firestore is None:
        return {"status": "updated (mock)", "id": transaction_id}
    
    # FIRESTORE MODE
    try:
        update_dict = {}
        if update_data.date is not None:
            update_dict['date'] = update_data.date
            update_dict['month_ref'] = update_data.date[:7]
        if update_data.amount is not None:
            update_dict['amount'] = update_data.amount
        if update_data.merchant_clean is not None:
            update_dict['merchant_clean'] = update_data.merchant_clean
        if update_data.category is not None:
            update_dict['category'] = update_data.category
        if update_data.subcategory is not None:
            update_dict['subcategory'] = update_data.subcategory
        if update_data.owner is not None:
            update_dict['owner'] = update_data.owner
        if update_data.type is not None:
            update_dict['type'] = update_data.type
        
        if not update_dict:
            return {"status": "no changes"}

        # Firestore-only update — BigQuery is synced separately via the sync button.
        doc_ref = db_firestore.collection(FIRESTORE_COLLECTION).document(transaction_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Transaction not found")

        current_data = doc.to_dict() or {}
        if (current_data.get("tenant_id") or DEFAULT_TENANT_ID) != tenant.tenant_id:
            raise HTTPException(status_code=404, detail="Transaction not found")

        doc_ref.update({**update_dict, "updated_at": datetime.datetime.now().isoformat()})

        dashboard_cache.invalidate_prefix(f"dashboard:{tenant.tenant_id}:")
        return {"status": "updated", "id": transaction_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transactions")
def create_transaction(tx: TransactionCreate, tenant: TenantContext = Depends(get_tenant_context)):
    """
    Create a new transaction.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    import uuid
    import datetime as dt
    
    tx_id = f"{tenant.tenant_id}-{str(uuid.uuid4())[:8]}-{tx.date.replace('-', '')}"
    month_ref = tx.date[:7] if tx.date else None
    
    # SQLITE MODE
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO transactions_gold 
            (id, tenant_id, date, month_ref, amount, merchant_clean, category, subcategory, owner, type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tx_id,
            tenant.tenant_id,
            tx.date,
            month_ref,
            tx.amount,
            tx.merchant_clean,
            tx.category,
            tx.subcategory,
            tx.owner,
            tx.type,
            dt.datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        dashboard_cache.invalidate_prefix(f"dashboard:{tenant.tenant_id}:")
        return {"status": "created", "id": tx_id}

    # MOCK MODE
    if USE_MOCK or db_firestore is None:
        return {"status": "created (mock)", "id": tx_id}
    
    # FIRESTORE MODE
    try:
        doc_data = {
            "date": tx.date,
            "month_ref": month_ref,
            "amount": tx.amount,
            "merchant_clean": tx.merchant_clean,
            "category": tx.category,
            "subcategory": tx.subcategory,
            "owner": tx.owner,
            "type": tx.type,
            "tenant_id": tenant.tenant_id,
            "created_at": dt.datetime.now().isoformat()
        }
        db_firestore.collection(FIRESTORE_COLLECTION).document(tx_id).set(doc_data)
        dashboard_cache.invalidate_prefix(f"dashboard:{tenant.tenant_id}:")
        _sync_to_bq_if_cloud(tenant.tenant_id)
        return {"status": "created", "id": tx_id}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str, tenant: TenantContext = Depends(get_tenant_context)):
    """
    Delete a transaction by ID.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    # SQLITE MODE
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "DELETE FROM transactions_gold WHERE id = ? AND tenant_id = ?",
            (transaction_id, tenant.tenant_id),
        )
        affected = c.rowcount
        conn.commit()
        conn.close()
        
        if affected == 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
        dashboard_cache.invalidate_prefix(f"dashboard:{tenant.tenant_id}:")
        return {"status": "deleted", "id": transaction_id}

    # MOCK MODE
    if USE_MOCK or db_firestore is None:
        return {"status": "deleted (mock)", "id": transaction_id}
    
    # FIRESTORE MODE
    try:
        doc_ref = db_firestore.collection(FIRESTORE_COLLECTION).document(transaction_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Transaction not found")
        doc_data = doc.to_dict() or {}
        if (doc_data.get("tenant_id") or DEFAULT_TENANT_ID) != tenant.tenant_id:
            raise HTTPException(status_code=404, detail="Transaction not found")
        doc_ref.delete()
        dashboard_cache.invalidate_prefix(f"dashboard:{tenant.tenant_id}:")
        _sync_to_bq_if_cloud(tenant.tenant_id)
        return {"status": "deleted", "id": transaction_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

from cache import dashboard_cache

def _serialize_firestore_value(value):
    """Convert Firestore-specific types (e.g. DatetimeWithNanoseconds) to JSON-serializable types."""
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value

def _sync_to_bq_if_cloud(tenant_id: str):
    """Trigger a lightweight BigQuery sync after Firestore writes.
    
    In cloud mode (Firestore + BigQuery), this ensures BQ stays in sync
    with Firestore after create/update/delete operations.
    Only syncs the affected tenant's data.
    """
    if USE_SQLITE or USE_MOCK or not db_firestore or not bq_client:
        return
    try:
        from google.cloud.bigquery import LoadJobConfig, SourceFormat
        
        docs = db_firestore.collection(FIRESTORE_COLLECTION).where(
            "tenant_id", "==", tenant_id
        ).stream()
        
        gold_rows = []
        for doc in docs:
            data = doc.to_dict() or {}
            gold_rows.append({
                "id": doc.id,
                "date": _serialize_firestore_value(data.get("date")),
                "month_ref": _serialize_firestore_value(data.get("month_ref")),
                "amount": float(data.get("amount") or 0),
                "merchant_clean": data.get("merchant_clean"),
                "category": data.get("category"),
                "subcategory": data.get("subcategory"),
                "type": data.get("type"),
                "owner": data.get("owner"),
                "tenant_id": tenant_id,
                "created_at": _serialize_firestore_value(data.get("created_at")) or datetime.datetime.now().isoformat(),
            })
        
        # Delete tenant data from BQ and reload
        delete_query = f"DELETE FROM `{TABLE_GOLD}` WHERE tenant_id = @tenant_id"
        delete_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id)]
        )
        bq_client.query(delete_query, job_config=delete_config).result()
        
        if gold_rows:
            job_config = LoadJobConfig(
                source_format=SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition="WRITE_APPEND",
            )
            load_job = bq_client.load_table_from_json(gold_rows, TABLE_GOLD, job_config=job_config)
            load_job.result()
        
        logger.info("Auto-synced %d rows to BQ for tenant %s", len(gold_rows), tenant_id)
    except Exception as e:
        logger.warning("Auto-sync to BQ failed for tenant %s: %s", tenant_id, e)

@app.get("/dashboard-summary")
def get_dashboard_summary(
    start: str,
    end: str = None,
    owner: str = None,
    tx_type: str = None,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Returns aggregated stats for the dashboard over a date range.
    Optional filters: owner, tx_type.
    Results are cached for 5 minutes per tenant+params combination.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    end_month = end or start
    if end_month < start:
        start, end_month = end_month, start

    cache_key = f"dashboard:{tenant.tenant_id}:{start}:{end_month}:{owner}:{tx_type}"
    cached = dashboard_cache.get(cache_key)
    if cached is not None:
        return cached
    
    # SQLITE MODE
    if USE_SQLITE:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        workspace_owners = _get_workspace_owner_names(tenant.tenant_id)
        
        # Helper to query totals
        def get_total_spend_sqlite(s_date, e_date):
            w = "tenant_id = ? AND month_ref >= ? AND month_ref <= ?"
            p = [tenant.tenant_id, s_date, e_date]
            if owner:
                w += " AND owner = ?"
                p.append(owner)
            if tx_type:
                w += " AND type = ?"
                p.append(tx_type)
            
            c.execute(f"""
                SELECT 
                    SUM(amount) as total_spend,
                    owner,
                    SUM(amount) as owner_spend
                FROM transactions_gold
                WHERE {w}
                GROUP BY owner
            """, p)
            rows = c.fetchall()
            result = {'total_spend': 0}
            for r in rows:
                o_name = r['owner']
                o_spend = r['owner_spend'] or 0
                result['total_spend'] += o_spend
                result[f'{o_name}_spend'] = o_spend
            return result

        # 1. Current Period
        current_totals = get_total_spend_sqlite(start, end_month)
        
        # 2. Last Year Period
        def get_past_date_str(date_str):
            y, m = map(int, date_str.split('-'))
            return f"{y-1}-{m:02d}"
            
        start_ly = get_past_date_str(start)
        end_ly = get_past_date_str(end_month)
        last_year_totals = get_total_spend_sqlite(start_ly, end_ly)

        # 3. Category Spend (Current Only)
        base_where = "tenant_id = ? AND month_ref >= ? AND month_ref <= ?"
        params = [tenant.tenant_id, start, end_month]
        if owner:
            base_where += " AND owner = ?"
            params.append(owner)
        if tx_type:
            base_where += " AND type = ?"
            params.append(tx_type)

        c.execute(f"""
            SELECT category, SUM(amount) as value
            FROM transactions_gold
            WHERE {base_where}
            GROUP BY category
            ORDER BY value DESC
        """, params)
        result_cat = [dict(r) for r in c.fetchall()]
        
        # 4. Settlement Logic (only for Shared transactions, Current Period)
        # When tx_type is set and is not "Shared", settlement is not applicable —
        # skip the query entirely and return zeroed settlement data.
        if tx_type and tx_type != "Shared":
            conn.close()
            direction = "Sem pendências"
            amount = 0
        else:
            settlement_where = "tenant_id = ? AND month_ref >= ? AND month_ref <= ?"
            settlement_params = [tenant.tenant_id, start, end_month]
            if owner:
                settlement_where += " AND owner = ?"
                settlement_params.append(owner)
            
            c.execute(f"""
                SELECT 
                    owner,
                    SUM(amount) as shared_paid
                FROM transactions_gold
                WHERE {settlement_where} AND type = 'Shared'
                GROUP BY owner
            """, settlement_params)
            settlement_rows = [dict(r) for r in c.fetchall()]
            conn.close()
            
            # Calculate settlement (split shared expenses evenly among all owners)
            paid_by_owner = {}
            for row in settlement_rows:
                paid_by_owner[row['owner']] = row['shared_paid'] or 0
                
            total_shared = sum(paid_by_owner.values())
            num_owners = len(workspace_owners) if workspace_owners else 2
            fair_share = total_shared / num_owners if total_shared > 0 else 0
            
            # Find who owes whom (simplified: largest overpayer vs largest underpayer)
            balances = {o: paid_by_owner.get(o, 0) - fair_share for o in workspace_owners}
            overpayers = {o: b for o, b in balances.items() if b > 0}
            underpayers = {o: b for o, b in balances.items() if b < 0}
            
            if overpayers and underpayers:
                top_overpayer = max(overpayers, key=overpayers.get)
                top_underpayer = min(underpayers, key=underpayers.get)
                direction = f"{top_underpayer} deve a {top_overpayer}"
                amount = abs(underpayers[top_underpayer])
            else:
                direction = "Sem pendências"
                amount = 0

        _sqlite_result = {
            "total_spend": current_totals['total_spend'] or 0,
            "total_spend_last_year": last_year_totals['total_spend'] or 0,
            "spend_by_person": [
                {
                    "name": o,
                    "value": current_totals.get(f'{o}_spend', 0),
                    "value_last_year": last_year_totals.get(f'{o}_spend', 0),
                }
                for o in workspace_owners
            ],
            "spend_by_category": [{"name": r['category'] or "Outros", "value": r['value']} for r in result_cat],
            "settlement": {
                "direction": direction,
                "amount": round(amount, 2)
            }
        }
        dashboard_cache.set(cache_key, _sqlite_result)
        return _sqlite_result

    # MOCK MODE
    if USE_MOCK or bq_client is None:
        logger.debug("Using mock data")
        data = load_mock_data()
        filtered = [
            tx for tx in data
            if tx.get("tenant_id") == tenant.tenant_id and start <= tx.get('month_ref', '') <= end_month
        ]
        if owner:
            filtered = [tx for tx in filtered if tx.get('owner') == owner]
        if tx_type:
            filtered = [tx for tx in filtered if tx.get('type') == tx_type]

        mock_owners = _get_workspace_owner_names(tenant.tenant_id)
        
        if not filtered:
            return {
                "total_spend": 0,
                "spend_by_person": [{"name": o, "value": 0} for o in mock_owners],
                "spend_by_category": [],
                "settlement": {
                    "direction": "Sem pendências",
                    "amount": 0
                }
            }
        
        # Calculate totals per owner
        total_spend = sum(tx.get('amount', 0) for tx in filtered)
        spend_per_owner = {}
        for o in mock_owners:
            spend_per_owner[o] = sum(tx.get('amount', 0) for tx in filtered if tx.get('owner') == o)
        
        # Calculate by category
        category_totals = {}
        for tx in filtered:
            cat = tx.get('category', 'Outros') or 'Outros'
            category_totals[cat] = category_totals.get(cat, 0) + tx.get('amount', 0)
        
        spend_by_category = [{"name": k, "value": v} for k, v in sorted(category_totals.items(), key=lambda x: -x[1])]
        
        # Settlement calculation (only for Shared transactions)
        # When tx_type is set and is not "Shared", settlement is not applicable —
        # return zeroed settlement data explicitly.
        if tx_type and tx_type != "Shared":
            direction = "Sem pendências"
            amount = 0
        else:
            shared_txs = [tx for tx in filtered if tx.get('type') == 'Shared']
            shared_per_owner = {}
            for o in mock_owners:
                shared_per_owner[o] = sum(tx.get('amount', 0) for tx in shared_txs if tx.get('owner') == o)
            
            total_shared = sum(shared_per_owner.values())
            num_owners = len(mock_owners) if mock_owners else 2
            fair_share = total_shared / num_owners if total_shared > 0 else 0
            
            balances = {o: shared_per_owner.get(o, 0) - fair_share for o in mock_owners}
            overpayers = {o: b for o, b in balances.items() if b > 0}
            underpayers = {o: b for o, b in balances.items() if b < 0}
            
            if overpayers and underpayers:
                top_overpayer = max(overpayers, key=overpayers.get)
                top_underpayer = min(underpayers, key=underpayers.get)
                direction = f"{top_underpayer} deve a {top_overpayer}"
                amount = abs(underpayers[top_underpayer])
            else:
                direction = "Sem pendências"
                amount = 0
        
        _mock_result = {
            "total_spend": total_spend,
            "spend_by_person": [
                {"name": o, "value": spend_per_owner.get(o, 0)}
                for o in mock_owners
            ],
            "spend_by_category": spend_by_category,
            "settlement": {
                "direction": direction,
                "amount": round(amount, 2)
            }
        }
        dashboard_cache.set(cache_key, _mock_result)
        return _mock_result
    
    # BIGQUERY MODE
    try:
        bq_owners = _get_workspace_owner_names(tenant.tenant_id)

        # Helper to query totals per owner
        def get_totals_bq(s_date, e_date):
            q_totals = f"""
                SELECT 
                    IFNULL(SUM(amount), 0) as total_spend,
                    owner,
                    IFNULL(SUM(amount), 0) as owner_spend
                FROM `{TABLE_GOLD}`
                WHERE tenant_id = @tenant_id AND month_ref >= @s AND month_ref <= @e
            """
            
            params_t = [
                bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant.tenant_id),
                bigquery.ScalarQueryParameter("s", "STRING", s_date),
                bigquery.ScalarQueryParameter("e", "STRING", e_date)
            ]
            
            filter_clause_t = ""
            if owner:
                filter_clause_t += " AND owner = @owner"
                params_t.append(bigquery.ScalarQueryParameter("owner", "STRING", owner))
            if tx_type:
                filter_clause_t += " AND type = @tx_type"
                params_t.append(bigquery.ScalarQueryParameter("tx_type", "STRING", tx_type))
            
            # Use GROUP BY owner for dynamic owner support
            q_totals = f"""
                SELECT 
                    owner,
                    IFNULL(SUM(amount), 0) as owner_spend
                FROM `{TABLE_GOLD}`
                WHERE tenant_id = @tenant_id AND month_ref >= @s AND month_ref <= @e {filter_clause_t}
                GROUP BY owner
            """

            conf_t = bigquery.QueryJobConfig(query_parameters=params_t)
            rows = list(bq_client.query(q_totals, job_config=conf_t))
            result = {'total_spend': 0}
            for r in rows:
                o_name = r.owner
                o_spend = r.owner_spend or 0
                result['total_spend'] += o_spend
                result[f'{o_name}_spend'] = o_spend
            return result

        # 1. Current Period
        current = get_totals_bq(start, end_month)
        
        # 2. Last Year Period
        def get_past_date_str_bq(date_str):
            y, m = map(int, date_str.split('-'))
            return f"{y-1}-{m:02d}"
            
        start_ly = get_past_date_str_bq(start)
        end_ly = get_past_date_str_bq(end_month)
        last_year = get_totals_bq(start_ly, end_ly)

        # 3. Category Spend (Current Only)
        base_where = "tenant_id = @tenant_id AND month_ref >= @start AND month_ref <= @end"
        params_base = [
            bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant.tenant_id),
            bigquery.ScalarQueryParameter("start", "STRING", start),
            bigquery.ScalarQueryParameter("end", "STRING", end_month)
        ]
        
        if owner:
            base_where += " AND owner = @owner"
            params_base.append(bigquery.ScalarQueryParameter("owner", "STRING", owner))
        if tx_type:
            base_where += " AND type = @tx_type"
            params_base.append(bigquery.ScalarQueryParameter("tx_type", "STRING", tx_type))

        query_cat = f"""
            SELECT IFNULL(category, 'Outros') as category, SUM(amount) as value
            FROM `{TABLE_GOLD}`
            WHERE {base_where}
            GROUP BY category
            ORDER BY value DESC
        """
        job_config_cat = bigquery.QueryJobConfig(query_parameters=params_base)
        result_cat = [dict(row) for row in bq_client.query(query_cat, job_config=job_config_cat)]
        
        # 4. Settlement Logic (Current Period, Shared Only)
        # When tx_type is set and is not "Shared", settlement is not applicable —
        # skip the query entirely and return zeroed settlement data.
        if tx_type and tx_type != "Shared":
            direction = "Sem pendências"
            amount = 0
        else:
            # Build settlement_where independently from base_where — only include
            # tenant_id and date range filters, NOT the tx_type filter.
            settlement_where = "tenant_id = @tenant_id AND month_ref >= @start AND month_ref <= @end"
            settlement_params = [
                bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant.tenant_id),
                bigquery.ScalarQueryParameter("start", "STRING", start),
                bigquery.ScalarQueryParameter("end", "STRING", end_month),
            ]
            if owner:
                settlement_where += " AND owner = @owner"
                settlement_params.append(bigquery.ScalarQueryParameter("owner", "STRING", owner))
            settlement_where += " AND type = 'Shared'"

            query_settlement = f"""
                SELECT 
                    owner,
                    SUM(amount) as shared_paid
                FROM `{TABLE_GOLD}`
                WHERE {settlement_where}
                GROUP BY owner
            """
            job_config_set = bigquery.QueryJobConfig(query_parameters=settlement_params)
            settlement_rows = [dict(row) for row in bq_client.query(query_settlement, job_config=job_config_set)]

            paid_by_owner = {}
            for row in settlement_rows:
                paid_by_owner[row['owner']] = row['shared_paid'] or 0

            total_shared = sum(paid_by_owner.values())
            num_owners = len(bq_owners) if bq_owners else 2
            fair_share = total_shared / num_owners if total_shared > 0 else 0

            balances = {o: paid_by_owner.get(o, 0) - fair_share for o in bq_owners}
            overpayers = {o: b for o, b in balances.items() if b > 0}
            underpayers = {o: b for o, b in balances.items() if b < 0}

            if overpayers and underpayers:
                top_overpayer = max(overpayers, key=overpayers.get)
                top_underpayer = min(underpayers, key=underpayers.get)
                direction = f"{top_underpayer} deve a {top_overpayer}"
                amount = abs(underpayers[top_underpayer])
            else:
                direction = "Sem pendências"
                amount = 0

        _bq_result = {
            "total_spend": current.get('total_spend', 0),
            "total_spend_last_year": last_year.get('total_spend', 0),
            "spend_by_person": [
                {
                    "name": o,
                    "value": current.get(f'{o}_spend', 0),
                    "value_last_year": last_year.get(f'{o}_spend', 0),
                }
                for o in bq_owners
            ],
            "spend_by_category": [{"name": r['category'], "value": r['value']} for r in result_cat],
            "settlement": {
                "direction": direction,
                "amount": round(amount, 2)
            }
        }
        dashboard_cache.set(cache_key, _bq_result)
        return _bq_result

    except Exception as e:
        logger.error("Error: %s", e)
        # Fallback: return error response
        return {"error": str(e)}

@app.get("/trend-data")
def get_trend_data(
    start: str,
    end: str = None,
    owner: str = None,
    tx_type: str = None,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Returns daily or monthly aggregated spend data for charts.
    - Daily aggregation for ranges <= 90 days
    - Monthly aggregation for longer ranges
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    from datetime import datetime, timedelta
    
    end_month = end or start
    if end_month < start:
        start, end_month = end_month, start
    
    # Calculate if we should use daily or monthly aggregation
    # Parse start/end as YYYY-MM and calculate difference
    start_date = datetime.strptime(start + "-01", "%Y-%m-%d")
    end_date = datetime.strptime(end_month + "-01", "%Y-%m-%d")
    # Move end_date to last day of month
    if end_date.month == 12:
        end_date = end_date.replace(year=end_date.year + 1, month=1) - timedelta(days=1)
    else:
        end_date = end_date.replace(month=end_date.month + 1) - timedelta(days=1)
    
    days_diff = (end_date - start_date).days
    use_daily = days_diff <= 90
    
    # SQLITE MODE
    if USE_SQLITE:
        conn = get_db_connection()
        c = conn.cursor()
        
        if use_daily:
            # Daily aggregation
            query = """
                SELECT date as period, SUM(amount) as total
                FROM transactions_gold
                WHERE tenant_id = ? AND month_ref >= ? AND month_ref <= ?
            """
            params = [tenant.tenant_id, start, end_month]
        else:
            # Monthly aggregation
            query = """
                SELECT month_ref as period, SUM(amount) as total
                FROM transactions_gold
                WHERE tenant_id = ? AND month_ref >= ? AND month_ref <= ?
            """
            params = [tenant.tenant_id, start, end_month]
        
        if owner:
            query += " AND owner = ?"
            params.append(owner)
        if tx_type:
            query += " AND type = ?"
            params.append(tx_type)
        
        if use_daily:
            query += " GROUP BY date ORDER BY date ASC"
        else:
            query += " GROUP BY month_ref ORDER BY month_ref ASC"
        
        c.execute(query, params)
        results = [{"period": row[0], "total": row[1] or 0} for row in c.fetchall()]
        conn.close()
        
        return {
            "granularity": "daily" if use_daily else "monthly",
            "data": results
        }
    
    # MOCK MODE
    if USE_MOCK or bq_client is None:
        return {
            "granularity": "daily" if use_daily else "monthly",
            "data": []
        }
    
    # BIGQUERY MODE - Analytics
    try:
        if use_daily:
            query = f"""
                SELECT date as period, SUM(amount) as total
                FROM `{TABLE_GOLD}`
                WHERE tenant_id = @tenant_id AND month_ref >= @start AND month_ref <= @end
            """
        else:
            query = f"""
                SELECT month_ref as period, SUM(amount) as total
                FROM `{TABLE_GOLD}`
                WHERE tenant_id = @tenant_id AND month_ref >= @start AND month_ref <= @end
            """
        
        params = [
            bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant.tenant_id),
            bigquery.ScalarQueryParameter("start", "STRING", start),
            bigquery.ScalarQueryParameter("end", "STRING", end_month)
        ]
        
        if owner:
            query += " AND owner = @owner"
            params.append(bigquery.ScalarQueryParameter("owner", "STRING", owner))
        if tx_type:
            query += " AND type = @tx_type"
            params.append(bigquery.ScalarQueryParameter("tx_type", "STRING", tx_type))
        
        if use_daily:
            query += " GROUP BY date ORDER BY date ASC"
        else:
            query += " GROUP BY month_ref ORDER BY month_ref ASC"
        
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        query_job = bq_client.query(query, job_config=job_config)
        results = [{"period": row.period, "total": row.total or 0} for row in query_job]
        
        return {
            "granularity": "daily" if use_daily else "monthly",
            "data": results
        }
    except Exception as e:
        logger.error("Error: %s", e)
        return {
            "granularity": "daily" if use_daily else "monthly",
            "data": []
        }

@app.post("/sync-firestore-to-bigquery")
def sync_firestore_to_bigquery(tenant: TenantContext = Depends(get_tenant_context)):
    """
    Synchronizes tenant transactions from Firestore to BigQuery.
    Uses tenant-scoped DELETE + batch load to avoid cross-tenant data loss.
    """
    _require_data_access(tenant)
    _require_tenant_id(tenant)
    # Only works in cloud mode
    if USE_SQLITE or USE_MOCK:
        return {"status": "skipped", "message": "Sync only available in cloud mode", "synced_count": 0}
    
    if not db_firestore or not bq_client:
        raise HTTPException(status_code=500, detail="Cloud clients not initialized")
    
    try:
        # 1. Read Firestore — filter by tenant_id at the query level
        docs = db_firestore.collection(FIRESTORE_COLLECTION).where(
            "tenant_id", "==", tenant.tenant_id
        ).stream()
        
        firestore_transactions = []
        for doc in docs:
            data = doc.to_dict() or {}
            data['id'] = doc.id
            firestore_transactions.append(data)
        
        if not firestore_transactions:
            return {"status": "success", "message": "No transactions to sync", "synced_count": 0}
        
        # 2. Remove only this tenant data from BigQuery before reloading
        delete_query = f"DELETE FROM `{TABLE_GOLD}` WHERE tenant_id = @tenant_id"
        delete_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant.tenant_id)]
        )
        bq_client.query(delete_query, job_config=delete_config).result()
        
        # 3. Prepare rows for batch insert
        gold_rows = []
        for tx in firestore_transactions:
            gold_rows.append({
                "id": tx.get('id'),
                "date": _serialize_firestore_value(tx.get('date')),
                "month_ref": _serialize_firestore_value(tx.get('month_ref')),
                "amount": float(tx.get('amount') or 0),
                "merchant_clean": tx.get('merchant_clean'),
                "category": tx.get('category'),
                "subcategory": tx.get('subcategory'),
                "type": tx.get('type'),
                "owner": tx.get('owner'),
                "tenant_id": tenant.tenant_id,
                "created_at": _serialize_firestore_value(tx.get('created_at')) or datetime.datetime.now().isoformat()
            })
        
        # 4. Use load_table_from_json for batch insert (not streaming)
        # This avoids the streaming buffer entirely
        from google.cloud.bigquery import LoadJobConfig, SourceFormat
        
        job_config = LoadJobConfig(
            source_format=SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition="WRITE_APPEND",
        )
        
        load_job = bq_client.load_table_from_json(
            gold_rows,
            TABLE_GOLD,
            job_config=job_config
        )
        load_job.result()  # Wait for completion
        
        return {
            "status": "success",
            "message": f"Synced {len(gold_rows)} transactions to BigQuery for tenant {tenant.tenant_id}",
            "synced_count": len(gold_rows)
        }
        
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # Local dev run
    uvicorn.run(app, host="0.0.0.0", port=8000)
