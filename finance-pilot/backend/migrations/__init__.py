"""
Reversible database migrations for Finance Pilot SaaS evolution.

Each migration script exposes apply(conn) and rollback(conn) functions
that receive an open sqlite3.Connection and perform schema changes
within a single transaction managed by the migration runner.
"""
