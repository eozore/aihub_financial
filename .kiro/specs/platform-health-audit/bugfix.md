# Documento de Requisitos de Bugfix — Platform Health Audit

## Introdução

A plataforma finance-pilot é uma aplicação de finanças pessoais para indivíduos e casais, implantada no GCP (Cloud Run, BigQuery, Firestore, GCS). Atualmente suporta apenas faturas CSV do Nubank. Uma auditoria completa revelou múltiplos bugs críticos que comprometem o funcionamento em produção (modo cloud), a manutenibilidade do código e a integridade dos dados financeiros. Este documento mapeia todos os defeitos encontrados, o comportamento esperado e os comportamentos que devem ser preservados — em especial a regra customizada de classificação de compras no cartão (`classification_service.py`).

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN o sistema opera em modo cloud (BigQuery) THEN o código referencia a tabela `transactions_gold` (variável `TABLE_GOLD` em `processor.py`) mas o Terraform cria a tabela com o nome `finance_gold` em `infra/main.tf`, causando falha em todas as escritas e leituras no BigQuery

1.2 WHEN o arquivo `main.py` é executado THEN ele contém ~3600 linhas com duplicações massivas de funções e classes que já existem em módulos dedicados (`helpers.py`, `auth.py`, `models.py`, `upload_validation.py`), incluindo: `TenantContext`, `_normalize_owner()`, `_parse_br_money()`, `_parse_br_percent()`, `_parse_month_ref()`, `_parse_ddmmyyyy_to_iso()`, `_parse_signed_amount()`, `_category_for_current_account()`, `_sanitize_tenant_id()`, `_extract_tenant_from_claims()`, `TransactionUpdate`, `TransactionCreate`, `PlanUpdate`, `WorkspaceCreate`, `WorkspaceUpdate`, `WorkspaceInviteCreate`, `NetWorthRowUpdate`, `_utc_now_iso()`, `_normalize_plan()`, `_plan_limits()`, `_normalize_email()`

1.3 WHEN o desenvolvedor procura a lógica de classificação THEN encontra `classifier.py` que é código morto/duplicado — contém a mesma lógica de `classification_service.py` mas nunca é importado por nenhum módulo ativo

1.4 WHEN o `processor.py` é inicializado THEN ele importa e carrega o modelo ML via `type_model.py` (`self.type_model = load_model()`), mas `predict_types()` nunca é chamado e o arquivo do modelo (`modelo_tipo_cartao.joblib`) não existe nos caminhos esperados

1.5 WHEN as dependências são instaladas via `requirements.txt` THEN `google-generativeai` e `scikit-learn` são instalados desnecessariamente — `google-generativeai` nunca é importado e `scikit-learn` só é usado pelo `type_model.py` que carrega um modelo inexistente e nunca é chamado

1.6 WHEN o desenvolvedor busca a camada de abstração de dados THEN encontra `repository.py` com implementações completas (`SQLiteTransactionRepository`, `MockTransactionRepository`) que nunca são usadas — `main.py` faz queries inline diretamente no SQLite/BigQuery/Firestore

1.7 WHEN um arquivo CSV de fatura é processado pelo `processor.py` THEN as transações individuais são agrupadas por merchant+category+owner+type e os valores são somados (agregação), perdendo os registros individuais na tabela gold

1.8 WHEN o `processor.py` classifica uma transação THEN o valor normalizado do merchant (`merchant_norm`) é computado pelo `ClassificationService` mas é armazenado apenas como campo intermediário — o campo `merchant_clean` na tabela gold recebe apenas `merchant_raw.strip()` e o schema da tabela gold não possui coluna `merchant_norm`

1.9 WHEN a infraestrutura é provisionada via Terraform THEN o bucket `${var.project_id}-internal` é criado mas nenhum código o referencia, gerando custo desnecessário no GCP

1.10 WHEN a infraestrutura é provisionada via Terraform THEN o bucket `${var.project_id}-firestore-backups` é criado mas nenhum job de backup (Cloud Scheduler ou similar) é configurado para executar backups do Firestore

1.11 WHEN o desenvolvedor examina o código THEN encontra `download_findata.py` que referencia `gspread` e `oauth2client` (não presentes no `requirements.txt`) e caminhos inexistentes (`data-transactions/acesso.json`) — é código legado morto

1.12 WHEN o desenvolvedor examina os scripts de inicialização THEN encontra `init_db.py` e `init_sqlite.py` redundantes com a função `init_db()` já existente em `database.py`, criando múltiplos caminhos conflitantes de inicialização

1.13 WHEN os testes são executados pelo test runner THEN `test_health.py` está na raiz do backend em vez de estar no diretório `tests/`, podendo não ser detectado pela configuração padrão do pytest

1.14 WHEN o repositório é clonado THEN o arquivo `frontend/.env.local` contém credenciais Firebase hardcoded commitadas no repositório

1.15 WHEN o endpoint `get_dashboard_summary()` é chamado com filtro `tx_type="Individual"` THEN a query de settlement tenta filtrar por `type='Shared'` enquanto o `base_where` já contém `type='Individual'`, criando uma cláusula WHERE contraditória (`type = 'Individual' AND type = 'Shared'`) que retorna 0 linhas

### Expected Behavior (Correct)

2.1 WHEN o sistema opera em modo cloud (BigQuery) THEN o nome da tabela gold no código (`TABLE_GOLD` em `processor.py`) SHALL corresponder exatamente ao `table_id` definido no Terraform (`finance_gold`), ou o Terraform SHALL ser atualizado para criar a tabela como `transactions_gold` — garantindo consistência entre infraestrutura e aplicação

