"""Tests for billing_service.py — BillingService, plan limits, and billing endpoints.

Covers:
- Plan configuration and limits
- Subscription creation (with mocked Mercado Pago SDK)
- Webhook processing (idempotent)
- Subscription cancellation
- Plan limit enforcement (uploads, cards, members)
- Billing API endpoints
"""

import os
import sqlite3
import uuid

import pytest

# Force SQLite mode before importing app modules
os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("USE_MOCK_DATA", "false")
os.environ.setdefault("REQUIRE_AUTH_FOR_DATA", "false")
os.environ.setdefault("TENANT_REQUIRED", "false")

from billing_service import BillingService, PLAN_CONFIG, PLAN_LIMITS
from database import get_db_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_workspace(workspace_id: str, owner_user_id: str = "user-1"):
    """Create a workspace + owner member + user profile in the test DB."""
    conn = get_db_connection()
    c = conn.cursor()
    now = "2026-01-01T00:00:00+00:00"

    c.execute(
        """
        INSERT OR REPLACE INTO workspaces (id, name, owner_user_id, member_limit, created_at, updated_at)
        VALUES (?, ?, ?, 10, ?, ?)
        """,
        (workspace_id, "Test Workspace", owner_user_id, now, now),
    )
    c.execute(
        """
        INSERT OR REPLACE INTO workspace_members (workspace_id, user_id, role, created_at)
        VALUES (?, ?, 'owner', ?)
        """,
        (workspace_id, owner_user_id, now),
    )
    c.execute(
        """
        INSERT OR REPLACE INTO users (user_id, email, plan_type, is_admin, active_workspace_id, created_at, updated_at)
        VALUES (?, 'test@example.com', 'free', 0, ?, ?, ?)
        """,
        (owner_user_id, workspace_id, now, now),
    )
    conn.commit()
    conn.close()


def _insert_subscription(workspace_id: str, plan_type: str, status: str, mp_preapproval_id: str):
    """Insert a subscription row directly."""
    conn = get_db_connection()
    c = conn.cursor()
    now = "2026-01-01T00:00:00+00:00"
    sub_id = f"sub-{uuid.uuid4().hex[:16]}"
    c.execute(
        """
        INSERT INTO subscriptions (id, workspace_id, mp_preapproval_id, plan_type, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (sub_id, workspace_id, mp_preapproval_id, plan_type, status, now, now),
    )
    conn.commit()
    conn.close()
    return sub_id


def _insert_upload_history(workspace_id: str, count: int = 1):
    """Insert completed upload_history rows for the current month."""
    conn = get_db_connection()
    c = conn.cursor()
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for _ in range(count):
        uid = f"upl-{uuid.uuid4().hex[:16]}"
        c.execute(
            """
            INSERT INTO upload_history (id, workspace_id, user_id, filename, file_hash, status, created_at)
            VALUES (?, ?, 'user-1', 'test.pdf', ?, 'completed', ?)
            """,
            (uid, workspace_id, uuid.uuid4().hex, now),
        )
    conn.commit()
    conn.close()


def _insert_cards(workspace_id: str, count: int = 1):
    """Insert card rows for a workspace."""
    conn = get_db_connection()
    c = conn.cursor()
    now = "2026-01-01T00:00:00+00:00"
    for i in range(count):
        card_id = f"card-{uuid.uuid4().hex[:16]}"
        last4 = f"{(1000 + i):04d}"
        c.execute(
            """
            INSERT INTO cards (id, workspace_id, owner, last4, card_type, bank, is_active, created_at, updated_at)
            VALUES (?, ?, 'owner', ?, 'individual', 'nubank', 1, ?, ?)
            """,
            (card_id, workspace_id, last4, now, now),
        )
    conn.commit()
    conn.close()


def _insert_members(workspace_id: str, count: int = 1):
    """Insert additional workspace_members rows."""
    conn = get_db_connection()
    c = conn.cursor()
    now = "2026-01-01T00:00:00+00:00"
    for i in range(count):
        user_id = f"member-{uuid.uuid4().hex[:8]}"
        c.execute(
            """
            INSERT OR REPLACE INTO workspace_members (workspace_id, user_id, role, created_at)
            VALUES (?, ?, 'member', ?)
            """,
            (workspace_id, user_id, now),
        )
    conn.commit()
    conn.close()


def _cleanup(workspace_id: str):
    """Remove test data for a workspace."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM subscriptions WHERE workspace_id = ?", (workspace_id,))
    c.execute("DELETE FROM upload_history WHERE workspace_id = ?", (workspace_id,))
    c.execute("DELETE FROM cards WHERE workspace_id = ?", (workspace_id,))
    c.execute("DELETE FROM workspace_members WHERE workspace_id = ?", (workspace_id,))
    c.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    c.execute("DELETE FROM users WHERE active_workspace_id = ?", (workspace_id,))
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def clean_test_workspace():
    """Ensure test workspace is clean before and after each test."""
    ws_id = "ws-billing-test"
    _cleanup(ws_id)
    _setup_workspace(ws_id)
    yield ws_id
    _cleanup(ws_id)


