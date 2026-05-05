# MELHORIAS — Finance Pilot → SaaS

> Documento de especificação para transformar o Finance Pilot em um SaaS vendável.
> **Proposta:** Plataforma que lê PDFs de conta corrente e cartão de crédito, identifica entradas e saídas, e organiza a vida financeira do usuário.

---

## Contexto Atual

### Dados existentes (preservar obrigatoriamente)
- **1.572 transações** (Victor: 1.112, Larissa: 460)
- **Período:** 2024-02 a 2026-02
- **Valor total:** R$ 563.512,50
- **Banco:** SQLite local (`finance-pilot/backend/finance.db`)
- **Cloud:** Firestore + BigQuery no projeto `aifin-project` (GCP)
- **Backup criado em:** 2026-05-01 (`finance-pilot/data/backups/`)

### Infraestrutura atual
- **Backend:** FastAPI (Python 3.11) no Cloud Run
- **Frontend:** Next.js 15 + React 19 no Cloud Run
- **Auth:** Firebase Authentication
- **Infra:** Terraform (GCS, Firestore, BigQuery, Cloud Run, Artifact Registry)
- **Deploy:** Scripts manuais (`deploy.sh`)

---

## Segurança de Dados

### Backup local (implementado)
- Script: `finance-pilot/scripts/backup.sh`
- Cria: cópia atômica do SQLite + CSVs de cada tabela
- Retenção: últimos 10 backups
- Custo: $0

### Backup cloud (implementado)
- Script: `finance-pilot/scripts/backup_cloud.sh`
- Exporta: Firestore + BigQuery → Cloud Storage
- Retenção: 30 dias
- Custo: ~$0.01/execução

### Regra de migração
- **NUNCA deletar tabelas existentes** — apenas adicionar colunas ou criar tabelas novas
- **Migrations devem ser reversíveis** — sempre ter rollback
- **Dados legados** ficam com `card_last4 = NULL` e `transaction_source = 'legacy_csv'`

---

## Inventário de Código — O que REMOVER após migração

### Arquivos a deletar
| Arquivo | Motivo |
|---------|--------|
| `finance-pilot/finance.db` | Cópia stale do DB (o real está em `backend/finance.db`) |
| `finance-pilot/data/backups/legacy_backup.csv` | Formato antigo, dados já migrados |
| `finance-pilot/data/backups/findata_backup_20260202_164435.csv` | Substituído por backup automatizado |
| `finance-pilot/data/backups/findata_backup_20260202_164435_clean.csv` | Idem |
| `finance-pilot/backend/type_model.py` | Modelo ML não usado (classificação é por regras) |

### Código a refatorar/remover dentro de arquivos existentes
| Local | O que remover | Substituir por |
|-------|---------------|----------------|
| `config.py` | `OWNERS = ["Victor", "Larissa"]` | Owners dinâmicos do workspace |
| `config.py` | `LEGACY_SHARED_EMAILS`, `AUTO_JOIN_LEGACY_WORKSPACE` | Removido (não existe mais conceito legacy) |
| `classification_service.py` | `VICTOR_INDIVIDUAL_KEYWORDS` | Classificação por cartão cadastrado |
| `classification_service.py` | `FORCE_SHARED_MERCHANTS` | Classificação por cartão cadastrado |
| `classification_service.py` | `ALWAYS_SHARED_CATEGORIES`, `ALWAYS_INDIVIDUAL_CATEGORIES` | Configurável por workspace |
| `normalization.py` | Mapeamentos pessoais em `merchant_map.json` | Mapa genérico + mapa por workspace |
| `category_mapping.py` | `category_map.json` (496 entries pessoais) | Categorias padrão SaaS + custom por workspace |
| `processor.py` | Parser CSV hardcoded (colunas Nubank) | LLM extraction service |
| `upload_validation.py` | Rejeição de não-CSV | Aceitar PDF + CSV + OFX |
| `main.py` | Lógica de `_day_name_pt()` no processor | Remover (não usado no gold) |
| `main.py` | `ensure_sqlite_*` migrations inline | Mover para módulo `migrations/` |
| `deploy_financial_platform.sh` | Referência a `portfolio` (projeto separado) | Remover seção portfolio |
| `frontend/cloudbuild.yaml` | Credenciais Firebase hardcoded | Usar substitutions do Cloud Build |

