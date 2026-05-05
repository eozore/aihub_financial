"""
Unified classification service.

Consolidates all classification logic into a single module:
- Merchant normalization (from normalization.py / merchant_map.json)
- Category mapping (from category_mapping.py / category_map.json)
- Type inference (placeholder — will be replaced by card_type lookup in categories.py)

Usage:
    from classification_service import ClassificationService
    svc = ClassificationService()
    result = svc.classify("Uber *Trip", amount=25.0, owner="user@example.com")
    # -> {"category": "Uber/Onibus", "type": None, "merchant_norm": "Uber"}
"""
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from normalization import normalize_merchant
from category_mapping import load_category_map, get_category

logger = logging.getLogger("finance-pilot")

DB_PATH = Path(__file__).parent / "finance.db"

# ─── Category keywords (single source of truth) ───
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Bar/Restaurante": [
        "potencia", "restaurante", "bar ", "barbearia", "churras", "grill",
        "pizza", "sushi", "hamburgu", "lanchonete", "cafe ", "padaria",
        "cerveja", "chopp", "pub", "boteco", "camelo", "esquina", "camarada",
        "pantucci", "papila", "bullguer", "cacilda", "fukuya", "nagairo",
        "ilhabela", "prainha", "arena resenha",
    ],
    "Delivery": ["ifood", "rappi", "uber eats", "delivery", "ifd*"],
    "Mercado": [
        "mercado", "supermercado", "atacadao", "carrefour", "extra",
        "pao de acucar", "assai", "hortifruti", "verduras", "bp xpress",
        "chocolandia", "eskinao",
    ],
    "Uber/Onibus": ["uber", "99", "cabify", "taxi", "onibus", "metro", "bilhete unico"],
    "Combustivel": [
        "posto", "shell", "br ", "ipiranga", "gasolina", "combustivel",
        "piloto auto", "petro", "vaca preta",
    ],
    "Pedagio": ["pedagio", "nutag", "sem parar", "conectcar", "veloe"],
    "Aluguel": ["aluguel", "imobiliaria"],
    "Condominio": ["condominio", "taxa condominial"],
}
CATEGORY_KEYWORDS.update({
    "Luz/Internet": ["luz", "energia", "enel", "cpfl", "internet", "net ", "claro", "vivo", "tim"],
    "Streaming": [
        "netflix", "spotify", "amazon prime", "disney", "hbo",
        "apple.com/bill", "apple tv", "youtube premium", "amazonprimebr", "prime canais",
    ],
    "Saúde/Estética": [
        "farmacia", "drogaria", "medico", "hospital", "clinica", "dentista",
        "totalpass", "academia", "gympass", "salao", "cabelo", "barbeiro",
        "gio barbeiro", "vila pompeia", "breakfit",
    ],
    "Vestuário": ["roupa", "loja", "shopping", "vestuario", "sapato", "tenis"],
    "Curso": ["curso", "escola", "faculdade", "udemy", "coursera", "alura", "treinamento", "sete treinamentos", "linkedin"],
    "Projeto Pessoal": ["chatgpt", "openai", "aws", "google cloud", "cloud", "github", "canva", "figma", "notion", "digital ocean", "sixhq", "colab"],
    "Airbnb/Hotel": ["airbnb", "hotel", "pousada", "booking", "expedia", "ibis"],
    "Voos": ["azul", "latam", "gol ", "voo", "passagem aerea", "aeroporto"],
    "ItensdeCasa": ["shopee", "mercado livre", "amazon", "casa", "decoracao", "moveis"],
    "Faxina": ["faxina", "diarista", "limpeza"],
    "Presentes": ["presente", "gift", "flor", "joalheria"],
    "Manutenção/Revisão": ["mecanico", "oficina", "revisao", "pneu", "lavajato", "rodamalu"],
    "Luana": ["luana"],
})


class ClassificationService:
    """Single entry-point for all transaction classification.

    NOTE: Type inference (Individual/Shared) is now determined by the
    card_type of registered cards (see categories.py, task 7).  The
    _infer_type() method returns None as a placeholder until that module
    is integrated.
    """

    def __init__(self):
        self._category_map = load_category_map()

    # ── public API ──

    def classify(
        self,
        description: str,
        amount: float = 0.0,
        owner: str = "",
        existing_category: Optional[str] = None,
    ) -> dict:
        """Return {"category": ..., "type": ..., "merchant_norm": ...}."""
        merchant_norm = normalize_merchant(description)

        # 1. Category
        category = existing_category
        if not category or category in ("Outro", "Outros"):
            category = get_category(merchant_norm, self._category_map)
        if not category or category in ("Outro", "Outros"):
            category = self._category_from_keywords(description)

        # 2. Type — placeholder; will be determined by card_type from
        #    registered cards once categories.py is integrated (task 7).
        tx_type = self._infer_type(description, amount, owner, category)

        return {
            "category": category,
            "type": tx_type,
            "merchant_norm": merchant_norm,
        }

    # ── internals ──

    def _category_from_keywords(self, description: str) -> str:
        desc_lower = description.strip().lower()
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in desc_lower:
                    return cat
        return "Outro"

    def _infer_type(
        self,
        description: str,
        amount: float,
        owner: str,
        category: str,
    ) -> Optional[str]:
        """Placeholder for type inference.

        Type (Individual/Shared) will be determined by the card_type of
        registered cards once the new categories.py module is integrated
        (task 7).  For now, return None so callers know the type has not
        been resolved yet.
        """
        return None

    @staticmethod
    def _get_history_stats(merchant_clean: str) -> tuple[float, int]:
        try:
            if not DB_PATH.exists():
                return 0.0, 0
            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            c.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN type = 'Shared' THEN 1 ELSE 0 END) AS shared_count
                FROM transactions_gold
                WHERE merchant_clean = ? COLLATE NOCASE
                """,
                (merchant_clean.strip(),),
            )
            row = c.fetchone()
            conn.close()
            if not row or row[0] == 0:
                return 0.0, 0
            return (row[1] or 0) / row[0], row[0]
        except Exception:
            return 0.0, 0
