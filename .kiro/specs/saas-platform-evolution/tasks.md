 # Plano de Implementação: Finance Pilot → SaaS Platform Evolution

## Visão Geral

Este plano transforma o Finance Pilot de uma ferramenta pessoal em uma plataforma SaaS multi-tenant. As tasks seguem a ordem de execução definida: segurança primeiro, limpeza de código pessoal, fundações (cartões e categorias), core feature (extração PDF), integração (upload), marketing (landing page) e monetização (Mercado Pago). Migrações de dados e limpeza de código são tasks transversais executadas no início e ao longo do processo.

## Tasks

- [x] 1. Migração de dados e setup de dependências
  - [x] 1.1 Criar módulo `finance-pilot/backend/migrations/` com scripts de migração reversíveis
    - Criar `migrations/__init__.py`
    - Criar `migrations/001_add_saas_columns.py` com funções `apply()` e `rollback()`
    - A função `apply()` deve adicionar as colunas `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id` e `needs_review` à tabela `transactions_gold`
    - A função `apply()` deve preencher `transaction_source = 'legacy_csv'` e `card_last4 = NULL` para transações existentes
    - A função `rollback()` deve reverter as alterações de schema (criar tabela backup sem colunas novas, copiar dados, renomear)
    - _Requisitos: 9.1, 9.2, 9.4_

  - [x] 1.2 Criar `migrations/002_create_saas_tables.py` para tabelas novas
    - Criar tabela `cards` com constraints CHECK para `last4` (4 dígitos) e `card_type` (individual/shared), UNIQUE(workspace_id, last4)
    - Criar tabela `workspace_category_rules` com UNIQUE(workspace_id, merchant_pattern)
    - Criar tabela `subscriptions` com constraints CHECK para `plan_type` e `status`
    - Criar tabela `upload_history` com constraints CHECK para `statement_type` e `status`
    - Implementar `rollback()` que faz DROP das 4 tabelas
    - _Requisitos: 9.3, 9.4_

  - [x] 1.3 Criar runner de migrações e integrar ao startup da aplicação
    - Criar `migrations/runner.py` que executa migrações pendentes em ordem e registra versão aplicada
    - Integrar chamada ao runner no startup de `main.py` (substituindo `ensure_sqlite_*` inline)
    - Verificar que as 1.572 transações existentes permanecem intactas após migração
    - _Requisitos: 9.5, 9.6_

  - [x] 1.4 Adicionar dependências ao `requirements.txt`
    - Adicionar `hypothesis>=6.100.0,<7.0.0`
    - Adicionar `pdfplumber>=0.11.0,<1.0.0`
    - Adicionar `google-generativeai>=0.8.0`
    - Adicionar `mercadopago>=2.2.0,<3.0.0`
    - _Requisitos: 5.4, 5.5, 8.1_

- [ ] 2. Checkpoint — Verificar migração
  - Executar migrações e confirmar que as 1.572 transações existentes estão preservadas
  - Verificar que as 4 novas tabelas foram criadas corretamente
  - Verificar que as 6 novas colunas existem em `transactions_gold`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Fix Firestore tenant filtering (segurança)
  - [x] 3.1 Corrigir queries Firestore para filtrar por tenant_id no nível da query
    - Em `main.py`, adicionar `.where("tenant_id", "==", tenant.tenant_id)` como primeira cláusula em todas as queries ao Firestore
    - Corrigir endpoint de dashboard-summary, transactions, trend-data e sync-firestore-to-bigquery
    - Remover filtragem de tenant em loops Python (pós-query)
    - _Requisitos: 1.1, 1.2, 1.4_

  - [x] 3.2 Adicionar validação de tenant_id obrigatório em queries
    - Criar guard que rejeita operações Firestore sem filtro de tenant_id (HTTP 400)
    - Aplicar guard em todos os endpoints que acessam Firestore
    - _Requisitos: 1.2_

  - [ ]* 3.3 Escrever testes unitários para isolamento de tenant no Firestore
    - Testar que query sem tenant_id retorna erro 400
    - Testar que query com tenant_id retorna apenas dados do tenant correto
    - Testar que sync-firestore-to-bigquery sincroniza apenas documentos do tenant
    - _Requisitos: 1.1, 1.2, 1.4, 1.5_