### Recursos cloud a limpar
| Recurso | Motivo |
|---------|--------|
| BigQuery `finance_gold` table | Tabela legacy não usada (schema diferente de `transactions_gold`) |
| BigQuery table expiration (6 meses) | Remover — dados não devem expirar |

---

## Especificação Técnica — Fase 1 (MVP SaaS)

### Task 1: Serviço de extração de PDF via Gemini Flash 2.5

**Objetivo:** Substituir o parser CSV por extração inteligente de PDF usando LLM.

**Criar:**
- `finance-pilot/backend/extraction_service.py` — módulo dedicado para chamadas ao Gemini
- Prompt estruturado que extrai transações do PDF do Nubank (crédito)
- Schema de validação do JSON retornado (Pydantic)
- Cache por hash SHA-256 do arquivo (evitar reprocessar mesmo PDF)
- Retry com exponential backoff (3 tentativas)
- Fallback: pdfplumber + regex para Nubank

**Input:** bytes do PDF
**Output:**
```python
class ExtractedStatement(BaseModel):
    statement_type: Literal["credit_card", "current_account"]
    bank: str  # "nubank"
    holder_name: str
    due_date: Optional[str]  # YYYY-MM-DD
    period_start: str  # YYYY-MM-DD
    period_end: str  # YYYY-MM-DD
    total_amount: float
    sections: list[ExtractedSection]

class ExtractedSection(BaseModel):
    owner_name: str
    subtotal: float
    transactions: list[ExtractedTransaction]

class ExtractedTransaction(BaseModel):
    date: str  # YYYY-MM-DD
    card_last4: Optional[str]  # "1171" ou None para NuTag/NuPay
    description: str
    amount: float
    is_refund: bool
    is_installment: bool
    installment_current: Optional[int]
    installment_total: Optional[int]
    original_currency: Optional[str]  # "USD" para internacionais
```

**Dependências:** `google-generativeai` (SDK do Gemini), `pdfplumber` (fallback)

**Custo:** ~R$0,005 por fatura (Gemini Flash 2.5 input pricing)

---

### Task 2: CRUD de cartões (últimos 4 dígitos)

**Objetivo:** Permitir que o usuário cadastre seus cartões e defina se cada um é individual ou compartilhado.

**Criar:**
- Tabela `cards` no SQLite/PostgreSQL
- Endpoints REST: `POST /cards`, `GET /cards`, `PUT /cards/{id}`, `DELETE /cards/{id}`
- Modelo Pydantic para request/response

**Schema:**
```sql
CREATE TABLE cards (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    last4 TEXT NOT NULL,
    label TEXT,
    card_type TEXT NOT NULL CHECK(card_type IN ('individual', 'shared')),
    bank TEXT DEFAULT 'nubank',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(workspace_id, last4)
);
```

**Regras:**
- `last4` deve ter exatamente 4 dígitos
- Não permitir duplicata de `last4` dentro do mesmo workspace
- Cada cartão pertence a um `owner` (membro do workspace)
- `card_type` determina se transações nesse cartão são individuais ou compartilhadas

**Frontend:**
- Tela de configuração de cartões (acessível via Settings ou primeiro upload)
- Onboarding: após primeiro upload de PDF, mostrar cartões detectados e pedir para classificar

---

### Task 3: Novo fluxo de upload (PDF → preview → confirmar)

**Objetivo:** Upload simplificado — drag & drop do PDF, zero input manual.

**Alterar:**
- `upload_validation.py` — aceitar PDF além de CSV
- `POST /upload` — novo fluxo:
  1. Recebe PDF
  2. Chama `extraction_service.py`
  3. Retorna preview das transações extraídas (não salva ainda)
- `POST /upload/confirm` — novo endpoint:
  1. Recebe lista de transações confirmadas (possivelmente editadas pelo usuário)
  2. Cruza `card_last4` com cadastro de cartões → define `type`
  3. Classifica categorias
  4. Salva no banco
  5. Invalida cache do dashboard

