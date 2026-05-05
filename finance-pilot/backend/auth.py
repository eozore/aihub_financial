"""Authentication and tenant resolution middleware."""
import os
import re
from typing import Optional

from fastapi import HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from config import (
    FIREBASE_PROJECT_ID,
    TENANT_HEADER_NAME,
    DEFAULT_TENANT_ID,
    TENANT_REQUIRED,
    REQUIRE_AUTH_FOR_DATA,
)
from models import TenantContext

GOOGLE_AUTH_REQUEST = google_requests.Request()


def sanitize_tenant_id(raw_tenant: Optional[str]) -> Optional[str]:
    if raw_tenant is None:
        return None
    tenant_id = raw_tenant.strip()
    if not tenant_id:
        return None
    if len(tenant_id) > 64 or not re.fullmatch(r"[A-Za-z0-9_.-]+", tenant_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid tenant_id. Use only letters, numbers, '.', '_' or '-'.",
        )
    return tenant_id


def extract_tenant_from_claims(claims: dict) -> Optional[str]:
    claim_tenant = claims.get("tenant_id")
    if isinstance(claim_tenant, str) and claim_tenant.strip():
        return claim_tenant.strip()

    firebase_claim = claims.get("firebase")
    if isinstance(firebase_claim, dict):
        firebase_tenant = firebase_claim.get("tenant")
        if isinstance(firebase_tenant, str) and firebase_tenant.strip():
            return firebase_tenant.strip()

    return None


def require_authenticated_user(tenant: TenantContext) -> str:
    if not tenant.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return tenant.user_id


def require_data_access(tenant: TenantContext) -> None:
    if REQUIRE_AUTH_FOR_DATA and not tenant.user_id:
        raise HTTPException(status_code=401, detail="Authentication required for data access")


def require_tenant_id(tenant: TenantContext) -> str:
    """Guard that rejects any Firestore/data operation without a valid tenant_id.

    Returns the tenant_id for convenience so callers can use it directly.
    Raises HTTPException 400 when tenant_id is missing or empty.

    Note: ``"default"`` is a valid workspace id (used by legacy workspaces)
    and is intentionally allowed through.
    """
    if (
        not tenant
        or not tenant.tenant_id
        or not tenant.tenant_id.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="tenant_id is required for this operation. Provide a valid workspace context.",
        )
    return tenant.tenant_id
