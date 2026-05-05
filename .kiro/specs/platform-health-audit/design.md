# Platform Health Audit — Bugfix Design

## Overview

A auditoria da plataforma finance-pilot revelou 15 defeitos distribuídos em 7 categorias: infraestrutura Terraform (nome de tabela inconsistente, buckets órfãos), código morto (5 arquivos sem uso), dependências desnecessárias, bugs de dados no processor (agregação destrutiva e merchant_clean ignorando normalização), duplicação massiva no main.py, queries de settlement contraditórias no dashboard, e credenciais expostas no frontend. A estratégia de correção é cirúrgica: cada defeito é corrigido isoladamente, preservando integralmente o `classification_service.py`, o fluxo de upload CSV, o dashboard, workspaces, patrimônio e o modo SQLite local.

## Glossary

- **Bug_Condition (C)**: Conjunto de condições que disparam cada defeito — desde nomes de tabela inconsistentes até queries SQL contraditórias
- **Property (P)**: Comportamento correto esperado após a correção de cada defeito
- **Preservation**: Comportamentos existentes que não devem ser alterados: classificação customizada, modo SQLite, autenticação Firebase, upload CSV, dashboard, workspaces, patrimônio, normalização de merchants e mapeamento de categorias
- **TransactionProcessor**: Classe em `processor.py` responsável por processar CSVs de fatura e inserir dados nas tabelas silver/gold
- **get_dashboard_summary()**: Endpoint em `main.py` que retorna resumo de gastos, categorias e settlement entre owners
- **TABLE_GOLD**: Variável em `processor.py` que referencia a tabela gold no BigQuery (`transactions_gold`)
- **classification_service.py**: Módulo ativo e único de classificação de transações (regras customizadas de categoria, tipo, merchant)
- **Settlement**: Cálculo de acerto de contas entre owners para transações do tipo "Shared"

## Bug Details

### Bug Condition

Os defeitos se manifestam em três domínios principais:

1. **Infraestrutura**: O Terraform cria a tabela como `finance_gold` mas o código referencia `transactions_gold`, causando falha em todas as operações BigQuery na tabela gold. Dois buckets GCS são provisionados sem uso.

2. **Dados (Processor)**: Transações individuais são destruídas por agregação groupby no `process_file()`, e o valor normalizado do merchant (`merchant_norm`) é computado mas descartado — `merchant_clean` recebe apenas `merchant_raw.strip()`.

3. **Lógica (Settlement)**: Quando `tx_type` é filtrado para "Individual", a query de settlement herda `type='Individual'` do `base_where` e adiciona `type='Shared'`, criando cláusula WHERE contraditória que sempre retorna 0 linhas.


**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type PlatformOperation
  OUTPUT: boolean

  // Bug 1.1: Table name mismatch
  IF input.operation == "bigquery_gold_access"
    RETURN terraform_table_id("gold") != code_table_reference("TABLE_GOLD")

  // Bug 1.7: Aggregation destroys individual transactions
  IF input.operation == "process_csv_file"
    RETURN process_file_uses_groupby_aggregation() == true

  // Bug 1.8: merchant_clean ignores normalization
  IF input.operation == "process_transaction"
    RETURN merchant_clean_value != classification["merchant_norm"]

  // Bug 1.15: Settlement query contradiction
  IF input.operation == "dashboard_settlement" AND input.tx_type IS NOT NULL
    RETURN input.tx_type != "Shared"
           AND settlement_query_inherits_base_where(input.tx_type) == true

  // Bugs 1.2-1.6, 1.9-1.14: Dead code, unused resources, security
  IF input.operation == "code_audit"
    RETURN dead_code_exists() OR unused_resources_exist() OR credentials_exposed()

  RETURN false
