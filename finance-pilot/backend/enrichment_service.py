"""Enrichment Service for transaction data.

This module provides stateless enrichment logic that transforms raw transaction
records with card metadata and computed month_ref values at query time.
The service is a pure function — no database access inside the service itself.
"""

from dataclasses import dataclass


@dataclass
class CardInfo:
    owner: str
    card_type: str  # "individual" or "shared"


class EnrichmentService:
    def compute_month_ref(self, transaction: dict) -> str:
        """Compute month_ref for a single transaction.

        If transaction already has a non-empty month_ref, return it as-is.
        Otherwise, derive YYYY-MM from the transaction's date field.
        """
        existing = transaction.get("month_ref")
        if existing and str(existing).strip():
            return str(existing)
        date_str = transaction.get("date", "")
        if date_str and len(date_str) >= 7:
            return date_str[:7]  # YYYY-MM
        return ""

    def enrich_card_data(self, transaction: dict, card_map: dict[str, CardInfo]) -> dict:
        """Apply card enrichment to a single transaction.

        If card_last4 matches a registered card, enrich owner/type only when
        the stored value is NULL or empty (preserving user edits).
        card_type is always enriched unconditionally (metadata field).
        """
        result = dict(transaction)  # shallow copy
        card_last4 = result.get("card_last4")
        if card_last4 and card_last4 in card_map:
            card_info = card_map[card_last4]
            if not result.get("owner"):
                result["owner"] = card_info.owner
            if not result.get("type"):
                result["type"] = card_info.card_type
            result["card_type"] = card_info.card_type
        return result

    def enrich_transactions(self, transactions: list[dict], card_map: dict[str, CardInfo]) -> list[dict]:
        """Enrich a list of raw transaction dicts with card data and month_ref.

        Applies both compute_month_ref and enrich_card_data to each transaction.
        """
        enriched = []
        for tx in transactions:
            enriched_tx = self.enrich_card_data(tx, card_map)
            enriched_tx["month_ref"] = self.compute_month_ref(enriched_tx)
            enriched.append(enriched_tx)
        return enriched
