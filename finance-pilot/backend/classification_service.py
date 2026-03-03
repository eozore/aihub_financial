"""
Unified classification service.

Consolidates all classification logic into a single module:
- Merchant normalization (from normalization.py / merchant_map.json)
- Category mapping (from category_mapping.py / category_map.json)
- Type inference (from classifier.py keyword rules + history)
- ML model predictions (from type_model.py)

Usage:
    from classification_service import ClassificationService
    svc = ClassificationService()
    result = svc.classify("Uber *Trip", amount=25.0, owner="Victor")
    # -> {"category": "Uber/Onibus", "type": "Shared", "merchant_norm": "Uber"}
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

# ─── Type inference rules ───
ALWAYS_SHARED_CATEGORIES = [
    "Aluguel", "Condominio", "Luz/Internet", "Faxina",
    "Streaming", "Mercado", "ItensdeCasa", "Manutenção/Revisão",
]
ALWAYS_INDIVIDUAL_CATEGORIES = [
    "Projeto Pessoal", "Vestuário", "Curso", "Luana", "Saúde/Estética",
]
FORCE_SHARED_MERCHANTS = [
    "nutag", "pedagio", "sem parar", "veloe", "conectcar",
    "canva", "apple.com/bill",
]
SHARED_KEYWORDS = [
    "aluguel", "condominio", "luz", "internet", "mercado", "supermercado",
    "ifood", "delivery", "netflix", "amazon prime", "spotify",
    "combustivel", "posto", "pedagio", "nutag", "uber",
    "restaurante", "airbnb", "hotel", "voo", "passagem",
]
VICTOR_INDIVIDUAL_KEYWORDS = [
    "barbeiro", "barbearia", "cerveja artesanal", "futebol", "joga10",
    "arena resenha", "gio barbeiro", "vila pompeia", "totalpass",
    "linkedin", "chatgpt", "openai", "github", "digital ocean",
]


class ClassificationService:
    """Single entry-point for all transaction classification."""

    def __init__(self):
        self._category_map = load_category_map()

    # ── public API ──

    def classify(
        self,
        description: str,
        amount: float = 0.0,
        owner: str = "Victor",
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

        # 2. Type
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
    ) -> str:
        desc_lower = description.strip().lower()

        # Rule 1: Force-shared merchants
        for kw in FORCE_SHARED_MERCHANTS:
            if kw.lower() in desc_lower:
                return "Shared"

        # Rule 2: Always-shared categories
        if category in ALWAYS_SHARED_CATEGORIES:
            return "Shared"

        # Rule 3: Always-individual categories
        if category in ALWAYS_INDIVIDUAL_CATEGORIES:
            return "Individual"

        # Rule 4: History lookup
        shared_ratio, total = self._get_history_stats(description)
        if total > 0:
            if shared_ratio > 0.6:
                return "Shared"
            if amount > 80 and shared_ratio > 0.3:
                return "Shared"
            return "Individual"

        # Rule 5: Keyword fallback
        # Non-primary owners default to simpler keyword matching
        if owner.strip().lower() not in ("victor",):
            return "Shared" if any(k in desc_lower for k in SHARED_KEYWORDS) else "Individual"

        if any(k in desc_lower for k in VICTOR_INDIVIDUAL_KEYWORDS):
            return "Individual"
        if any(k in desc_lower for k in SHARED_KEYWORDS) and amount > 50:
            return "Shared"

        return "Individual"

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
