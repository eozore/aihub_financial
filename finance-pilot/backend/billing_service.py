"""Billing service — Mercado Pago subscription management and plan limit enforcement.

Provides:
- ``BillingService`` class for creating/cancelling subscriptions via Mercado Pago
- Idempotent webhook processing for IPN notifications
- Plan limit checking for uploads, cards, and members

Requirements: 8.1, 8.2, 8.4, 8.5, 8.6, 8.7, 8.8
"""

import datetime
import logging
import os
import uuid
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from database import get_db_connection
from helpers import utc_now_iso

# In cloud mode (USE_SQLITE=false) the subscriptions table lives in SQLite
# only when running locally.  In production the billing tables are not yet
# migrated to Firestore/BigQuery, so we degrade gracefully: limits are not
# enforced and status always returns "none" / "free".
_USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() == "true"

logger = logging.getLogger("finance-pilot.billing")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateSubscriptionRequest(BaseModel):
    plan_type: Literal["pro", "familia"]


class CreateSubscriptionResponse(BaseModel):
    subscription_id: str
    init_point: str  # Mercado Pago checkout URL


class BillingStatusResponse(BaseModel):
    plan_type: Literal["free", "pro", "familia"]
    status: Literal["active", "paused", "cancelled", "pending", "none"]
    current_period_end: Optional[str] = None


# ---------------------------------------------------------------------------
# Plan configuration
# ---------------------------------------------------------------------------

PLAN_CONFIG = {
    "pro": {"amount": 19.0, "reason": "Finance Pilot Pro"},
    "familia": {"amount": 39.0, "reason": "Finance Pilot Família"},
}

PLAN_LIMITS = {
    "free": {"uploads_month": 2, "history_months": 3, "members": 1, "cards": 2},
    "pro": {"uploads_month": -1, "history_months": 12, "members": 1, "cards": 5},
    "familia": {"uploads_month": -1, "history_months": -1, "members": 4, "cards": 10},
}

# Mercado Pago status → internal status mapping
_MP_STATUS_MAP = {
    "authorized": "active",
    "paused": "paused",
    "cancelled": "cancelled",
    "pending": "pending",
}


# ---------------------------------------------------------------------------
# Mercado Pago SDK wrapper (mockable for tests)
# ---------------------------------------------------------------------------

def _get_mp_sdk():
    """Return a configured Mercado Pago SDK instance.

    Reads ``MERCADO_PAGO_ACCESS_TOKEN`` from the environment.
    Returns ``None`` when the token is not set (e.g. in tests).
    """
    access_token = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN")
    if not access_token:
        return None
    try:
        import mercadopago  # noqa: E402
        return mercadopago.SDK(access_token)
    except Exception as exc:
        logger.warning("Could not initialise Mercado Pago SDK: %s", exc)
        return None


# ---------------------------------------------------------------------------
# BillingService
# ---------------------------------------------------------------------------