**Frontend (`UploadForm.tsx`):**
- Remover dropdown de "tipo de arquivo" (detectar automaticamente)
- Remover campo "owner" (extrair do PDF)
- Remover campo "mês referência" (extrair do PDF)
- Adicionar tela de preview pós-extração:
  - Tabela com transações extraídas
  - Highlight de transações com cartão não cadastrado (pedir para cadastrar)
  - Highlight de transações não classificadas
  - Botão "Confirmar e Importar"
- Aceitar `.pdf` e `.csv` no input

---

### Task 4: Categorias genéricas + classificação

**Objetivo:** Substituir categorias pessoais por sistema genérico escalável.

**Criar:**
- `finance-pilot/backend/categories.py` — categorias padrão do SaaS
- Tabela `workspace_category_rules` para regras customizadas por workspace

**Categorias padrão:**
```python
DEFAULT_CATEGORIES = {
    "Alimentação": ["restaurante", "bar", "padaria", "lanchonete", "pizza", "sushi", "hamburgu"],
    "Delivery": ["ifood", "rappi", "uber eats", "ifd*"],
    "Mercado": ["mercado", "supermercado", "hortifruti", "carrefour", "assai"],
    "Transporte": ["uber", "99", "cabify", "combustivel", "posto", "estacionamento", "pedagio", "nutag"],
    "Moradia": ["aluguel", "condominio", "luz", "energia", "agua", "gas", "internet"],
    "Saúde": ["farmacia", "drogaria", "medico", "hospital", "academia", "totalpass"],
    "Educação": ["curso", "escola", "udemy", "alura", "linkedin"],
    "Lazer": ["cinema", "show", "ingresso", "parque"],
    "Streaming": ["netflix", "spotify", "disney", "hbo", "amazon prime", "youtube premium", "apple tv"],
    "Compras": ["shopee", "mercado livre", "amazon", "magazine"],
    "Assinaturas": ["google one", "icloud", "canva", "chatgpt", "github", "claude"],
    "Viagem": ["airbnb", "hotel", "pousada", "booking", "azul", "latam", "gol"],
    "Pets": ["petlove", "petshop", "veterinario"],
    "Impostos/Taxas": ["iof", "anuidade", "taxa"],
    "Transferência": ["pix", "ted", "transferencia"],
    "Outros": [],
}
```

**Lógica de classificação (em ordem):**
1. Regra do workspace (tabela `workspace_category_rules`) — match exato por merchant_clean
2. Keywords genéricos (DEFAULT_CATEGORIES) — match parcial
3. Não classificado → marcar como "Outros" + flag `needs_review = true`

**Migração de dados legados:**
- Manter categorias existentes nas 1.572 transações
- Não reclassificar automaticamente (usuário pode fazer manualmente se quiser)

---

### Task 5: Remover lógica pessoal

**Objetivo:** Limpar todo código específico de Victor/Larissa.

**Alterações em `config.py`:**
```python
# REMOVER:
OWNERS = ["Victor", "Larissa"]
LEGACY_SHARED_EMAILS = ...
AUTO_JOIN_LEGACY_WORKSPACE = ...
DEFAULT_LEGACY_MEMBER_LIMIT = ...

# MANTER (mas tornar dinâmico):
# Owners agora vêm do workspace (membros cadastrados)
```

**Alterações em `classification_service.py`:**
- Remover `VICTOR_INDIVIDUAL_KEYWORDS`
- Remover `FORCE_SHARED_MERCHANTS`
- Remover `ALWAYS_SHARED_CATEGORIES` / `ALWAYS_INDIVIDUAL_CATEGORIES`
- Tipo agora é determinado pelo `card_type` do cartão cadastrado

**Alterações em `main.py`:**
- Endpoint `GET /owners` → retornar membros do workspace (não mais config estática)
- Settlement → calcular baseado em cartões `shared`, não em categorias hardcoded

**Dados:**
- `merchant_map.json` → manter apenas mapeamentos universais (Amazon, Netflix, Uber, etc.), remover pessoais
- `category_map.json` → substituir por `DEFAULT_CATEGORIES` + `workspace_category_rules`