- [ ] 4. Remover lógica pessoal hardcoded
  - [x] 4.1 Limpar `config.py` — remover variáveis pessoais
    - Remover `OWNERS = ["Victor", "Larissa"]`
    - Remover `LEGACY_SHARED_EMAILS`, `AUTO_JOIN_LEGACY_WORKSPACE`, `DEFAULT_LEGACY_MEMBER_LIMIT`
    - Atualizar imports em `main.py` que referenciam essas variáveis
    - _Requisitos: 2.4, 2.5_

  - [x] 4.2 Refatorar `classification_service.py` — remover regras pessoais
    - Remover constantes `VICTOR_INDIVIDUAL_KEYWORDS`, `FORCE_SHARED_MERCHANTS`, `ALWAYS_SHARED_CATEGORIES`, `ALWAYS_INDIVIDUAL_CATEGORIES`
    - Remover lógica de `_infer_type()` baseada em owner "Victor"
    - Manter a estrutura da classe `ClassificationService` para ser substituída pelo novo módulo `categories.py` na task 6
    - _Requisitos: 2.6_

  - [x] 4.3 Refatorar endpoint `GET /owners` para retornar membros dinâmicos do workspace
    - Alterar implementação para consultar `workspace_members` do tenant atual
    - Remover referência à variável `OWNERS` de `config.py`
    - Retornar nomes dos membros do workspace (não lista estática)
    - _Requisitos: 2.1, 2.3_

  - [x] 4.4 Limpar `merchant_map.json` — manter apenas mapeamentos universais
    - Remover mapeamentos pessoais (nomes de pessoas, eventos pessoais, etc.)
    - Manter mapeamentos universais: Amazon, Netflix, Uber, iFood, Spotify, Google, Apple, etc.
    - _Requisitos: 10.2_

  - [ ]* 4.5 Escrever testes para verificar remoção de lógica pessoal
    - Verificar que `config.py` não contém referências a "Victor", "Larissa"
    - Verificar que `classification_service.py` não contém keywords pessoais
    - Verificar que `GET /owners` retorna membros do workspace
    - _Requisitos: 2.4, 2.6, 2.3_

  - [ ]* 4.6 Escrever teste de propriedade para owners dinâmicos do workspace
    - **Propriedade 6: Owners dinâmicos do workspace**
    - **Valida: Requisitos 2.1, 2.3**

- [ ] 5. Checkpoint — Verificar limpeza
  - Verificar zero referências hardcoded a "Victor", "Larissa" no código-fonte
  - Verificar que `GET /owners` retorna membros do workspace dinamicamente
  - Verificar que dados legados (1.572 transações) mantêm seus valores originais de owner e type
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. CRUD de cartões
  - [x] 6.1 Criar `finance-pilot/backend/card_service.py` com lógica de negócio
    - Implementar funções: `create_card()`, `list_cards()`, `get_card()`, `update_card()`, `delete_card()`
    - Validar `last4` como exatamente 4 dígitos numéricos
    - Validar `card_type` como `"individual"` ou `"shared"`
    - Verificar unicidade de `last4` por workspace (retornar HTTP 409 se duplicado)
    - Garantir isolamento por tenant em todas as operações
    - _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 6.2 Adicionar endpoints REST de cartões em `main.py`
    - `POST /cards` — cria cartão no workspace atual
    - `GET /cards` — lista cartões do workspace atual
    - `PUT /cards/{id}` — atualiza cartão (somente do workspace atual)
    - `DELETE /cards/{id}` — remove cartão (somente do workspace atual)
    - Usar modelos Pydantic `CardCreate` e `CardResponse` conforme design
    - _Requisitos: 3.1, 3.4, 3.5, 3.6_

  - [ ]* 6.3 Escrever teste de propriedade para validação de cartão
    - **Propriedade 1: Validação de cartão — last4 e card_type**
    - **Valida: Requisitos 3.2, 3.7**

  - [ ]* 6.4 Escrever teste de propriedade para unicidade de cartão por workspace
    - **Propriedade 2: Unicidade de cartão por workspace**
    - **Valida: Requisito 3.3**

  - [ ]* 6.5 Escrever teste de propriedade para isolamento de cartões por tenant
    - **Propriedade 3: Isolamento de cartões por tenant**
    - **Valida: Requisitos 3.4, 3.5, 3.6**

