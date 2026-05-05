"""Generic SaaS category system with workspace-level overrides.

Provides:
- ``DEFAULT_CATEGORIES``: 16 standard categories with associated keywords
- ``ClassificationResult``: dataclass returned by the classification service
- ``ClassificationService``: 3-priority classification (workspace rule → keywords → fallback)
- CRUD functions for ``workspace_category_rules`` table

Requirements: 4.1, 4.2, 4.3, 4.6
"""

import uuid
from dataclasses import dataclass
from typing import List, Optional

from database import get_db_connection
from helpers import utc_now_iso


# ---------------------------------------------------------------------------
# Default categories — 16 generic SaaS categories
# ---------------------------------------------------------------------------

DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Alimentação": ["restaurante", "bar", "padaria", "lanchonete", "pizza", "sushi"],
    "Delivery": ["ifood", "rappi", "uber eats", "ifd*"],
    "Mercado": ["mercado", "supermercado", "hortifruti", "carrefour"],
    "Transporte": ["uber", "99", "combustivel", "posto", "estacionamento", "pedagio"],
    "Moradia": ["aluguel", "condominio", "luz", "energia", "agua", "internet"],
    "Saúde": ["farmacia", "drogaria", "medico", "academia", "totalpass"],
    "Educação": ["curso", "escola", "udemy", "alura", "linkedin"],
    "Lazer": ["cinema", "show", "ingresso", "parque"],
    "Streaming": ["netflix", "spotify", "disney", "hbo", "amazon prime", "youtube premium"],
    "Compras": ["shopee", "mercado livre", "amazon", "magazine"],
    "Assinaturas": ["google one", "icloud", "canva", "chatgpt", "github"],
    "Viagem": ["airbnb", "hotel", "pousada", "booking", "azul", "latam"],
    "Pets": ["petlove", "petshop", "veterinario"],
    "Impostos/Taxas": ["iof", "anuidade", "taxa"],
    "Transferência": ["pix", "ted", "transferencia"],
    "Outros": [],
}


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """Result of the classification pipeline."""

    category: str
    needs_review: bool


# ---------------------------------------------------------------------------
# Classification service
# ---------------------------------------------------------------------------

