"""
Migration 003 — Create raw_statements table.

Stores the free-form JSON returned by Gemini Stage 1 extraction so that
the raw data is preserved for debugging, re-processing, and future analysis.

All CREATE statements are idempotent (IF NOT EXISTS).
Rollback drops the table and its indexes.

Requirements: 2-stage PDF extraction architecture.
"""

import sqlite3
import logging

logger = logging.getLogger("finance-pilot.migrations")


def apply(conn: sqlite3.Connection) -> None:
    """Create the raw_statements table and its indexes."""
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_statements (
            id TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL UNIQUE,
            workspace_id TEXT NOT NULL,
            filename TEXT,
            model_used TEXT,
            raw_json TEXT NOT NULL,
            statement_type TEXT,
            bank TEXT,
            holder_name TEXT,
            invoice_total REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    logger.info("Created table raw_statements (IF NOT EXISTS)")

    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_raw_statements_workspace "
        "ON raw_statements(workspace_id)"
    )
    logger.info("Created index idx_raw_statements_workspace (IF NOT EXISTS)")

    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_raw_statements_file_hash "
        "ON raw_statements(file_hash)"
    )
    logger.info("Created index idx_raw_statements_file_hash (IF NOT EXISTS)")


def rollback(conn: sqlite3.Connection) -> None:
    """Drop the raw_statements table (indexes are dropped automatically)."""
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS raw_statements")
    logger.info("Dropped table raw_statements")