- [x] 7. Sistema de categorias genéricas
  - [x] 7.1 Criar `finance-pilot/backend/categories.py` com categorias padrão SaaS
    - Definir `DEFAULT_CATEGORIES` com 16 categorias e keywords associados (Alimentação, Delivery, Mercado, Transporte, Moradia, Saúde, Educação, Lazer, Streaming, Compras, Assinaturas, Viagem, Pets, Impostos/Taxas, Transferência, Outros)
    - Implementar `ClassificationService` refatorado com 3 níveis de prioridade: (1) regra do workspace, (2) keywords genéricos, (3) fallback "Outros" + `needs_review=true`
    - Implementar `_get_workspace_rule()` que consulta tabela `workspace_category_rules`
    - Implementar `_match_default_keywords()` com match parcial case-insensitive
    - _Requisitos: 4.1, 4.2, 4.3, 4.6_

  - [x] 7.2 Adicionar endpoints REST para regras de categoria customizadas
    - `POST /category-rules` — cria regra para o workspace atual
    - `GET /category-rules` — lista regras do workspace atual
    - `PUT /category-rules/{id}` — atualiza regra
    - `DELETE /category-rules/{id}` — remove regra
    - Usar modelos Pydantic `CategoryRuleCreate` e `CategoryRuleResponse`
    - _Requisitos: 4.5_

  - [x] 7.3 Integrar novo `ClassificationService` no fluxo existente
    - Substituir imports do antigo `classification_service.py` pelo novo `categories.py` em `processor.py` e `main.py`
    - Garantir que categorias existentes nas 1.572 transações legadas NÃO são reclassificadas
    - _Requisitos: 4.4_

  - [ ]* 7.4 Escrever teste de propriedade para cadeia de prioridade da classificação
    - **Propriedade 4: Cadeia de prioridade da classificação**
    - **Valida: Requisitos 4.2, 4.3, 4.6**

- [ ] 8. Checkpoint — Verificar fundações (cartões + categorias)
  - Verificar CRUD completo de cartões com isolamento por tenant
  - Verificar classificação com 3 níveis de prioridade funcionando
  - Verificar que categorias legadas não foram alteradas
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Serviço de extração de PDF via Gemini Flash 2.5
  - [x] 9.1 Criar modelos Pydantic para schema de extração
    - Criar `ExtractedStatement`, `ExtractedSection`, `ExtractedTransaction` em `extraction_service.py`
    - Campos de `ExtractedTransaction`: date, card_last4, description, amount, is_refund, is_installment, installment_current, installment_total, original_currency
    - Campos de `ExtractedStatement`: statement_type, bank, holder_name, due_date, period_start, period_end, total_amount, sections
    - _Requisitos: 5.1, 5.2_

  - [x] 9.2 Implementar `ExtractionService` com pipeline cache → Gemini → fallback
    - Implementar cache em memória por hash SHA-256 do PDF
    - Implementar `_call_gemini()` com prompt estruturado que solicita JSON no schema definido
    - Implementar retry com exponential backoff (3 tentativas: 1s, 2s, 4s)
    - Implementar validação do JSON retornado contra schema Pydantic
    - _Requisitos: 5.1, 5.3, 5.4, 5.6_

  - [x] 9.3 Implementar fallback com pdfplumber + regex para faturas Nubank
    - Implementar `_fallback_pdfplumber()` que extrai transações via regex
    - Suportar separação de seções por titular (cartões adicionais)
    - _Requisitos: 5.5, 5.7_

  - [ ]* 9.4 Escrever teste de propriedade para round-trip do schema de extração
    - **Propriedade 7: Round-trip do schema de extração**
    - **Valida: Requisitos 5.2, 5.6**

  - [ ]* 9.5 Escrever teste de propriedade para cache SHA-256
    - **Propriedade 8: Cache de extração por hash SHA-256**
    - **Valida: Requisito 5.3**

