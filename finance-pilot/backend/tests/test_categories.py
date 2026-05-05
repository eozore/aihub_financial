"""Tests for the categories module.

Covers:
- DEFAULT_CATEGORIES structure (16 categories)
- ClassificationService 3-priority chain
- Workspace rule CRUD (create, list, update, delete)
- Case-insensitive partial keyword matching
- Fallback to "Outros" with needs_review=True

Requirements: 4.1, 4.2, 4.3, 4.6
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Patch database.DB_PATH before importing categories so all DB operations
# use the temporary test database.
import database

_tmp_dir = tempfile.mkdtemp()
_test_db_path = Path(_tmp_dir) / "test_categories.db"
database.DB_PATH = _test_db_path


from categories import (
    DEFAULT_CATEGORIES,
    ClassificationResult,
    ClassificationService,
    create_rule,
    delete_rule,
    list_rules,
    update_rule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _setup_db():
    """Create a fresh test database with the workspace_category_rules table."""
    database.DB_PATH = _test_db_path
    conn = sqlite3.connect(str(_test_db_path))
    conn.execute("DROP TABLE IF EXISTS workspace_category_rules")
    conn.execute(
        """
        CREATE TABLE workspace_category_rules (
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
    conn.commit()
    conn.close()
    yield
    # Cleanup
    if _test_db_path.exists():
        os.remove(str(_test_db_path))


# ---------------------------------------------------------------------------
# DEFAULT_CATEGORIES tests
# ---------------------------------------------------------------------------

class TestDefaultCategories:
    def test_has_16_categories(self):
        assert len(DEFAULT_CATEGORIES) == 16

    def test_expected_category_names(self):
        expected = {
            "Alimentação", "Delivery", "Mercado", "Transporte", "Moradia",
            "Saúde", "Educação", "Lazer", "Streaming", "Compras",
            "Assinaturas", "Viagem", "Pets", "Impostos/Taxas",
            "Transferência", "Outros",
        }
        assert set(DEFAULT_CATEGORIES.keys()) == expected

    def test_outros_has_empty_keywords(self):
        assert DEFAULT_CATEGORIES["Outros"] == []

    def test_all_values_are_lists(self):
        for cat, keywords in DEFAULT_CATEGORIES.items():
            assert isinstance(keywords, list), f"{cat} keywords should be a list"

    def test_all_keywords_are_strings(self):
        for cat, keywords in DEFAULT_CATEGORIES.items():
            for kw in keywords:
                assert isinstance(kw, str), f"Keyword in {cat} should be a string"


# ---------------------------------------------------------------------------
# ClassificationResult tests
# ---------------------------------------------------------------------------

class TestClassificationResult:
    def test_creation(self):
        result = ClassificationResult(category="Mercado", needs_review=False)
        assert result.category == "Mercado"
        assert result.needs_review is False

    def test_fallback_result(self):
        result = ClassificationResult(category="Outros", needs_review=True)
        assert result.category == "Outros"
        assert result.needs_review is True


# ---------------------------------------------------------------------------
# ClassificationService — keyword matching
# ---------------------------------------------------------------------------

class TestKeywordMatching:
    def setup_method(self):
        self.svc = ClassificationService()

    def test_exact_keyword_match(self):
        result = self.svc.classify("netflix", workspace_id="ws-1")
        assert result.category == "Streaming"
        assert result.needs_review is False

    def test_partial_keyword_match(self):
        result = self.svc.classify("Supermercado Extra", workspace_id="ws-1")
        assert result.category == "Mercado"
        assert result.needs_review is False

    def test_case_insensitive_match(self):
        result = self.svc.classify("NETFLIX", workspace_id="ws-1")
        assert result.category == "Streaming"
        assert result.needs_review is False

    def test_mixed_case_match(self):
        result = self.svc.classify("IFood Delivery", workspace_id="ws-1")
        assert result.category == "Delivery"
        assert result.needs_review is False

    def test_fallback_to_outros(self):
        result = self.svc.classify("xyzunknownmerchant123", workspace_id="ws-1")
        assert result.category == "Outros"
        assert result.needs_review is True

    def test_empty_merchant_fallback(self):
        result = self.svc.classify("", workspace_id="ws-1")
        assert result.category == "Outros"
        assert result.needs_review is True

    def test_whitespace_only_fallback(self):
        result = self.svc.classify("   ", workspace_id="ws-1")
        assert result.category == "Outros"
        assert result.needs_review is True

    def test_alimentacao_keywords(self):
        for merchant in ["Restaurante Bom Sabor", "Padaria Central", "Sushi House"]:
            result = self.svc.classify(merchant, workspace_id="ws-1")
            assert result.category == "Alimentação", f"Failed for {merchant}"

    def test_transporte_keywords(self):
        for merchant in ["Uber Trip", "Posto Shell", "Estacionamento Centro"]:
            result = self.svc.classify(merchant, workspace_id="ws-1")
            assert result.category == "Transporte", f"Failed for {merchant}"

    def test_moradia_keywords(self):
        for merchant in ["Aluguel Apto", "Condominio Res", "Energia Enel"]:
            result = self.svc.classify(merchant, workspace_id="ws-1")
            assert result.category == "Moradia", f"Failed for {merchant}"

    def test_compras_keywords(self):
        result = self.svc.classify("Shopee Brasil", workspace_id="ws-1")
        assert result.category == "Compras"

    def test_viagem_keywords(self):
        result = self.svc.classify("Airbnb Reserva", workspace_id="ws-1")
        assert result.category == "Viagem"

    def test_pets_keywords(self):
        result = self.svc.classify("Petlove Compra", workspace_id="ws-1")
        assert result.category == "Pets"

    def test_impostos_keywords(self):
        result = self.svc.classify("IOF Compra Internacional", workspace_id="ws-1")
        assert result.category == "Impostos/Taxas"

    def test_transferencia_keywords(self):
        result = self.svc.classify("PIX Enviado", workspace_id="ws-1")
        assert result.category == "Transferência"


# ---------------------------------------------------------------------------
# ClassificationService — workspace rule priority
# ---------------------------------------------------------------------------

class TestWorkspaceRulePriority:
    def setup_method(self):
        self.svc = ClassificationService()

    def test_workspace_rule_overrides_keyword(self):
        # "netflix" would match Streaming by keyword, but workspace rule
        # should take priority.
        create_rule("ws-1", "netflix", "Lazer Pessoal")
        result = self.svc.classify("netflix", workspace_id="ws-1")
        assert result.category == "Lazer Pessoal"
        assert result.needs_review is False

    def test_workspace_rule_case_insensitive(self):
        create_rule("ws-1", "My Custom Merchant", "Custom Category")
        result = self.svc.classify("my custom merchant", workspace_id="ws-1")
        assert result.category == "Custom Category"
        assert result.needs_review is False

    def test_workspace_rule_does_not_affect_other_workspace(self):
        create_rule("ws-1", "netflix", "Lazer Pessoal")
        # ws-2 should still get the keyword match
        result = self.svc.classify("netflix", workspace_id="ws-2")
        assert result.category == "Streaming"

    def test_no_rule_falls_through_to_keywords(self):
        result = self.svc.classify("spotify", workspace_id="ws-1")
        assert result.category == "Streaming"
        assert result.needs_review is False

    def test_no_rule_no_keyword_falls_to_outros(self):
        result = self.svc.classify("totally unknown", workspace_id="ws-1")
        assert result.category == "Outros"
        assert result.needs_review is True


# ---------------------------------------------------------------------------
# CRUD — create_rule
# ---------------------------------------------------------------------------

class TestCreateRule:
    def test_create_rule_returns_dict(self):
        rule = create_rule("ws-1", "starbucks", "Alimentação")
        assert isinstance(rule, dict)
        assert rule["workspace_id"] == "ws-1"
        assert rule["merchant_pattern"] == "starbucks"
        assert rule["category"] == "Alimentação"
        assert rule["id"].startswith("rule-")

    def test_create_rule_with_created_by(self):
        rule = create_rule("ws-1", "starbucks", "Alimentação", created_by="user@test.com")
        assert rule["created_by"] == "user@test.com"

    def test_create_duplicate_raises(self):
        create_rule("ws-1", "starbucks", "Alimentação")
        with pytest.raises(ValueError, match="already exists"):
            create_rule("ws-1", "starbucks", "Delivery")

    def test_same_pattern_different_workspace_ok(self):
        rule1 = create_rule("ws-1", "starbucks", "Alimentação")
        rule2 = create_rule("ws-2", "starbucks", "Delivery")
        assert rule1["workspace_id"] == "ws-1"
        assert rule2["workspace_id"] == "ws-2"


# ---------------------------------------------------------------------------
# CRUD — list_rules
# ---------------------------------------------------------------------------

class TestListRules:
    def test_list_empty(self):
        rules = list_rules("ws-1")
        assert rules == []

    def test_list_returns_only_workspace_rules(self):
        create_rule("ws-1", "starbucks", "Alimentação")
        create_rule("ws-1", "uber", "Transporte")
        create_rule("ws-2", "netflix", "Streaming")

        rules = list_rules("ws-1")
        assert len(rules) == 2
        patterns = {r["merchant_pattern"] for r in rules}
        assert patterns == {"starbucks", "uber"}

    def test_list_ordered_by_created_at(self):
        create_rule("ws-1", "aaa", "Cat1")
        create_rule("ws-1", "bbb", "Cat2")
        rules = list_rules("ws-1")
        assert rules[0]["merchant_pattern"] == "aaa"
        assert rules[1]["merchant_pattern"] == "bbb"


# ---------------------------------------------------------------------------
# CRUD — update_rule
# ---------------------------------------------------------------------------

class TestUpdateRule:
    def test_update_category(self):
        rule = create_rule("ws-1", "starbucks", "Alimentação")
        updated = update_rule("ws-1", rule["id"], category="Delivery")
        assert updated["category"] == "Delivery"
        assert updated["merchant_pattern"] == "starbucks"

    def test_update_merchant_pattern(self):
        rule = create_rule("ws-1", "starbucks", "Alimentação")
        updated = update_rule("ws-1", rule["id"], merchant_pattern="starbucks coffee")
        assert updated["merchant_pattern"] == "starbucks coffee"

    def test_update_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            update_rule("ws-1", "nonexistent-id", category="X")

    def test_update_wrong_workspace_raises(self):
        rule = create_rule("ws-1", "starbucks", "Alimentação")
        with pytest.raises(ValueError, match="not found"):
            update_rule("ws-2", rule["id"], category="X")

    def test_update_pattern_to_existing_raises(self):
        create_rule("ws-1", "starbucks", "Alimentação")
        rule2 = create_rule("ws-1", "uber", "Transporte")
        with pytest.raises(ValueError, match="already exists"):
            update_rule("ws-1", rule2["id"], merchant_pattern="starbucks")


# ---------------------------------------------------------------------------
# CRUD — delete_rule
# ---------------------------------------------------------------------------

class TestDeleteRule:
    def test_delete_rule(self):
        rule = create_rule("ws-1", "starbucks", "Alimentação")
        delete_rule("ws-1", rule["id"])
        rules = list_rules("ws-1")
        assert len(rules) == 0

    def test_delete_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            delete_rule("ws-1", "nonexistent-id")

    def test_delete_wrong_workspace_raises(self):
        rule = create_rule("ws-1", "starbucks", "Alimentação")
        with pytest.raises(ValueError, match="not found"):
            delete_rule("ws-2", rule["id"])

    def test_delete_does_not_affect_other_rules(self):
        rule1 = create_rule("ws-1", "starbucks", "Alimentação")
        create_rule("ws-1", "uber", "Transporte")
        delete_rule("ws-1", rule1["id"])
        rules = list_rules("ws-1")
        assert len(rules) == 1
        assert rules[0]["merchant_pattern"] == "uber"
