"""
Migration 002 — Create SaaS tables.

Creates the four new tables required for the SaaS platform evolution:
  - cards: registered payment cards per workspace
  - workspace_category_rules: custom category rules per workspace
  - subscriptions: billing subscriptions via Mercado Pago
  - upload_history: record of file uploads and their processing status

All CREATE statements are idempotent (IF NOT EXISTS).
Rollback drops all four tables.

Requirements: 9.3, 9.4
"""

import sqlite3
import logging

logger = logging.getLogger("finance-pilot.migrations")


def apply(conn: sqlite3.Connection) -> None:
    """Create the four SaaS tables if they do not already exist."""
    c = conn.cursor()

    # --- cards ---
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            last4 TEXT NOT NULL CHECK(length(last4) = 4 AND last4 GLOB '[0-9][0-9][0-9][0-9]'),
            label TEXT,
            card_type TEXT NOT NULL CHECK(card_type IN ('individual', 'shared')),
            bank TEXT DEFAULT 'nubank',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id, last4)
        )
        """
    )
    logger.info("Created table cards (IF NOT EXISTS)")

    # --- workspace_category_rules ---
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_category_rules (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            merchant_pattern TEXT NOT NULL,
            category TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workspace_id, merchant_pattern)
        )
        """
    )
    logger.info("Created table workspace_category_rules (IF NOT EXISTS)")

    # --- subscriptions ---
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            mp_preapproval_id TEXT,
            plan_type TEXT NOT NULL DEFAULT 'free' CHECK(plan_type IN ('free', 'pro', 'familia')),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'paused', 'cancelled', 'pending')),
            trial_ends_at TIMESTAMP,
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    logger.info("Created table subscriptions (IF NOT EXISTS)")

    # --- upload_history ---
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_history (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            file_size_bytes INTEGER,
            statement_type TEXT CHECK(statement_type IN ('credit_card', 'current_account')),
            bank TEXT,
            period_start TEXT,
            period_end TEXT,
            transactions_count INTEGER,
            status TEXT NOT NULL CHECK(status IN ('processing', 'completed', 'failed', 'reverted')),
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    logger.info("Created table upload_history (IF NOT EXISTS)")


def rollback(conn: sqlite3.Connection) -> None:
    """Drop the four SaaS tables."""
    c = conn.cursor()

    for table in ("cards", "workspace_category_rules", "subscriptions", "upload_history"):
        c.execute(f"DROP TABLE IF EXISTS {table}")
        logger.info("Dropped table %s", table)