---

### Task 6: Landing page

**Objetivo:** Página pública para atrair e converter usuários.

**Criar:**
- `finance-pilot/frontend/app/(public)/page.tsx` — landing page (rota pública)
- Mover dashboard para `finance-pilot/frontend/app/(app)/dashboard/page.tsx`
- Layout público vs layout autenticado

**Seções:**
1. Hero: "Organize suas finanças em minutos"
2. Como funciona (3 steps com ícones)
3. Bancos suportados (Nubank por enquanto, "mais em breve")
4. Screenshots
5. Pricing (Free / Pro / Família)
6. FAQ
7. CTA: "Comece grátis"

**Técnico:**
- SEO: meta tags, Open Graph
- Mobile-first
- Se logado, redirecionar para `/dashboard`

---

### Task 7: Integração Mercado Pago

**Objetivo:** Monetizar com assinaturas recorrentes.

**Criar:**
- `finance-pilot/backend/billing_service.py` — integração com API do Mercado Pago
- Endpoints: `POST /billing/create-subscription`, `POST /billing/webhook`, `GET /billing/status`, `POST /billing/cancel`
- Tabela `subscriptions` no banco

**Planos:**
| Feature | Free | Pro (R$19/mês) | Família (R$39/mês) |
|---------|------|-----------------|---------------------|
| Uploads/mês | 2 | Ilimitado | Ilimitado |
| Histórico | 3 meses | 12 meses | Ilimitado |
| Membros | 1 | 1 | 4 |
| Cartões | 2 | 5 | 10 |
| Exportação | ❌ | CSV | CSV + PDF |
| Divisão de despesas | ❌ | ❌ | ✅ |

**Fluxo:**
1. Usuário clica "Assinar Pro" na landing ou settings
2. Backend cria `preapproval` no Mercado Pago → retorna `init_point` (URL de checkout)
3. Frontend redireciona para checkout do MP
4. MP processa pagamento → envia webhook (IPN) para backend
5. Backend atualiza `plan_type` do workspace
6. Middleware verifica limites antes de cada operação

**Schema:**
```sql
CREATE TABLE subscriptions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    mp_preapproval_id TEXT,
    plan_type TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'active', 'paused', 'cancelled', 'pending'
    trial_ends_at TIMESTAMP,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

### Task 8: Fix Firestore tenant filtering

**Objetivo:** Corrigir vulnerabilidade de segurança onde dados de outros tenants são carregados em memória.

**Alterar em `main.py`:**
```python
# ANTES (inseguro):
query = db_firestore.collection(FIRESTORE_COLLECTION)
query = query.where("month_ref", ">=", start).where("month_ref", "<=", end_month)
# filtra tenant em loop

# DEPOIS (seguro):
query = db_firestore.collection(FIRESTORE_COLLECTION)
query = query.where("tenant_id", "==", tenant.tenant_id)
query = query.where("month_ref", ">=", start).where("month_ref", "<=", end_month)
```

**Também:**
- Mesmo fix no endpoint `sync-firestore-to-bigquery`
- Adicionar Firestore Security Rules que impedem leitura cross-tenant

---

## Especificação Técnica — Fase 2

### Task 9: Conta corrente (PDF)
- Prompt LLM específico para extrato de conta corrente
- Diferenciar entrada vs saída
- Evitar duplicidade com fatura de cartão (pagamento de fatura = ignorar)

### Task 10: Metas por categoria
- Tabela `category_budgets` (workspace_id, category, monthly_limit)
- Indicador visual no dashboard quando categoria ultrapassa meta
- Notificação (email ou in-app)

### Task 11: Refatorar main.py em routers
- `routers/transactions.py`
- `routers/upload.py`
- `routers/dashboard.py`
- `routers/workspaces.py`
- `routers/billing.py`
- `routers/cards.py`
- `services/` layer para lógica de negócio

### Task 12: PostgreSQL como banco principal
- Migrar de SQLite para PostgreSQL (Cloud SQL ou Supabase)
- Alembic para migrations
- Row-Level Security (RLS) por tenant_id

### Task 13: Mais bancos
- Itaú, Bradesco, Santander, Inter, C6
- Prompt LLM adaptado por banco
- Detecção automática do banco pelo layout do PDF

### Task 14: Exportação
- CSV download das transações filtradas
- PDF report mensal (resumo + gráficos)

### Task 15: Detecção automática de owner/mês
- Extrair do PDF sem input do usuário
- Matching de nome no PDF com membros do workspace

---

## Especificação Técnica — Fase 3

### Task 16: ML/LLM para classificação com feedback loop
### Task 17: Projeções e insights automáticos
### Task 18: App mobile (React Native)
### Task 19: Open Finance (conexão direta com banco)
### Task 20: Relatório mensal automático por email
### Task 21: Integração com Google Sheets

---

## Modelo de Dados — Schema Final (Fase 1)

### Tabelas novas
```sql
-- Cartões cadastrados
CREATE TABLE cards (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    last4 TEXT NOT NULL,
    label TEXT,
    card_type TEXT NOT NULL CHECK(card_type IN ('individual', 'shared')),
    bank TEXT DEFAULT 'nubank',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(workspace_id, last4)
);

