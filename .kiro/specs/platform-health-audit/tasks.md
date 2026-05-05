# Tarefas — Platform Health Audit

## Fase 1: Correções de Infraestrutura (Terraform)

- [x] 1.1 Corrigir nome da tabela gold no Terraform: alterar `table_id = "finance_gold"` para `table_id = "transactions_gold"` em `finance-pilot/infra/main.tf`
- [x] 1.2 Remover bucket `finance_internal` de `finance-pilot/infra/main.tf` (recurso `google_storage_bucket.finance_internal` e referências)
- [x] 1.3 Remover bucket `firestore_backups` de `finance-pilot/infra/main.tf` (seção 9 inteira: recurso `google_storage_bucket.firestore_backups`)

## Fase 2: Remoção de Código Morto

- [x] 2.1 Deletar `finance-pilot/backend/classifier.py`
- [x] 2.2 Deletar `finance-pilot/backend/download_findata.py`
- [x] 2.3 Deletar `finance-pilot/backend/init_db.py`
- [x] 2.4 Deletar `finance-pilot/backend/init_sqlite.py`
- [x] 2.5 Deletar `finance-pilot/backend/repository.py`
- [x] 2.6 Mover `finance-pilot/backend/test_health.py` para `finance-pilot/backend/tests/test_health.py`

## Fase 3: Limpeza de Dependências e Imports

- [x] 3.1 Remover `google-generativeai` e `scikit-learn` de `finance-pilot/backend/requirements.txt`
- [x] 3.2 Remover import de `type_model` e inicialização do modelo ML em `finance-pilot/backend/processor.py` (remover `from type_model import load_model, predict_types` e `self.type_model = load_model()`)

## Fase 4: Correção do Processor (Bugs de Dados)

- [x] 4.1 Corrigir `_process_chunk()` em `finance-pilot/backend/processor.py`: alterar `merchant_clean` de `merchant_raw.strip()` para `classification["merchant_norm"]`
- [x] 4.2 Corrigir `process_file()` em `finance-pilot/backend/processor.py`: remover agregação (groupby+agg) e construir gold_rows diretamente a partir das transações individuais processadas

## Fase 5: Eliminação de Duplicação em main.py

- [x] 5.1 Adicionar imports dos módulos dedicados em `finance-pilot/backend/main.py`: `helpers`, `auth`, `models`, `upload_validation`
- [x] 5.2 Remover definições duplicadas de funções e classes em `finance-pilot/backend/main.py` e atualizar referências para usar os nomes importados dos módulos

## Fase 6: Correção do Settlement Query

- [x] 6.1 Corrigir settlement query no modo SQLite em `get_dashboard_summary()`: quando `tx_type` está definido e não é "Shared", retornar settlement zerado
- [x] 6.2 Corrigir settlement query no modo BigQuery em `get_dashboard_summary()`: não herdar `base_where` para settlement; construir settlement_where independentemente, e quando `tx_type` não é "Shared", retornar settlement zerado
- [x] 6.3 Corrigir settlement no modo Mock em `get_dashboard_summary()`: tornar explícito que settlement é N/A quando `tx_type != "Shared"`

## Fase 7: Segurança do Frontend

- [x] 7.1 Criar `finance-pilot/frontend/.env.local.example` com placeholders genéricos (sem credenciais reais)
- [x] 7.2 Adicionar `.env.local` explicitamente ao `.gitignore` raiz e verificar que o `.gitignore` do frontend já cobre o padrão `.env*`
- [x] 7.3 Remover `finance-pilot/frontend/.env.local` do tracking do git via `git rm --cached`

## Fase 8: Validação

- [x] 8.1 Verificar que `classification_service.py` não foi alterado (diff vazio)
- [x] 8.2 Executar testes existentes (`pytest finance-pilot/backend/tests/`) e confirmar que passam
- [x] 8.3 Verificar que `main.py` importa corretamente dos módulos dedicados e não contém duplicatas
- [x] 8.4 Verificar que `processor.py` não importa `type_model` e não agrega transações
