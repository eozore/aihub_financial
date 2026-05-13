"""Tests for month_ref preservation when date is edited (Task 3.2)."""
import pytest
from fastapi.testclient import TestClient
from database import get_db_connection


class TestMonthRefPreservation:
    """Test that PUT /transactions preserves existing month_ref when date is edited."""

    def test_preserves_existing_month_ref_when_date_edited(self, client: TestClient, auth_headers):
        """When a transaction has a non-NULL month_ref, editing the date should NOT overwrite it."""
        # Create a transaction with a specific date
        create_resp = client.post(
            "/transactions",
            json={
                "date": "2026-04-05",
                "amount": -100.0,
                "merchant_clean": "Test Store",
                "category": "Shopping",
                "subcategory": "General",
                "owner": "Victor",
                "type": "individual",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 200
        tx_id = create_resp.json()["id"]

        # Simulate a credit card scenario: manually set month_ref to a different month
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE transactions_gold SET month_ref = ? WHERE id = ?",
            ("2026-03", tx_id),
        )
        conn.commit()
        conn.close()

        # Now edit the date — month_ref should be preserved as "2026-03"
        update_resp = client.put(
            f"/transactions/{tx_id}",
            json={"date": "2026-04-10"},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200

        # Verify month_ref was preserved
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT month_ref, date FROM transactions_gold WHERE id = ?", (tx_id,))
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row["month_ref"] == "2026-03", f"month_ref should be preserved as '2026-03', got '{row['month_ref']}'"
        assert row["date"] == "2026-04-10", f"date should be updated to '2026-04-10', got '{row['date']}'"

    def test_derives_month_ref_from_date_when_null(self, client: TestClient, auth_headers):
        """When a transaction has NULL month_ref, editing the date should derive month_ref from new date."""
        # Create a transaction
        create_resp = client.post(
            "/transactions",
            json={
                "date": "2026-05-15",
                "amount": -50.0,
                "merchant_clean": "Another Store",
                "category": "Food",
                "subcategory": "Restaurant",
                "owner": "Maria",
                "type": "shared",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 200
        tx_id = create_resp.json()["id"]

        # Set month_ref to NULL to simulate a transaction without explicit month assignment
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE transactions_gold SET month_ref = NULL WHERE id = ?",
            (tx_id,),
        )
        conn.commit()
        conn.close()

        # Now edit the date — month_ref should be derived from new date
        update_resp = client.put(
            f"/transactions/{tx_id}",
            json={"date": "2026-06-20"},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200

        # Verify month_ref was derived from new date
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT month_ref, date FROM transactions_gold WHERE id = ?", (tx_id,))
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row["month_ref"] == "2026-06", f"month_ref should be derived as '2026-06', got '{row['month_ref']}'"
        assert row["date"] == "2026-06-20", f"date should be updated to '2026-06-20', got '{row['date']}'"

    def test_date_edit_without_month_ref_change_still_updates_date(self, client: TestClient, auth_headers):
        """Editing the date should always update the date field, regardless of month_ref behavior."""
        # Create a transaction
        create_resp = client.post(
            "/transactions",
            json={
                "date": "2026-07-01",
                "amount": -75.0,
                "merchant_clean": "Store C",
                "category": "Transport",
                "subcategory": "Fuel",
                "owner": "Victor",
                "type": "individual",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 200
        tx_id = create_resp.json()["id"]

        # Edit the date
        update_resp = client.put(
            f"/transactions/{tx_id}",
            json={"date": "2026-07-15"},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200

        # Verify date was updated
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT date, month_ref FROM transactions_gold WHERE id = ?", (tx_id,))
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row["date"] == "2026-07-15", f"date should be '2026-07-15', got '{row['date']}'"