END FUNCTION
```

### Examples

- **Tabela Gold (1.1)**: `processor.py` executa `INSERT INTO transactions_gold` mas Terraform criou `finance_gold` → erro 404 no BigQuery
- **Agregação (1.7)**: Upload de CSV com 50 transações do mesmo merchant → gold recebe apenas 1 linha com soma total, perdendo datas e valores individuais
- **Merchant Clean (1.8)**: Merchant raw "UBER *EATS" → `classification_service` normaliza para "Uber Eats" mas `merchant_clean` recebe "UBER *EATS" (apenas strip)
- **Settlement (1.15)**: Dashboard com `tx_type=Individual` → settlement query tem `WHERE type='Individual' AND type='Shared'` → 0 resultados → settlement sempre "Sem pendências"
- **Credenciais (1.14)**: Clone do repo expõe `apiKey`, `authDomain` e demais credenciais Firebase em `.env.local`

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `classification_service.py` deve continuar aplicando todas as regras customizadas de classificação (keywords, merchants forçados, categorias always-shared/always-individual, lookup de histórico, fallback)
- Modo SQLite local (`USE_SQLITE=true`) deve continuar funcionando para desenvolvimento
- Autenticação Firebase, resolução de tenant/workspace e rate limiting devem permanecer inalterados
- Upload e validação de CSV do Nubank (tamanho, extensão, MIME, detecção de colunas) devem continuar funcionando
- Dashboard deve continuar retornando resumos por categoria, owner e tipo, incluindo tendências
- Workspaces (criação, ativação, convites, membros) devem continuar funcionando
- Patrimônio (upload CSV, visualização mensal, validação cruzada, edição manual) deve continuar funcionando
- `normalization.py` deve continuar aplicando regras de limpeza e `merchant_map.json`
- `category_mapping.py` deve continuar usando `category_map.json` para mapeamento

**Scope:**
Todas as operações que NÃO envolvem os 15 defeitos listados devem ser completamente inalteradas. Isso inclui:
- Endpoints de CRUD de transações (exceto a lógica de processamento do processor)
- Endpoints de workspace e patrimônio
- Lógica de autenticação e autorização
- Frontend (exceto remoção de `.env.local` do tracking)

## Hypothesized Root Cause

Based on the bug analysis and source code review:

1. **Table Name Mismatch (1.1)**: O Terraform define `table_id = "finance_gold"` (linha ~170 de main.tf) mas `processor.py` usa `TABLE_GOLD = "transactions_gold"`. Provável renomeação no código sem atualização do Terraform.

2. **Aggregation Bug (1.7)**: `process_file()` executa `df_proc.groupby(["tenant_id", "merchant_clean", "category", "owner", "type"]).agg({"amount": "sum", "date": "min"})` nas linhas ~210-215 de `processor.py`. Isso foi provavelmente implementado como otimização prematura, mas destrói a granularidade dos dados.

3. **Merchant Clean Bug (1.8)**: Em `_process_chunk()` linha ~125, `merchant_clean = merchant_raw.strip()` é atribuído antes da chamada ao `classification_service`, e o resultado `classification["merchant_norm"]` é armazenado em campo separado mas nunca usado para sobrescrever `merchant_clean`.

4. **Settlement Query Bug (1.15)**: No modo BigQuery, `settlement_where = base_where` herda o filtro `type=@tx_type` do `base_where`. Quando `tx_type="Individual"`, a query adiciona `AND type='Shared'` mas já contém `AND type='Individual'` — contradição lógica. No modo SQLite, o settlement constrói `settlement_where` independentemente mas não verifica se `tx_type != "Shared"` para retornar zerado. No modo Mock, o filtro `tx_type` já filtra as transações antes do cálculo de settlement, mas não há lógica explícita para retornar zerado quando `tx_type != "Shared"`.

5. **Dead Code (1.3, 1.4, 1.6, 1.11, 1.12)**: Arquivos legados de iterações anteriores do projeto que nunca foram removidos: `classifier.py` (substituído por `classification_service.py`), `download_findata.py` (dependências inexistentes), `init_db.py`/`init_sqlite.py` (substituídos por `database.py`), `repository.py` (padrão Repository nunca integrado).

6. **main.py Duplication (1.2)**: Funções foram copiadas para `main.py` durante desenvolvimento rápido e nunca refatoradas para importar dos módulos dedicados.

7. **Unused Terraform Resources (1.9, 1.10)**: Buckets provisionados preventivamente durante setup inicial mas nunca integrados ao código da aplicação.

8. **Frontend Credentials (1.14)**: `.env.local` commitado acidentalmente antes de configurar o `.gitignore` adequadamente.


## Correctness Properties

Property 1: Bug Condition - Terraform Table Name Consistency

_For any_ BigQuery operation referencing the gold table, the table name in the Terraform infrastructure definition SHALL match the table name referenced in the application code (`transactions_gold`), ensuring all reads and writes succeed.

**Validates: Requirements 2.1**

Property 2: Bug Condition - Individual Transaction Preservation in Gold Table

_For any_ CSV file processed by `TransactionProcessor.process_file()`, each valid transaction SHALL be preserved as an individual record in the gold table, without aggregation by merchant+category+owner+type, maintaining the original date, amount, and merchant for each transaction.

**Validates: Requirements 2.7**

Property 3: Bug Condition - Merchant Normalization in Gold Table

_For any_ transaction processed by `TransactionProcessor._process_chunk()`, the `merchant_clean` field in the gold row SHALL contain the normalized merchant value from `classification_service.classify()["merchant_norm"]` instead of the raw stripped merchant name.

**Validates: Requirements 2.8**

Property 4: Bug Condition - Settlement Query Correctness

_For any_ call to `get_dashboard_summary()` where `tx_type` is set and is not "Shared", the settlement result SHALL return zeroed values (`direction: "Sem pendências", amount: 0`) without creating contradictory WHERE clauses, across all three modes (SQLite, BigQuery, Mock).

**Validates: Requirements 2.15**

Property 5: Bug Condition - Dead Code Removal

_For any_ code audit of the repository after the fix, the files `classifier.py`, `download_findata.py`, `init_db.py`, `init_sqlite.py`, and `repository.py` SHALL NOT exist in the backend directory, and `test_health.py` SHALL be located in the `tests/` directory.

**Validates: Requirements 2.3, 2.6, 2.11, 2.12, 2.13**

Property 6: Bug Condition - Dependency Cleanup

_For any_ installation of dependencies via `requirements.txt`, `google-generativeai` and `scikit-learn` SHALL NOT be present, and `processor.py` SHALL NOT import `type_model`.

**Validates: Requirements 2.4, 2.5**

Property 7: Bug Condition - main.py Deduplication

_For any_ execution of `main.py`, duplicated functions and classes SHALL be replaced by imports from their dedicated modules (`helpers.py`, `auth.py`, `models.py`, `upload_validation.py`), with no duplicate definitions remaining.

**Validates: Requirements 2.2**

Property 8: Bug Condition - Unused Infrastructure Removal

_For any_ Terraform plan execution, the buckets `${var.project_id}-internal` and `${var.project_id}-firestore-backups` SHALL NOT be present in the infrastructure definition.

**Validates: Requirements 2.9, 2.10**

Property 9: Bug Condition - Frontend Credential Security

_For any_ clone of the repository, `frontend/.env.local` SHALL NOT be tracked by git, and a `.env.local.example` with placeholder values SHALL exist for developer reference.

**Validates: Requirements 2.14**

Property 10: Preservation - Classification Service Integrity

_For any_ transaction classification operation, the `classification_service.py` module SHALL produce exactly the same results as before the fix, preserving all custom rules (keywords, forced merchants, always-shared/always-individual categories, history lookup, fallback).

**Validates: Requirements 3.1, 3.8, 3.9**

Property 11: Preservation - Existing Functionality

_For any_ operation that does NOT involve the 15 fixed bugs (CRUD transactions, workspaces, patrimônio, authentication, upload validation, dashboard non-settlement logic), the system SHALL produce exactly the same behavior as before the fix.

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**


## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `finance-pilot/infra/main.tf`

**Changes**:
1. **Table Name Fix**: Alterar `table_id = "finance_gold"` para `table_id = "transactions_gold"` no recurso `google_bigquery_table.finance_gold`
2. **Remove Unused Bucket (internal)**: Remover o recurso `google_storage_bucket.finance_internal` e quaisquer referências
3. **Remove Unused Bucket (firestore_backups)**: Remover o recurso `google_storage_bucket.firestore_backups` (seção 9 inteira)

---

**File**: `finance-pilot/backend/processor.py`

**Function**: `_process_chunk()`

**Changes**:
4. **Merchant Clean Fix**: Alterar `merchant_clean = merchant_raw.strip()` para `merchant_clean = classification["merchant_norm"]` (mover a atribuição para depois da chamada ao `classification_svc.classify()`)

**Function**: `process_file()`

**Changes**:
5. **Remove Aggregation**: Remover o bloco `df_proc.groupby(...).agg(...)` e construir `gold_rows` diretamente a partir de `df_proc` (iterando cada linha sem agregação), preservando cada transação individual com seus dados originais
6. **Remove type_model Import**: Remover `from type_model import load_model, predict_types` e `self.type_model = load_model()` do `__init__`

---

**File**: `finance-pilot/backend/main.py`

**Function**: `get_dashboard_summary()`

**Changes**:
7. **SQLite Settlement Fix**: Quando `tx_type` está definido e não é "Shared", retornar settlement zerado (`direction: "Sem pendências", amount: 0`) sem executar a query de settlement
8. **BigQuery Settlement Fix**: Não herdar `base_where` para `settlement_where`; construir `settlement_where` independentemente com apenas `tenant_id` e `month_ref`. Quando `tx_type` não é "Shared", retornar settlement zerado
9. **Mock Settlement Fix**: Quando `tx_type` não é "Shared", retornar settlement zerado explicitamente

**Deduplication Changes**:
10. **Add Imports**: Adicionar imports dos módulos dedicados (`helpers`, `auth`, `models`, `upload_validation`)
11. **Remove Duplicates**: Remover as definições duplicadas de `TenantContext`, `_normalize_owner()`, `_parse_br_money()`, `_parse_br_percent()`, `_parse_month_ref()`, `_parse_ddmmyyyy_to_iso()`, `_parse_signed_amount()`, `_category_for_current_account()`, `_sanitize_tenant_id()`, `_extract_tenant_from_claims()`, `TransactionUpdate`, `TransactionCreate`, `PlanUpdate`, `WorkspaceCreate`, `WorkspaceUpdate`, `WorkspaceInviteCreate`, `NetWorthRowUpdate`, `_utc_now_iso()`, `_normalize_plan()`, `_plan_limits()`, `_normalize_email()` e atualizar todas as referências internas para usar os nomes importados

---

**Dead Code Removal**:
12. **Delete Files**: Remover `classifier.py`, `download_findata.py`, `init_db.py`, `init_sqlite.py`, `repository.py`
13. **Move Test**: Mover `test_health.py` para `tests/test_health.py`

---

**File**: `finance-pilot/backend/requirements.txt`

**Changes**:
14. **Remove Unused Dependencies**: Remover `google-generativeai` e `scikit-learn`

---

**File**: `finance-pilot/frontend/.env.local.example` (novo)

**Changes**:
15. **Create Example File**: Criar `.env.local.example` com placeholders genéricos para credenciais Firebase

**File**: `.gitignore` e `finance-pilot/frontend/.gitignore`

**Changes**:
16. **Gitignore Update**: Adicionar `.env.local` explicitamente ao `.gitignore` raiz
17. **Untrack Credentials**: Executar `git rm --cached finance-pilot/frontend/.env.local`


## Testing Strategy

### Validation Approach

A estratégia de testes segue duas fases: primeiro, confirmar os defeitos no código não-corrigido via counterexamples; depois, verificar que a correção funciona e preserva comportamentos existentes.

### Exploratory Bug Condition Checking

**Goal**: Surfar counterexamples que demonstram os bugs ANTES de implementar a correção. Confirmar ou refutar a análise de root cause.

**Test Plan**: Escrever testes que exercitam cada condição de bug no código não-corrigido e observar as falhas.

**Test Cases**:
1. **Table Name Mismatch Test**: Verificar que `TABLE_GOLD` em `processor.py` não corresponde ao `table_id` no Terraform (will fail on unfixed code)
2. **Aggregation Test**: Processar CSV com múltiplas transações do mesmo merchant e verificar que gold_rows contém menos linhas que o input (will fail on unfixed code — demonstra perda de dados)
3. **Merchant Clean Test**: Processar transação com merchant raw "UBER *EATS" e verificar que `merchant_clean` != `merchant_norm` (will fail on unfixed code)
4. **Settlement Contradiction Test**: Chamar `get_dashboard_summary(tx_type="Individual")` com dados Shared existentes e verificar que settlement retorna 0 (will fail on unfixed code — retorna 0 por contradição, não por lógica correta)
5. **Dead Code Existence Test**: Verificar que `classifier.py`, `download_findata.py` etc. existem no filesystem (will fail on unfixed code — confirma presença de código morto)

**Expected Counterexamples**:
- Aggregation: 10 transações de "Uber Eats" → 1 linha gold com soma total
- Merchant clean: "UBER *EATS" → merchant_clean = "UBER *EATS" em vez de "Uber Eats"
- Settlement: tx_type="Individual" → WHERE contraditório retorna 0 linhas

### Fix Checking

**Goal**: Verificar que para todos os inputs onde a condição de bug se aplica, a função corrigida produz o comportamento esperado.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT expectedBehavior(result)
END FOR
```