class ClassificationService:
    """Classify merchants using a 3-level priority chain.

    Priority:
        1. Workspace rule — exact match on ``merchant_clean`` in
           ``workspace_category_rules``.
        2. Generic keywords — partial, case-insensitive match against
           ``DEFAULT_CATEGORIES``.
        3. Fallback — returns ``"Outros"`` with ``needs_review=True``.
    """

    def classify(self, merchant_clean: str, workspace_id: str) -> ClassificationResult:
        """Classify *merchant_clean* within the context of *workspace_id*."""
        # 1. Workspace rule (exact match by merchant_clean)
        rule = self._get_workspace_rule(workspace_id, merchant_clean)
        if rule:
            return ClassificationResult(category=rule["category"], needs_review=False)

        # 2. Generic keywords (partial match)
        category = self._match_default_keywords(merchant_clean)
        if category and category != "Outros":
            return ClassificationResult(category=category, needs_review=False)

        # 3. Fallback
        return ClassificationResult(category="Outros", needs_review=True)

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _get_workspace_rule(workspace_id: str, merchant_clean: str) -> Optional[dict]:
        """Query ``workspace_category_rules`` for an exact match.

        Returns a dict with at least a ``category`` key, or ``None``.
        """
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT category
                FROM workspace_category_rules
                WHERE workspace_id = ?
                  AND merchant_pattern = ? COLLATE NOCASE
                """,
                (workspace_id, merchant_clean),
            )
            row = c.fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    @staticmethod
    def _match_default_keywords(merchant_clean: str) -> Optional[str]:
        """Return the first category whose keyword is a substring of
        *merchant_clean* (case-insensitive).  Returns ``None`` when no
        keyword matches.
        """
        desc_lower = merchant_clean.strip().lower()
        if not desc_lower:
            return None
        for category, keywords in DEFAULT_CATEGORIES.items():
            for kw in keywords:
                if kw.lower() in desc_lower:
                    return category
        return None


# ---------------------------------------------------------------------------
# CRUD for workspace_category_rules
# ---------------------------------------------------------------------------

def create_rule(
    workspace_id: str,
    merchant_pattern: str,
    category: str,
    created_by: Optional[str] = None,
) -> dict:
    """Create a new workspace category rule.

    Returns the created rule as a dict.

    Raises ``ValueError`` if a rule with the same ``merchant_pattern``
    already exists in the workspace.
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()

        # Check uniqueness
        c.execute(
            "SELECT id FROM workspace_category_rules WHERE workspace_id = ? AND merchant_pattern = ?",
            (workspace_id, merchant_pattern),
        )
        if c.fetchone() is not None:
            raise ValueError(
                f"Rule for merchant_pattern '{merchant_pattern}' already exists in this workspace"
            )

        now = utc_now_iso()
        rule_id = f"rule-{uuid.uuid4().hex[:16]}"

        c.execute(
            """
            INSERT INTO workspace_category_rules
                (id, workspace_id, merchant_pattern, category, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (rule_id, workspace_id, merchant_pattern, category, created_by, now),
        )
        conn.commit()

        c.execute("SELECT * FROM workspace_category_rules WHERE id = ?", (rule_id,))
        return dict(c.fetchone())
    finally:
        conn.close()


def list_rules(workspace_id: str) -> List[dict]:
    """Return all category rules for *workspace_id*."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM workspace_category_rules WHERE workspace_id = ? ORDER BY created_at ASC",
            (workspace_id,),
        )
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


def update_rule(
    workspace_id: str,
    rule_id: str,
    merchant_pattern: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """Update an existing workspace category rule.

    Returns the updated rule as a dict.

    Raises ``ValueError`` if the rule is not found or belongs to another
    workspace.
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM workspace_category_rules WHERE id = ?", (rule_id,))
        row = c.fetchone()

        if row is None:
            raise ValueError("Rule not found")

        existing = dict(row)
        if existing["workspace_id"] != workspace_id:
            raise ValueError("Rule not found")

        new_pattern = merchant_pattern if merchant_pattern is not None else existing["merchant_pattern"]
        new_category = category if category is not None else existing["category"]

        # If merchant_pattern changed, check uniqueness
        if new_pattern != existing["merchant_pattern"]:
            c.execute(
                "SELECT id FROM workspace_category_rules WHERE workspace_id = ? AND merchant_pattern = ? AND id != ?",
                (workspace_id, new_pattern, rule_id),
            )
            if c.fetchone() is not None:
                raise ValueError(
                    f"Rule for merchant_pattern '{new_pattern}' already exists in this workspace"
                )

        c.execute(
            """
            UPDATE workspace_category_rules
            SET merchant_pattern = ?, category = ?
            WHERE id = ? AND workspace_id = ?
            """,
            (new_pattern, new_category, rule_id, workspace_id),
        )
        conn.commit()

        c.execute("SELECT * FROM workspace_category_rules WHERE id = ?", (rule_id,))
        return dict(c.fetchone())
    finally:
        conn.close()


def delete_rule(workspace_id: str, rule_id: str) -> None:
    """Delete a workspace category rule.

    Raises ``ValueError`` if the rule is not found or belongs to another
    workspace.
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM workspace_category_rules WHERE id = ?", (rule_id,))
        row = c.fetchone()

        if row is None:
            raise ValueError("Rule not found")

        if dict(row)["workspace_id"] != workspace_id:
            raise ValueError("Rule not found")

        c.execute(
            "DELETE FROM workspace_category_rules WHERE id = ? AND workspace_id = ?",
            (rule_id, workspace_id),
        )
        conn.commit()
    finally:
        conn.close()