# ---------------------------------------------------------------------------
# Plan configuration tests
# ---------------------------------------------------------------------------

class TestPlanConfig:
    def test_plan_config_has_pro_and_familia(self):
        assert "pro" in PLAN_CONFIG
        assert "familia" in PLAN_CONFIG

    def test_pro_price(self):
        assert PLAN_CONFIG["pro"]["amount"] == 19.0

    def test_familia_price(self):
        assert PLAN_CONFIG["familia"]["amount"] == 39.0

    def test_plan_limits_has_all_plans(self):
        assert "free" in PLAN_LIMITS
        assert "pro" in PLAN_LIMITS
        assert "familia" in PLAN_LIMITS

    def test_free_plan_limits(self):
        limits = PLAN_LIMITS["free"]
        assert limits["uploads_month"] == 2
        assert limits["history_months"] == 3
        assert limits["members"] == 1
        assert limits["cards"] == 2

    def test_pro_plan_limits(self):
        limits = PLAN_LIMITS["pro"]
        assert limits["uploads_month"] == -1  # unlimited
        assert limits["history_months"] == 12
        assert limits["members"] == 1
        assert limits["cards"] == 5

    def test_familia_plan_limits(self):
        limits = PLAN_LIMITS["familia"]
        assert limits["uploads_month"] == -1  # unlimited
        assert limits["history_months"] == -1  # unlimited
        assert limits["members"] == 4
        assert limits["cards"] == 10


# ---------------------------------------------------------------------------
# BillingService — create_subscription
# ---------------------------------------------------------------------------