- [x] 10. Novo fluxo de upload (PDF → Preview → Confirmar)
  - [x] 10.1 Refatorar `upload_validation.py` para aceitar PDF e CSV
    - Adicionar MIME types de PDF (`application/pdf`) à lista de tipos aceitos
    - Atualizar validação de extensão para aceitar `.pdf` e `.csv`
    - Manter limite de 10MB
    - _Requisitos: 6.4_

  - [x] 10.2 Implementar endpoint `POST /upload` com preview (sem salvar)
    - Detectar tipo de arquivo (PDF ou CSV) automaticamente
    - Para PDF: chamar `ExtractionService.extract()` e retornar preview
    - Para CSV: manter fluxo existente de parsing
    - Cruzar `card_last4` com cartões cadastrados para sugerir `card_type`
    - Marcar transações com cartão não cadastrado como `needs_review = true`
    - Retornar `UploadPreviewResponse` conforme design (sem salvar no banco)
    - Extrair owner e mês de referência automaticamente do conteúdo do PDF
    - _Requisitos: 6.1, 6.3, 6.5, 6.7_

  - [x] 10.3 Implementar endpoint `POST /upload/confirm` para salvar transações
    - Receber lista de transações confirmadas (possivelmente editadas pelo usuário)
    - Cruzar `card_last4` com cartões cadastrados para definir `card_type`
    - Classificar categorias usando novo `ClassificationService`
    - Salvar transações com colunas: card_last4, card_type, is_refund, transaction_source='pdf_extraction', upload_id, needs_review
    - Registrar upload na tabela `upload_history` com todos os campos obrigatórios
    - _Requisitos: 6.2, 6.6, 6.8_

  - [x] 10.4 Refatorar componente `UploadForm.tsx` no frontend
    - Aceitar `.pdf` e `.csv` no input de arquivo e drag & drop
    - Remover dropdown de "tipo de arquivo" (detectar automaticamente)
    - Remover campo "owner" (extrair do PDF)
    - Remover campo "mês referência" (extrair do PDF)
    - Após upload, exibir tela de preview com `UploadPreview` component
    - _Requisitos: 6.1, 6.4, 6.7_

  - [x] 10.5 Criar componente `UploadPreview.tsx`
    - Tabela com transações extraídas (data, descrição, valor, categoria sugerida)
    - Highlight amarelo para transações com cartão não cadastrado
    - Highlight para transações não classificadas (`needs_review`)
    - Botão "Confirmar e Importar" que chama `POST /upload/confirm`
    - _Requisitos: 6.1, 6.3_

  - [x] 10.6 Criar componente `CardOnboarding.tsx`
    - Modal que aparece quando upload detecta cartões não cadastrados
    - Lista cartões detectados (last4) e permite classificar como individual/shared
    - Salva cartões via `POST /cards` antes de confirmar importação
    - _Requisitos: 6.3_

  - [ ]* 10.7 Escrever teste de propriedade para determinação de tipo por cartão
    - **Propriedade 5: Determinação de tipo por cartão cadastrado**
    - **Valida: Requisitos 2.2, 6.2, 6.3**

  - [ ]* 10.8 Escrever teste de propriedade para registro de upload_history
    - **Propriedade 9: Registro de upload_history na confirmação**
    - **Valida: Requisito 6.6**

- [ ] 11. Checkpoint — Verificar fluxo de upload end-to-end
  - Verificar que upload de PDF funciona: PDF → extração → preview → confirm → transações no DB
  - Verificar que cartões não cadastrados são destacados no preview
  - Verificar que upload_history é registrado corretamente
  - Verificar que categorias são aplicadas conforme cadeia de prioridade
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Landing page pública
  - [x] 12.1 Criar estrutura de route groups `(public)` e `(app)` no frontend
    - Criar `finance-pilot/frontend/app/(public)/layout.tsx` — layout sem sidebar, sem auth guard
    - Criar `finance-pilot/frontend/app/(app)/layout.tsx` — layout com AppShell + auth guard
    - Mover dashboard de `app/page.tsx` para `app/(app)/page.tsx`
    - Mover `transactions/`, `upload/`, `patrimonio/`, `workspace/` para dentro de `(app)/`
    - Manter `login/page.tsx` fora dos route groups
    - _Requisitos: 7.1, 7.3_

  - [x] 12.2 Criar landing page em `(public)/page.tsx`
    - Seção Hero: "Organize suas finanças em minutos" com CTA "Comece grátis"
    - Seção Como Funciona: 3 passos com ícones (Upload PDF → Revisão → Dashboard)
    - Seção Bancos Suportados: Nubank (+ "mais em breve")
    - Seção Screenshots do produto
    - Seção Planos e Preços com componente `PricingTable` (Free/Pro/Família)
    - Seção FAQ com accordion
    - CTA final de cadastro
    - Informar que plano Free funciona sem cartão de crédito
    - _Requisitos: 7.2, 7.6_

  - [x] 12.3 Criar componente `PricingTable.tsx`
    - Tabela comparativa: Free (R$0), Pro (R$19/mês), Família (R$39/mês)
    - Features: uploads/mês, histórico, membros, cartões, exportação, divisão de despesas
    - Botões de CTA para cada plano
    - _Requisitos: 7.2_

  - [x] 12.4 Implementar SEO e redirect de usuário autenticado
    - Adicionar meta tags de SEO e Open Graph na landing page
    - Implementar redirect automático para dashboard quando usuário está autenticado
    - Garantir design responsivo mobile-first (zona do polegar, hierarquia visual CRAP)
    - _Requisitos: 7.3, 7.4, 7.5_