2.2 WHEN o `main.py` é executado THEN ele SHALL importar e utilizar as funções e classes dos módulos dedicados (`helpers.py`, `auth.py`, `models.py`, `upload_validation.py`) em vez de conter cópias duplicadas, eliminando a divergência comportamental entre cópias

2.3 WHEN o desenvolvedor examina o código THEN `classifier.py` SHALL ser removido do projeto, pois `classification_service.py` é o módulo ativo e único responsável pela classificação

2.4 WHEN o `processor.py` é inicializado THEN ele SHALL não importar nem carregar o modelo ML (`type_model.py`) enquanto o modelo não existir e `predict_types()` não for integrado ao fluxo de processamento

2.5 WHEN as dependências são instaladas via `requirements.txt` THEN `google-generativeai` e `scikit-learn` SHALL ser removidos das dependências de produção, reduzindo o tamanho da imagem Docker e a superfície de ataque

2.6 WHEN o desenvolvedor busca a camada de abstração de dados THEN `repository.py` SHALL ser integrado ao `main.py` como camada de acesso a dados, ou SHALL ser removido se a integração não for viável neste momento — eliminando código morto que gera confusão

2.7 WHEN um arquivo CSV de fatura é processado pelo `processor.py` THEN cada transação individual SHALL ser preservada como registro separado na tabela gold, sem agregação por merchant+category+owner+type, permitindo que o usuário visualize cada transação individualmente

2.8 WHEN o `processor.py` classifica uma transação THEN o valor normalizado do merchant (`merchant_norm`) SHALL ser utilizado como `merchant_clean` na tabela gold, ou a tabela gold SHALL incluir uma coluna `merchant_norm` para armazenar o valor normalizado

2.9 WHEN a infraestrutura é provisionada via Terraform THEN o bucket `${var.project_id}-internal` SHALL ser removido do Terraform se não houver uso planejado, evitando custo desnecessário

2.10 WHEN a infraestrutura é provisionada via Terraform THEN o bucket de backups do Firestore SHALL ter um job de backup configurado (Cloud Scheduler + export), ou SHALL ser removido se backups automáticos não forem necessários neste momento

2.11 WHEN o desenvolvedor examina o código THEN `download_findata.py` SHALL ser removido do projeto por ser código legado morto com dependências inexistentes

2.12 WHEN o desenvolvedor examina os scripts de inicialização THEN `init_db.py` e `init_sqlite.py` SHALL ser removidos, mantendo apenas `database.py` como ponto único de inicialização do banco de dados

2.13 WHEN os testes são executados pelo test runner THEN `test_health.py` SHALL estar dentro do diretório `tests/` para ser detectado pela configuração padrão do pytest

2.14 WHEN o repositório é clonado THEN o arquivo `frontend/.env.local` SHALL estar listado no `.gitignore` e as credenciais Firebase SHALL ser fornecidas via variáveis de ambiente ou arquivo `.env.local.example` com placeholders

2.15 WHEN o endpoint `get_dashboard_summary()` é chamado com filtro `tx_type="Individual"` THEN a query de settlement SHALL respeitar o filtro de tipo ativo, retornando dados de settlement apenas para transações do tipo filtrado, sem criar cláusulas WHERE contraditórias

### Unchanged Behavior (Regression Prevention)

3.1 WHEN transações são classificadas pelo `classification_service.py` THEN o sistema SHALL CONTINUE TO aplicar as regras customizadas de classificação de compras no cartão (keywords de categoria, regras de tipo Shared/Individual, merchants forçados, categorias always-shared/always-individual, lookup de histórico e fallback por keywords) exatamente como implementadas atualmente

3.2 WHEN o sistema opera em modo SQLite local (`USE_SQLITE=true`) THEN o sistema SHALL CONTINUE TO funcionar corretamente para desenvolvimento local, incluindo CRUD de transações, upload de faturas, dashboard e patrimônio

3.3 WHEN o frontend faz requisições à API THEN o sistema SHALL CONTINUE TO validar tokens Firebase, resolver tenant/workspace e aplicar rate limiting conforme implementado atualmente

3.4 WHEN um arquivo CSV do Nubank é enviado via upload THEN o sistema SHALL CONTINUE TO validar o arquivo (tamanho, extensão, MIME type), detectar colunas automaticamente (date/Data, amount/Valor, title/Observações) e processar as transações

3.5 WHEN o usuário acessa o dashboard THEN o sistema SHALL CONTINUE TO retornar resumos de gastos por categoria, owner e tipo (Shared/Individual), incluindo dados de tendência e settlement entre owners

3.6 WHEN o sistema gerencia workspaces THEN o sistema SHALL CONTINUE TO suportar criação, ativação, convites e gerenciamento de membros de workspaces conforme implementado atualmente

3.7 WHEN o sistema gerencia patrimônio (net worth) THEN o sistema SHALL CONTINUE TO suportar upload de CSV de patrimônio, visualização mensal, validação cruzada com conta corrente e edição manual de snapshots

3.8 WHEN o `normalization.py` normaliza nomes de merchants THEN o sistema SHALL CONTINUE TO aplicar as regras de limpeza técnica (regex), substituições do `merchant_map.json` e mapeamentos inteligentes conforme implementado atualmente

3.9 WHEN o `category_mapping.py` mapeia categorias THEN o sistema SHALL CONTINUE TO utilizar o `category_map.json` para mapear merchants normalizados para categorias, tratando valores vazios e ambíguos como `None`