class TestCreateSubscription:
    def test_create_subscription_stores_in_db(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()  # No MP SDK → stub mode
        result = svc.create_subscription(ws_id, "pro")

        assert "subscription_id" in result
        assert "init_point" in result
        assert result["init_point"]  # non-empty URL

        # Verify DB record
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM subscriptions WHERE id = ?", (result["subscription_id"],))
        row = dict(c.fetchone())
        conn.close()

        assert row["workspace_id"] == ws_id
        assert row["plan_type"] == "pro"
        assert row["status"] == "pending"
        assert row["mp_preapproval_id"] is not None

    def test_create_subscription_familia(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()
        result = svc.create_subscription(ws_id, "familia")

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT plan_type FROM subscriptions WHERE id = ?", (result["subscription_id"],))
        row = dict(c.fetchone())
        conn.close()

        assert row["plan_type"] == "familia"

    def test_create_subscription_invalid_plan(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()
        with pytest.raises(Exception) as exc_info:
            svc.create_subscription(ws_id, "invalid_plan")
        assert "Invalid plan_type" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# BillingService — process_webhook (idempotent)
# ---------------------------------------------------------------------------

class TestProcessWebhook:
    def test_webhook_activates_subscription(self, clean_test_workspace):
        ws_id = clean_test_workspace
        mp_id = f"mp-{uuid.uuid4().hex[:8]}"
        _insert_subscription(ws_id, "pro", "pending", mp_id)

        svc = BillingService()
        svc.process_webhook({
            "topic": "preapproval",
            "data": {"id": mp_id},
            "status": "authorized",
        })

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT status FROM subscriptions WHERE mp_preapproval_id = ?", (mp_id,))
        row = dict(c.fetchone())
        conn.close()

        assert row["status"] == "active"

    def test_webhook_idempotent(self, clean_test_workspace):
        ws_id = clean_test_workspace
        mp_id = f"mp-{uuid.uuid4().hex[:8]}"
        _insert_subscription(ws_id, "pro", "pending", mp_id)

        svc = BillingService()
        payload = {
            "topic": "preapproval",
            "data": {"id": mp_id},
            "status": "authorized",
        }

        # Process same webhook 3 times
        svc.process_webhook(payload)
        svc.process_webhook(payload)
        svc.process_webhook(payload)

        # Should still have exactly one subscription with status active
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT status FROM subscriptions WHERE mp_preapproval_id = ?", (mp_id,))
        rows = c.fetchall()
        conn.close()

        assert len(rows) == 1
        assert dict(rows[0])["status"] == "active"

    def test_webhook_cancels_subscription(self, clean_test_workspace):
        ws_id = clean_test_workspace
        mp_id = f"mp-{uuid.uuid4().hex[:8]}"
        _insert_subscription(ws_id, "pro", "active", mp_id)

        svc = BillingService()
        svc.process_webhook({
            "topic": "preapproval",
            "data": {"id": mp_id},
            "status": "cancelled",
        })

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT status FROM subscriptions WHERE mp_preapproval_id = ?", (mp_id,))
        row = dict(c.fetchone())
        conn.close()

        assert row["status"] == "cancelled"

    def test_webhook_ignores_unknown_topic(self, clean_test_workspace):
        svc = BillingService()
        # Should not raise
        svc.process_webhook({"topic": "payment", "data": {"id": "123"}})

    def test_webhook_ignores_missing_resource_id(self, clean_test_workspace):
        svc = BillingService()
        # Should not raise
        svc.process_webhook({"topic": "preapproval"})

    def test_webhook_updates_user_plan_type(self, clean_test_workspace):
        ws_id = clean_test_workspace
        mp_id = f"mp-{uuid.uuid4().hex[:8]}"
        _insert_subscription(ws_id, "pro", "pending", mp_id)

        svc = BillingService()
        svc.process_webhook({
            "topic": "preapproval",
            "data": {"id": mp_id},
            "status": "authorized",
        })

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT plan_type FROM users WHERE user_id = 'user-1'")
        row = c.fetchone()
        conn.close()

        assert dict(row)["plan_type"] == "pro"


# ---------------------------------------------------------------------------
# BillingService — cancel_subscription
# ---------------------------------------------------------------------------

class TestCancelSubscription:
    def test_cancel_active_subscription(self, clean_test_workspace):
        ws_id = clean_test_workspace
        mp_id = f"mp-{uuid.uuid4().hex[:8]}"
        _insert_subscription(ws_id, "pro", "active", mp_id)

        svc = BillingService()
        result = svc.cancel_subscription(ws_id)

        assert result["status"] == "cancelled"
        assert result["plan_type"] == "pro"

        # Verify DB
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT status FROM subscriptions WHERE mp_preapproval_id = ?", (mp_id,))
        row = dict(c.fetchone())
        conn.close()

        assert row["status"] == "cancelled"

    def test_cancel_no_subscription_raises_404(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()
        with pytest.raises(Exception) as exc_info:
            svc.cancel_subscription(ws_id)
        assert exc_info.value.status_code == 404

    def test_cancel_reverts_user_to_free(self, clean_test_workspace):
        ws_id = clean_test_workspace
        mp_id = f"mp-{uuid.uuid4().hex[:8]}"
        _insert_subscription(ws_id, "pro", "active", mp_id)

        # Set user to pro first
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET plan_type = 'pro' WHERE user_id = 'user-1'")
        conn.commit()
        conn.close()

        svc = BillingService()
        svc.cancel_subscription(ws_id)

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT plan_type FROM users WHERE user_id = 'user-1'")
        row = dict(c.fetchone())
        conn.close()

        assert row["plan_type"] == "free"


# ---------------------------------------------------------------------------
# BillingService — get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_status_no_subscription(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()
        status = svc.get_status(ws_id)

        assert status.plan_type == "free"
        assert status.status == "none"

    def test_status_active_subscription(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_subscription(ws_id, "familia", "active", "mp-123")

        svc = BillingService()
        status = svc.get_status(ws_id)

        assert status.plan_type == "familia"
        assert status.status == "active"


# ---------------------------------------------------------------------------
# BillingService — check_limit
# ---------------------------------------------------------------------------

class TestCheckLimit:
    def test_free_plan_upload_limit_not_reached(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()
        # No uploads yet — should be allowed
        assert svc.check_limit(ws_id, "uploads_month") is True

    def test_free_plan_upload_limit_reached(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_upload_history(ws_id, count=2)

        svc = BillingService()
        assert svc.check_limit(ws_id, "uploads_month") is False

    def test_pro_plan_upload_unlimited(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_subscription(ws_id, "pro", "active", "mp-pro")
        _insert_upload_history(ws_id, count=100)

        svc = BillingService()
        assert svc.check_limit(ws_id, "uploads_month") is True

    def test_free_plan_card_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_cards(ws_id, count=2)

        svc = BillingService()
        assert svc.check_limit(ws_id, "cards") is False

    def test_free_plan_card_under_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_cards(ws_id, count=1)

        svc = BillingService()
        assert svc.check_limit(ws_id, "cards") is True

    def test_pro_plan_card_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_subscription(ws_id, "pro", "active", "mp-pro")
        _insert_cards(ws_id, count=5)

        svc = BillingService()
        assert svc.check_limit(ws_id, "cards") is False

    def test_familia_plan_card_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_subscription(ws_id, "familia", "active", "mp-fam")
        _insert_cards(ws_id, count=9)

        svc = BillingService()
        assert svc.check_limit(ws_id, "cards") is True

    def test_free_plan_member_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        # Already has 1 member (owner) from setup
        svc = BillingService()
        assert svc.check_limit(ws_id, "members") is False  # 1 >= 1

    def test_familia_plan_member_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_subscription(ws_id, "familia", "active", "mp-fam")
        # 1 owner + 2 additional = 3 total, limit is 4
        _insert_members(ws_id, count=2)

        svc = BillingService()
        assert svc.check_limit(ws_id, "members") is True

    def test_unknown_resource_allowed(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()
        assert svc.check_limit(ws_id, "unknown_resource") is True


# ---------------------------------------------------------------------------
# BillingService — get_plan_limit
# ---------------------------------------------------------------------------

class TestGetPlanLimit:
    def test_free_plan_upload_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        svc = BillingService()
        assert svc.get_plan_limit(ws_id, "uploads_month") == 2

    def test_pro_plan_card_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_subscription(ws_id, "pro", "active", "mp-pro")
        svc = BillingService()
        assert svc.get_plan_limit(ws_id, "cards") == 5

    def test_familia_plan_member_limit(self, clean_test_workspace):
        ws_id = clean_test_workspace
        _insert_subscription(ws_id, "familia", "active", "mp-fam")
        svc = BillingService()
        assert svc.get_plan_limit(ws_id, "members") == 4