Especificamente:
- Para cada CSV processado, verificar que `len(gold_rows) == len(valid_transactions)`
- Para cada transação, verificar que `merchant_clean == classification["merchant_norm"]`
- Para `get_dashboard_summary(tx_type="Individual")`, verificar que settlement = `{"direction": "Sem pendências", "amount": 0}`
- Para Terraform, verificar que `table_id == "transactions_gold"`

### Preservation Checking

**Goal**: Verificar que para todos os inputs onde a condição de bug NÃO se aplica, a função corrigida produz o mesmo resultado que a original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing é recomendado para preservation checking porque:
- Gera muitos test cases automaticamente no domínio de input
- Captura edge cases que testes manuais podem perder
- Fornece garantias fortes de que o comportamento é inalterado para inputs não-buggy

**Test Plan**: Observar comportamento no código não-corrigido para operações não afetadas, depois escrever property-based tests capturando esse comportamento.

**Test Cases**:
1. **Classification Preservation**: Verificar que `classification_service.classify()` retorna os mesmos resultados antes e depois do fix para qualquer merchant/amount/owner
2. **Dashboard Non-Settlement Preservation**: Verificar que `total_spend`, `spend_by_person` e `spend_by_category` retornam os mesmos valores antes e depois do fix
3. **Settlement Shared Preservation**: Verificar que `get_dashboard_summary(tx_type="Shared")` retorna o mesmo settlement antes e depois do fix
4. **Upload Validation Preservation**: Verificar que validação de CSV (tamanho, extensão, MIME) funciona identicamente
5. **SQLite Mode Preservation**: Verificar que CRUD de transações em modo SQLite funciona identicamente