class BillingService:
    """Integração com Mercado Pago para assinaturas recorrentes."""

    PLAN_CONFIG = PLAN_CONFIG
    PLAN_LIMITS = PLAN_LIMITS

    def __init__(self, mp_sdk=None):
        """Initialise with an optional Mercado Pago SDK instance.

        When *mp_sdk* is ``None`` the service will attempt to create one from
        the environment on first use.
        """
        self._mp_sdk = mp_sdk

    @property
    def mp_sdk(self):
        if self._mp_sdk is None:
            self._mp_sdk = _get_mp_sdk()
        return self._mp_sdk

    # ------------------------------------------------------------------
    # create_subscription
    # ------------------------------------------------------------------

    def create_subscription(self, workspace_id: str, plan_type: str) -> dict:
        """Create a Mercado Pago ``preapproval`` and return ``init_point``.

        Returns a dict with ``subscription_id`` and ``init_point``.
        """
        if plan_type not in self.PLAN_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid plan_type: {plan_type}")

        if not _USE_SQLITE:
            # In cloud mode, billing DB tables are not yet available.
            # Return a stub response so the UI doesn't crash.
            logger.warning("create_subscription called in cloud mode — returning stub")
            stub_id = f"sub-stub-{uuid.uuid4().hex[:8]}"
            return {
                "subscription_id": stub_id,
                "init_point": "https://mercadopago.com.br/stub-checkout/" + stub_id,
            }

        config = self.PLAN_CONFIG[plan_type]
        now = utc_now_iso()
        subscription_id = f"sub-{uuid.uuid4().hex[:16]}"

        # Build Mercado Pago preapproval payload
        back_url = os.environ.get("BILLING_BACK_URL", "http://localhost:3000/workspace")
        preapproval_data = {
            "reason": config["reason"],
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": config["amount"],
                "currency_id": "BRL",
            },
            "back_url": back_url,
            "external_reference": f"{workspace_id}:{subscription_id}",
        }

        mp_preapproval_id = None
        init_point = ""

        sdk = self.mp_sdk
        if sdk is not None:
            try:
                result = sdk.preapproval().create(preapproval_data)
                response = result.get("response", {})
                mp_preapproval_id = response.get("id")
                init_point = response.get("init_point", "")
            except Exception as exc:
                logger.error("Mercado Pago create preapproval failed: %s", exc)
                raise HTTPException(
                    status_code=502,
                    detail="Failed to create subscription on payment provider",
                ) from exc
        else:
            logger.warning("Mercado Pago SDK not available; returning stub subscription")
            mp_preapproval_id = f"mp-stub-{uuid.uuid4().hex[:8]}"
            init_point = f"https://mercadopago.com.br/stub-checkout/{mp_preapproval_id}"

        # Persist subscription in the database
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO subscriptions
                    (id, workspace_id, mp_preapproval_id, plan_type, status,
                     current_period_start, current_period_end, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, NULL, ?, ?)
                """,
                (
                    subscription_id,
                    workspace_id,
                    mp_preapproval_id,
                    plan_type,
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "subscription_id": subscription_id,
            "init_point": init_point,
        }

    # ------------------------------------------------------------------
    # process_webhook  (idempotent)
    # ------------------------------------------------------------------

    def process_webhook(self, payload: dict) -> None:
        """Process an IPN notification from Mercado Pago.

        Idempotent: processing the same payload multiple times produces the
        same final state without duplicating records.
        """
        if not _USE_SQLITE:
            logger.warning("process_webhook called in cloud mode — skipping DB update")
            return
        # Mercado Pago IPN sends topic + id (or data.id)
        topic = payload.get("topic") or payload.get("type", "")
        resource_id = payload.get("data", {}).get("id") or payload.get("id")

        if not resource_id:
            logger.warning("Webhook payload missing resource id: %s", payload)
            return

        # We only care about preapproval (subscription) events
        if topic not in ("preapproval", "subscription_preapproval"):
            logger.info("Ignoring webhook topic: %s", topic)
            return

        # Fetch preapproval details from Mercado Pago (or use payload directly)
        mp_status = None
        mp_preapproval_id = str(resource_id)

        sdk = self.mp_sdk
        if sdk is not None:
            try:
                result = sdk.preapproval().get(mp_preapproval_id)
                response = result.get("response", {})
                mp_status = response.get("status")
            except Exception as exc:
                logger.error("Failed to fetch preapproval %s: %s", mp_preapproval_id, exc)
                # Fall back to status in payload if available
                mp_status = payload.get("status")
        else:
            # In test/stub mode, accept status from payload
            mp_status = payload.get("status")

        if not mp_status:
            logger.warning("Could not determine status for preapproval %s", mp_preapproval_id)
            return

        internal_status = _MP_STATUS_MAP.get(mp_status, mp_status)

        conn = get_db_connection()
        try:
            c = conn.cursor()

            # Find subscription by mp_preapproval_id
            c.execute(
                "SELECT * FROM subscriptions WHERE mp_preapproval_id = ?",
                (mp_preapproval_id,),
            )
            row = c.fetchone()
            if row is None:
                logger.warning("No subscription found for mp_preapproval_id=%s", mp_preapproval_id)
                return

            sub = dict(row)
            now = utc_now_iso()

            # Idempotency: skip if status is already the same
            if sub["status"] == internal_status:
                logger.info(
                    "Subscription %s already has status %s — skipping",
                    sub["id"],
                    internal_status,
                )
                return

            # Update subscription status
            c.execute(
                """
                UPDATE subscriptions
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (internal_status, now, sub["id"]),
            )

            # Update workspace plan_type based on subscription status
            workspace_id = sub["workspace_id"]
            if internal_status == "active":
                new_plan = sub["plan_type"]
            else:
                # If cancelled or paused, revert to free
                new_plan = "free"

            c.execute(
                """
                UPDATE workspaces
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, workspace_id),
            )

            # Also update the user profile plan_type for the workspace owner
            c.execute(
                "SELECT owner_user_id FROM workspaces WHERE id = ?",
                (workspace_id,),
            )
            ws_row = c.fetchone()
            if ws_row:
                owner_user_id = dict(ws_row)["owner_user_id"]
                c.execute(
                    """
                    UPDATE users
                    SET plan_type = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (new_plan, now, owner_user_id),
                )

            conn.commit()
            logger.info(
                "Webhook processed: subscription=%s status=%s plan=%s",
                sub["id"],
                internal_status,
                new_plan,
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # cancel_subscription
    # ------------------------------------------------------------------

    def cancel_subscription(self, workspace_id: str) -> dict:
        """Cancel the active subscription for a workspace.

        Returns a dict with the cancelled subscription details.
        """
        if not _USE_SQLITE:
            raise HTTPException(status_code=404, detail="No active subscription found")
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT * FROM subscriptions
                WHERE workspace_id = ? AND status IN ('active', 'pending')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (workspace_id,),
            )
            row = c.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="No active subscription found")

            sub = dict(row)
            mp_preapproval_id = sub.get("mp_preapproval_id")

            # Cancel on Mercado Pago
            sdk = self.mp_sdk
            if sdk is not None and mp_preapproval_id:
                try:
                    sdk.preapproval().update(
                        mp_preapproval_id,
                        {"status": "cancelled"},
                    )
                except Exception as exc:
                    logger.error("Failed to cancel preapproval on MP: %s", exc)
                    raise HTTPException(
                        status_code=502,
                        detail="Failed to cancel subscription on payment provider",
                    ) from exc

            now = utc_now_iso()
            c.execute(
                """
                UPDATE subscriptions
                SET status = 'cancelled', updated_at = ?
                WHERE id = ?
                """,
                (now, sub["id"]),
            )

            # Revert workspace to free plan
            c.execute(
                "SELECT owner_user_id FROM workspaces WHERE id = ?",
                (workspace_id,),
            )
            ws_row = c.fetchone()
            if ws_row:
                owner_user_id = dict(ws_row)["owner_user_id"]
                c.execute(
                    """
                    UPDATE users
                    SET plan_type = 'free', updated_at = ?
                    WHERE user_id = ?
                    """,
                    (now, owner_user_id),
                )

            conn.commit()

            return {
                "subscription_id": sub["id"],
                "status": "cancelled",
                "plan_type": sub["plan_type"],
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # get_status
    # ------------------------------------------------------------------

    def get_status(self, workspace_id: str) -> BillingStatusResponse:
        """Return the current billing status for a workspace."""
        # In cloud mode (no SQLite), subscriptions table is not available yet.
        # Return a safe default so the app doesn't crash.
        if not _USE_SQLITE:
            return BillingStatusResponse(plan_type="free", status="none", current_period_end=None)

        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT * FROM subscriptions
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (workspace_id,),
            )
            row = c.fetchone()
            if row is None:
                return BillingStatusResponse(
                    plan_type="free",
                    status="none",
                    current_period_end=None,
                )

            sub = dict(row)
            return BillingStatusResponse(
                plan_type=sub["plan_type"],
                status=sub["status"],
                current_period_end=sub.get("current_period_end"),
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # check_limit
    # ------------------------------------------------------------------

    def check_limit(self, workspace_id: str, resource: str) -> bool:
        """Check whether the workspace can perform an operation within plan limits.

        *resource* is one of: ``"uploads_month"``, ``"cards"``, ``"members"``.

        Returns ``True`` if the operation is allowed, ``False`` if the limit
        is reached.
        """
        # In cloud mode, billing tables are not available — allow all operations.
        if not _USE_SQLITE:
            return True

        plan_type = self._get_workspace_plan(workspace_id)
        limits = self.PLAN_LIMITS.get(plan_type, self.PLAN_LIMITS["free"])
        limit_value = limits.get(resource)

        if limit_value is None:
            # Unknown resource — allow by default
            return True

        if limit_value == -1:
            # Unlimited
            return True

        current_usage = self._get_current_usage(workspace_id, resource)
        return current_usage < limit_value

    def get_plan_limit(self, workspace_id: str, resource: str) -> int:
        """Return the numeric limit for a resource on the workspace's current plan."""
        # In cloud mode, return unlimited (-1) since billing tables are not available.
        if not _USE_SQLITE:
            return -1
        plan_type = self._get_workspace_plan(workspace_id)
        limits = self.PLAN_LIMITS.get(plan_type, self.PLAN_LIMITS["free"])
        return limits.get(resource, -1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_workspace_plan(self, workspace_id: str) -> str:
        """Determine the current plan for a workspace based on active subscriptions."""
        if not _USE_SQLITE:
            return "free"
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT plan_type FROM subscriptions
                WHERE workspace_id = ? AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (workspace_id,),
            )
            row = c.fetchone()
            if row is None:
                return "free"
            return dict(row)["plan_type"]
        finally:
            conn.close()

    def _get_current_usage(self, workspace_id: str, resource: str) -> int:
        """Query the database for current usage of a resource."""
        conn = get_db_connection()
        try:
            c = conn.cursor()

            if resource == "uploads_month":
                # Count uploads in the current calendar month
                now = datetime.datetime.now(datetime.timezone.utc)
                month_start = now.strftime("%Y-%m-01")
                c.execute(
                    """
                    SELECT COUNT(*) FROM upload_history
                    WHERE workspace_id = ?
                      AND status = 'completed'
                      AND created_at >= ?
                    """,
                    (workspace_id, month_start),
                )
                return c.fetchone()[0]

            elif resource == "cards":
                c.execute(
                    "SELECT COUNT(*) FROM cards WHERE workspace_id = ?",
                    (workspace_id,),
                )
                return c.fetchone()[0]

            elif resource == "members":
                c.execute(
                    "SELECT COUNT(*) FROM workspace_members WHERE workspace_id = ?",
                    (workspace_id,),
                )
                return c.fetchone()[0]

            else:
                return 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Module-level singleton for convenience
# ---------------------------------------------------------------------------

billing_service = BillingService()