- [x] 13. Integração de billing com Mercado Pago
  - [x] 13.1 Criar `finance-pilot/backend/billing_service.py`
    - Implementar `BillingService` com configuração de planos (Pro: R$19, Família: R$39)
    - Implementar `create_subscription()` que cria `preapproval` no Mercado Pago e retorna `init_point`
    - Implementar `process_webhook()` idempotente que atualiza status da assinatura e `plan_type` do workspace
    - Implementar `cancel_subscription()` que cancela `preapproval` no Mercado Pago
    - Implementar `check_limit()` que verifica limites do plano antes de operações restritas
    - Definir `PLAN_LIMITS`: uploads/mês (Free=2, Pro=∞, Família=∞), histórico (Free=3m, Pro=12m, Família=∞), membros (Free=1, Pro=1, Família=4), cartões (Free=2, Pro=5, Família=10)
    - _Requisitos: 8.1, 8.2, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [x] 13.2 Adicionar endpoints de billing em `main.py`
    - `POST /billing/create-subscription` — cria assinatura e retorna URL de checkout
    - `POST /billing/webhook` — recebe IPN do Mercado Pago (idempotente)
    - `GET /billing/status` — retorna status da assinatura do workspace
    - `POST /billing/cancel` — cancela assinatura
    - _Requisitos: 8.1, 8.2, 8.3, 8.4_

  - [x] 13.3 Integrar verificação de limites de plano nos endpoints existentes
    - Adicionar check de limite de uploads/mês no `POST /upload`
    - Adicionar check de limite de cartões no `POST /cards`
    - Adicionar check de limite de membros nos endpoints de workspace
    - Retornar HTTP 402 quando limite é excedido com sugestão de upgrade
    - Garantir que plano Free funciona sem dados de cartão de crédito
    - _Requisitos: 8.5, 8.6_

  - [ ]* 13.4 Escrever teste de propriedade para idempotência do webhook
    - **Propriedade 10: Idempotência do webhook de billing**
    - **Valida: Requisito 8.8**

  - [ ]* 13.5 Escrever teste de propriedade para enforcement de limites de plano
    - **Propriedade 11: Enforcement de limites de plano**
    - **Valida: Requisito 8.5**

  - [ ]* 13.6 Escrever teste de propriedade para atualização de status via webhook
    - **Propriedade 12: Webhook atualiza status e plan_type corretamente**
    - **Valida: Requisitos 8.2, 8.7**

- [x] 14. Limpeza de código e arquivos
  - [x] 14.1 Remover arquivos mortos do repositório
    - Deletar `finance-pilot/finance.db` (cópia stale)
    - Deletar `finance-pilot/data/backups/legacy_backup.csv`
    - Deletar `finance-pilot/data/backups/findata_backup_20260202_164435.csv`
    - Deletar `finance-pilot/data/backups/findata_backup_20260202_164435_clean.csv`
    - Deletar `finance-pilot/backend/type_model.py` (modelo ML não utilizado)
    - _Requisitos: 10.1_

  - [x] 14.2 Substituir `category_map.json` pelo sistema de categorias padrão
    - Remover `category_map.json` (496 entradas pessoais)
    - Atualizar `category_mapping.py` para usar `DEFAULT_CATEGORIES` de `categories.py`
    - _Requisitos: 10.3_

  - [x] 14.3 Limpar script de deploy e referências legadas
    - Remover referências ao projeto `portfolio` de `deploy_financial_platform.sh`
    - _Requisitos: 10.4_

- [ ] 15. Checkpoint final — Verificação completa
  - Verificar que nenhum dado existente foi perdido (1.572 transações preservadas)
  - Verificar zero referências hardcoded a "Victor", "Larissa" no código
  - Verificar que todos os endpoints filtram por tenant_id no nível da query
  - Verificar que upload de PDF funciona end-to-end (PDF → preview → confirmar → dashboard)
  - Verificar que cartões cadastrados determinam tipo (individual/shared) das transações
  - Verificar que landing page é acessível sem login
  - Verificar que plano Free funciona sem cartão de crédito
  - Verificar que nenhum arquivo morto ou código duplicado permanece no repositório
  - Ensure all tests pass, ask the user if questions arise.

## Notas

- Tasks marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Cada task referencia requisitos específicos para rastreabilidade
- Checkpoints garantem validação incremental a cada fase
- Testes de propriedade validam propriedades universais de corretude definidas no design
- Testes unitários validam exemplos específicos e edge cases
- Migrações são sempre reversíveis — cada script tem `apply()` e `rollback()`
- Dados legados (1.572 transações) NUNCA são alterados ou reclassificados automaticamente