### Unit Tests

- Testar `_process_chunk()` com merchant que requer normalização e verificar `merchant_clean`
- Testar `process_file()` com CSV de múltiplas transações e verificar que cada uma é preservada individualmente
- Testar `get_dashboard_summary()` com `tx_type="Individual"`, `tx_type="Shared"` e `tx_type=None` nos três modos
- Testar que imports em `main.py` resolvem corretamente para os módulos dedicados
- Testar que `requirements.txt` não contém `google-generativeai` nem `scikit-learn`

### Property-Based Tests

- Gerar CSVs aleatórios com N transações e verificar que gold_rows sempre contém N linhas válidas (sem agregação)
- Gerar merchants aleatórios e verificar que `merchant_clean` sempre corresponde ao output de `classification_service.classify()["merchant_norm"]`
- Gerar combinações aleatórias de `tx_type` e verificar que settlement é zerado quando `tx_type != "Shared"` e calculado corretamente quando `tx_type == "Shared"` ou `tx_type == None`
- Gerar inputs aleatórios para `classification_service.classify()` e verificar que o output é idêntico antes e depois do fix

### Integration Tests

- Testar fluxo completo: upload CSV → processamento → verificar dados na tabela gold (cada transação individual preservada)
- Testar dashboard end-to-end com filtros de owner e tx_type, verificando settlement em cada combinação
- Testar que `main.py` inicia sem erros após remoção de duplicatas e importação dos módulos
- Testar que `terraform plan` não mostra erros após as alterações em `main.tf`
