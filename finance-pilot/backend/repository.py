"""
Repository pattern — abstracts database access for transactions.

Provides a unified interface regardless of backend (SQLite, Firestore+BigQuery, Mock).
This eliminates the if/else branching scattered throughout main.py.

Usage:
    from repository import get_repository
    repo = get_repository()
    transactions = repo.list_transactions(tenant_id, start, end)
"""
import datetime
import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("finance-pilot")


class TransactionRepository(ABC):
    """Abstract base for transaction data access."""

    @abstractmethod
    def list_transactions(
        self, tenant_id: str, start: str, end: str,
        owner: Optional[str] = None, tx_type: Optional[str] = None,
        limit: int = 200, offset: int = 0,
    ) -> dict:
        """Returns {"data": [...], "total": int, "limit": int, "offset": int}."""

    @abstractmethod
    def get_transaction(self, tenant_id: str, transaction_id: str) -> Optional[dict]:
        ...

    @abstractmethod
    def create_transaction(self, tenant_id: str, tx_data: dict) -> dict:
        ...

    @abstractmethod
    def update_transaction(self, tenant_id: str, transaction_id: str, updates: dict) -> dict:
        ...

    @abstractmethod
    def delete_transaction(self, tenant_id: str, transaction_id: str) -> bool:
        ...


class SQLiteTransactionRepository(TransactionRepository):
    """SQLite implementation of the transaction repository."""

    def __init__(self, db_path: Path):
        self._db_path = db_path

    def _conn(self):
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def list_transactions(
        self, tenant_id: str, start: str, end: str,
        owner: Optional[str] = None, tx_type: Optional[str] = None,
        limit: int = 200, offset: int = 0,
    ) -> dict:
        conn = self._conn()
        c = conn.cursor()

        where = "tenant_id = ? AND month_ref >= ? AND month_ref <= ?"
        params: list[Any] = [tenant_id, start, end]
        if owner:
            where += " AND owner = ?"
            params.append(owner)
        if tx_type:
            where += " AND type = ?"
            params.append(tx_type)

        c.execute(f"SELECT COUNT(*) FROM transactions_gold WHERE {where}", params)
        total = c.fetchone()[0]

        c.execute(
            f"SELECT * FROM transactions_gold WHERE {where} ORDER BY date DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return {"data": rows, "total": total, "limit": limit, "offset": offset}

    def get_transaction(self, tenant_id: str, transaction_id: str) -> Optional[dict]:
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM transactions_gold WHERE id = ? AND tenant_id = ?",
            (transaction_id, tenant_id),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_transaction(self, tenant_id: str, tx_data: dict) -> dict:
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO transactions_gold
            (id, tenant_id, date, month_ref, amount, merchant_clean, category, subcategory, owner, type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx_data["id"], tenant_id, tx_data["date"], tx_data.get("month_ref"),
                tx_data["amount"], tx_data["merchant_clean"], tx_data.get("category"),
                tx_data.get("subcategory"), tx_data["owner"], tx_data["type"],
                tx_data.get("created_at", datetime.datetime.now().isoformat()),
            ),
        )
        conn.commit()
        conn.close()
        return {"status": "created", "id": tx_data["id"]}

    def update_transaction(self, tenant_id: str, transaction_id: str, updates: dict) -> dict:
        existing = self.get_transaction(tenant_id, transaction_id)
        if not existing:
            return {"error": "not_found"}

        set_clauses = []
        params: list[Any] = []
        for key, value in updates.items():
            if value is not None:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        if not set_clauses:
            return {"status": "no changes"}

        params.extend([transaction_id, tenant_id])
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            f"UPDATE transactions_gold SET {', '.join(set_clauses)} WHERE id = ? AND tenant_id = ?",
            params,
        )
        conn.commit()
        conn.close()
        return {"status": "updated", "id": transaction_id}

    def delete_transaction(self, tenant_id: str, transaction_id: str) -> bool:
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "DELETE FROM transactions_gold WHERE id = ? AND tenant_id = ?",
            (transaction_id, tenant_id),
        )
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0


class MockTransactionRepository(TransactionRepository):
    """Mock/JSON file implementation for development."""

    def __init__(self, mock_data_path: Path):
        self._path = mock_data_path

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def list_transactions(
        self, tenant_id: str, start: str, end: str,
        owner: Optional[str] = None, tx_type: Optional[str] = None,
        limit: int = 200, offset: int = 0,
    ) -> dict:
        data = self._load()
        filtered = [
            tx for tx in data
            if tx.get("tenant_id") == tenant_id
            and start <= tx.get("month_ref", "") <= end
        ]
        if owner:
            filtered = [tx for tx in filtered if tx.get("owner") == owner]
        if tx_type:
            filtered = [tx for tx in filtered if tx.get("type") == tx_type]

        total = len(filtered)
        page = filtered[offset : offset + limit]
        return {"data": page, "total": total, "limit": limit, "offset": offset}

    def get_transaction(self, tenant_id: str, transaction_id: str) -> Optional[dict]:
        data = self._load()
        for tx in data:
            if tx.get("id") == transaction_id and tx.get("tenant_id") == tenant_id:
                return tx
        return None

    def create_transaction(self, tenant_id: str, tx_data: dict) -> dict:
        return {"status": "created (mock)", "id": tx_data.get("id")}

    def update_transaction(self, tenant_id: str, transaction_id: str, updates: dict) -> dict:
        return {"status": "updated (mock)", "id": transaction_id}

    def delete_transaction(self, tenant_id: str, transaction_id: str) -> bool:
        return True