-- Regras de categoria por workspace
CREATE TABLE workspace_category_rules (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    merchant_pattern TEXT NOT NULL,
    category TEXT NOT NULL,
    created_by TEXT,
    created_at TIMESTAMP
);

-- Assinaturas (billing)
CREATE TABLE subscriptions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    mp_preapproval_id TEXT,
    plan_type TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active',
    trial_ends_at TIMESTAMP,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Histórico de uploads
CREATE TABLE upload_history (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size_bytes INTEGER,
    statement_type TEXT,  -- 'credit_card', 'current_account'
    bank TEXT,
    period_start TEXT,
    period_end TEXT,
    transactions_count INTEGER,
    status TEXT NOT NULL,  -- 'processing', 'completed', 'failed', 'reverted'
    error_message TEXT,
    created_at TIMESTAMP
);
```

### Alterações em tabelas existentes
```sql
-- transactions_gold: adicionar colunas
ALTER TABLE transactions_gold ADD COLUMN card_last4 TEXT;
ALTER TABLE transactions_gold ADD COLUMN card_type TEXT;  -- 'individual' ou 'shared'
ALTER TABLE transactions_gold ADD COLUMN is_refund INTEGER DEFAULT 0;
ALTER TABLE transactions_gold ADD COLUMN transaction_source TEXT DEFAULT 'legacy_csv';  -- 'pdf_extraction', 'manual', 'legacy_csv'
ALTER TABLE transactions_gold ADD COLUMN upload_id TEXT;  -- FK para upload_history
ALTER TABLE transactions_gold ADD COLUMN needs_review INTEGER DEFAULT 0;
```

---

## Ordem de Execução

```
1. Task 8 (Fix Firestore) — segurança, rápido
2. Task 5 (Remover lógica pessoal) — limpeza, desbloqueia o resto
3. Task 2 (CRUD de cartões) — fundação do novo modelo
4. Task 4 (Categorias genéricas) — fundação da classificação
5. Task 1 (Extração PDF via Gemini) — core feature
6. Task 3 (Novo fluxo de upload) — integra tasks 1+2+4
7. Task 6 (Landing page) — marketing
8. Task 7 (Mercado Pago) — monetização
```

---

## Critérios de Aceite Globais

- [ ] Nenhum dado existente é perdido (1.572 transações preservadas)
- [ ] Backup automatizado funciona (local + cloud)
- [ ] Zero referências hardcoded a "Victor", "Larissa", ou dados pessoais no código
- [ ] Todos os endpoints filtram por `tenant_id` no nível da query (não em memória)
- [ ] Upload de PDF funciona end-to-end (PDF → preview → confirmar → dashboard atualiza)
- [ ] Cartões cadastrados determinam tipo (individual/shared) das transações
- [ ] Landing page acessível sem login
- [ ] Plano Free funciona sem cartão de crédito
- [ ] Testes passam para cada task
- [ ] Nenhum arquivo morto ou código duplicado permanece no repositório
