"""
Migration 001 — Add SaaS columns to transactions_gold.

Adds columns required for the SaaS platform evolution:
  - card_last4: last 4 digits of the card used in the transaction
  - card_type: 'individual' or 'shared' (determined by registered cards)
  - is_refund: flag indicating refund/chargeback transactions
  - transaction_source: origin of the transaction ('legacy_csv', 'pdf_extraction', etc.)
  - upload_id: reference to the upload_history entry that created this transaction
  - needs_review: flag for transactions requiring manual review

Legacy data is backfilled with transaction_source='legacy_csv' and card_last4=NULL.

Rollback uses the backup-table approach because SQLite < 3.35.0 does not
support DROP COLUMN.

Requirements: 9.1, 9.2, 9.4
"""

import sqlite3
import logging

logger = logging.getLogger("finance-pilot.migrations")

# The original columns in transactions_gold (before this migration).
_ORIGINAL_COLUMNS = [
    "id",
    "tenant_id",
    "date",
    "month_ref",
    "amount",
    "merchant_clean",
    "category",
    "subcategory",
    "owner",
    "type",
    "created_at",
]


def apply(conn: sqlite3.Connection) -> None:
    """Add SaaS columns to transactions_gold and backfill legacy defaults."""
    c = conn.cursor()

    # Discover which columns already exist to make the migration idempotent.
    c.execute("PRAGMA table_info(transactions_gold)")
    existing_cols = {row[1] for row in c.fetchall()}

    new_columns = [
        ("card_last4", "TEXT"),
        ("card_type", "TEXT"),
        ("is_refund", "INTEGER DEFAULT 0"),
        ("transaction_source", "TEXT DEFAULT 'legacy_csv'"),
        ("upload_id", "TEXT"),
        ("needs_review", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in existing_cols:
            stmt = f"ALTER TABLE transactions_gold ADD COLUMN {col_name} {col_def}"
            c.execute(stmt)
            logger.info("Added column %s to transactions_gold", col_name)

    # Backfill defaults for existing (legacy) rows.
    c.execute(
        """
        UPDATE transactions_gold
        SET transaction_source = 'legacy_csv',
            card_last4 = NULL,
            needs_review = 0
        WHERE transaction_source IS NULL
        """
    )
    backfilled = c.rowcount
    logger.info("Backfilled %d legacy rows with default values", backfilled)


def rollback(conn: sqlite3.Connection) -> None:
    """Remove SaaS columns by rebuilding the table (SQLite compat)."""
    c = conn.cursor()

    cols_csv = ", ".join(_ORIGINAL_COLUMNS)

    # 1. Create backup with only the original columns.
    c.execute(
        f"CREATE TABLE transactions_gold_backup AS SELECT {cols_csv} FROM transactions_gold"
    )
    logger.info("Created transactions_gold_backup with original columns")

    # 2. Drop the current table.
    c.execute("DROP TABLE transactions_gold")
    logger.info("Dropped transactions_gold")

    # 3. Rename backup to the original name.
    c.execute("ALTER TABLE transactions_gold_backup RENAME TO transactions_gold")
    logger.info("Renamed transactions_gold_backup → transactions_gold")
