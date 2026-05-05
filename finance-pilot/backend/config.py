"""
Centralized configuration — all settings come from environment variables.
No hardcoded secrets or PII.
"""
import os
import logging
import sys
from pathlib import Path
from typing import List, Set

# ─── Structured Logging ───
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("finance-pilot")

def _parse_email_list(value: str) -> List[str]:
    return [
        item.strip().lower()
        for item in (value or "").split(",")
        if item.strip()
    ]

# ─── GCP / Firebase ───
PROJECT_ID = os.environ.get("PROJECT_ID", "aifin-project")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", PROJECT_ID)
BUCKET_RAW = f"{PROJECT_ID}-raw-uploads"

# ─── Tenant ───
FIRESTORE_COLLECTION = "transactions"
TENANT_HEADER_NAME = os.environ.get("TENANT_HEADER_NAME", "X-Tenant-ID")
DEFAULT_TENANT_ID = os.environ.get("DEFAULT_TENANT_ID", "default")
TENANT_REQUIRED = os.environ.get("TENANT_REQUIRED", "true").lower() == "true"

# ─── Collections ───
USERS_COLLECTION = os.environ.get("USERS_COLLECTION", "users")
WORKSPACES_COLLECTION = os.environ.get("WORKSPACES_COLLECTION", "workspaces")
WORKSPACE_MEMBERS_COLLECTION = os.environ.get("WORKSPACE_MEMBERS_COLLECTION", "workspace_members")
WORKSPACE_INVITES_COLLECTION = os.environ.get("WORKSPACE_INVITES_COLLECTION", "workspace_invites")
NET_WORTH_COLLECTION = os.environ.get("NET_WORTH_COLLECTION", "net_worth_monthly")
CURRENT_ACCOUNT_COLLECTION = os.environ.get("CURRENT_ACCOUNT_COLLECTION", "current_account_movements")

# ─── Workspace ───
PREMIUM_EMAILS: Set[str] = set(_parse_email_list(os.environ.get("PREMIUM_EMAILS", "")))
ADMIN_EMAILS: Set[str] = set(_parse_email_list(os.environ.get("ADMIN_EMAILS", "")))

# ─── Modes ───
USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() == "true"
USE_MOCK = os.environ.get("USE_MOCK_DATA", "false").lower() == "true"
REQUIRE_AUTH_FOR_DATA = os.environ.get("REQUIRE_AUTH_FOR_DATA", "true").lower() == "true"
MOCK_DATA_PATH = Path(__file__).parent.parent / "data" / "gold_transactions.json"

# ─── CORS ───
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000",
    ).split(",")
    if origin.strip()
]
CORS_ALLOWED_METHODS = [
    method.strip()
    for method in os.environ.get(
        "CORS_ALLOWED_METHODS", "GET,POST,PUT,DELETE,OPTIONS"
    ).split(",")
    if method.strip()
]
CORS_ALLOWED_HEADERS = [
    header.strip()
    for header in os.environ.get(
        "CORS_ALLOWED_HEADERS",
        "Authorization,Content-Type,X-Tenant-ID",
    ).split(",")
    if header.strip()
]

# ─── Plans ───
PLAN_LIMITS = {
    "free": {"max_workspaces": 1, "max_members_per_workspace": 1},
    "paid": {"max_workspaces": 3, "max_members_per_workspace": 2},
}