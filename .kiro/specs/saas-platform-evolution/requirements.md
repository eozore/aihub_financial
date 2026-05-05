# Documento de Requisitos — Finance Pilot → SaaS

## Introdução

Este documento especifica os requisitos para transformar o Finance Pilot de uma ferramenta pessoal de finanças em uma plataforma SaaS vendável. A plataforma permite que usuários façam upload de PDFs de faturas bancárias, extraiam transações automaticamente via LLM, classifiquem despesas e gerenciem finanças compartilhadas — tudo com isolamento multi-tenant e monetização via assinaturas.

## Glossário

- **Sistema**: A plataforma Finance Pilot SaaS como um todo (backend + frontend + infraestrutura)
- **Serviço_de_Extração**: Módulo backend responsável por extrair transações de PDFs usando Gemini Flash 2.5
- **Serviço_de_Classificação**: Módulo backend responsável por categorizar transações automaticamente
- **Serviço_de_Billing**: Módulo backend responsável pela integração com Mercado Pago para assinaturas
- **Workspace**: Espaço isolado de dados pertencente a um ou mais usuários (equivalente a tenant)
- **Cartão**: Registro dos últimos 4 dígitos de um cartão de crédito/débito, associado a um owner e tipo (individual/shared)
- **Owner**: Membro de um workspace que possui transações associadas
- **Tenant_ID**: Identificador único do workspace usado para isolamento de dados em todas as queries
- **Landing_Page**: Página pública de marketing acessível sem autenticação
- **Preview**: Tela intermediária que exibe transações extraídas do PDF antes da confirmação de importação
- **Regra_de_Categoria**: Mapeamento configurável por workspace entre merchant e categoria

## Requisitos

### Requisito 1: Isolamento de Dados por Tenant no Firestore

**User Story:** Como operador da plataforma, eu quero que todas as queries ao Firestore filtrem por tenant_id no nível da query, para que dados de um workspace nunca sejam carregados em memória junto com dados de outro workspace.

#### Critérios de Aceite

1. THE Sistema SHALL incluir filtro `tenant_id == <tenant_id_do_request>` como primeira cláusula em todas as queries ao Firestore
2. WHEN uma query ao Firestore é executada sem filtro de tenant_id, THE Sistema SHALL rejeitar a operação e retornar erro HTTP 400
3. THE Sistema SHALL aplicar Firestore Security Rules que impeçam leitura de documentos onde `resource.data.tenant_id != request.auth.token.tenant_id`
4. WHEN o endpoint `sync-firestore-to-bigquery` é chamado, THE Sistema SHALL sincronizar apenas documentos pertencentes ao tenant_id do request
5. THE Sistema SHALL preservar todas as 1.572 transações existentes durante a aplicação do fix de segurança

### Requisito 2: Remoção de Lógica Pessoal Hardcoded

**User Story:** Como desenvolvedor da plataforma, eu quero que todo código específico de usuários pessoais (Victor/Larissa) seja removido, para que a plataforma funcione genericamente para qualquer usuário.

#### Critérios de Aceite

1. THE Sistema SHALL obter a lista de owners dinamicamente a partir dos membros do workspace ativo
2. THE Sistema SHALL utilizar o tipo do cartão cadastrado (`card_type`) para determinar se uma transação é individual ou compartilhada
3. WHEN o endpoint `GET /owners` é chamado, THE Sistema SHALL retornar os membros do workspace do tenant_id atual (não uma lista estática de configuração)
4. THE Sistema SHALL conter zero referências hardcoded aos nomes "Victor", "Larissa" ou quaisquer dados pessoais no código-fonte
5. THE Sistema SHALL remover as variáveis de configuração `OWNERS`, `LEGACY_SHARED_EMAILS`, `AUTO_JOIN_LEGACY_WORKSPACE` e `DEFAULT_LEGACY_MEMBER_LIMIT` do módulo `config.py`
6. THE Serviço_de_Classificação SHALL remover as constantes `VICTOR_INDIVIDUAL_KEYWORDS`, `FORCE_SHARED_MERCHANTS`, `ALWAYS_SHARED_CATEGORIES` e `ALWAYS_INDIVIDUAL_CATEGORIES`
7. THE Sistema SHALL manter os dados legados intactos (transações existentes preservam seus valores de owner e type originais)

### Requisito 3: CRUD de Cartões

**User Story:** Como usuário da plataforma, eu quero cadastrar meus cartões (últimos 4 dígitos) e definir se cada um é individual ou compartilhado, para que o sistema classifique automaticamente o tipo das transações.

#### Critérios de Aceite

1. WHEN um request `POST /cards` é recebido com dados válidos, THE Sistema SHALL criar um registro de cartão associado ao workspace_id do tenant atual
2. THE Sistema SHALL validar que o campo `last4` contém exatamente 4 dígitos numéricos
3. WHEN um cartão com o mesmo `last4` já existe no workspace, THE Sistema SHALL rejeitar a criação e retornar erro HTTP 409 (conflito)
4. WHEN um request `GET /cards` é recebido, THE Sistema SHALL retornar apenas cartões pertencentes ao workspace_id do tenant atual
5. WHEN um request `PUT /cards/{id}` é recebido, THE Sistema SHALL atualizar o cartão somente se ele pertencer ao workspace_id do tenant atual
6. WHEN um request `DELETE /cards/{id}` é recebido, THE Sistema SHALL remover o cartão somente se ele pertencer ao workspace_id do tenant atual
7. THE Sistema SHALL aceitar apenas os valores `individual` ou `shared` para o campo `card_type`
8. THE Sistema SHALL armazenar para cada cartão: id, workspace_id, owner, last4, label, card_type, bank, is_active, created_at, updated_at

### Requisito 4: Sistema de Categorias Genéricas

**User Story:** Como usuário da plataforma, eu quero que transações sejam classificadas em categorias genéricas padronizadas, para que a organização financeira funcione sem configuração manual inicial.

#### Critérios de Aceite

1. THE Serviço_de_Classificação SHALL fornecer um conjunto de categorias padrão aplicáveis a qualquer workspace (Alimentação, Delivery, Mercado, Transporte, Moradia, Saúde, Educação, Lazer, Streaming, Compras, Assinaturas, Viagem, Pets, Impostos/Taxas, Transferência, Outros)
2. WHEN uma regra customizada existe na tabela `workspace_category_rules` para o merchant da transação, THE Serviço_de_Classificação SHALL aplicar a regra do workspace com prioridade sobre as categorias padrão
3. WHEN nenhuma regra (workspace ou padrão) corresponde ao merchant, THE Serviço_de_Classificação SHALL classificar a transação como "Outros" e marcar `needs_review = true`
4. THE Sistema SHALL preservar as categorias existentes nas 1.572 transações legadas sem reclassificação automática
5. THE Sistema SHALL permitir que o usuário crie, edite e remova regras de categoria customizadas para seu workspace via endpoints REST
6. THE Serviço_de_Classificação SHALL aplicar a classificação na seguinte ordem de prioridade: (1) regra do workspace por match exato de merchant_clean, (2) keywords genéricos das categorias padrão por match parcial, (3) fallback para "Outros"

### Requisito 5: Serviço de Extração de PDF via Gemini Flash 2.5

**User Story:** Como usuário da plataforma, eu quero fazer upload de PDFs de faturas bancárias e ter as transações extraídas automaticamente, para que eu não precise inserir dados manualmente.

#### Critérios de Aceite

1. WHEN um PDF válido de fatura é enviado, THE Serviço_de_Extração SHALL extrair todas as transações e retornar um objeto estruturado contendo: tipo de extrato, banco, nome do titular, data de vencimento, período, valor total e lista de transações
2. THE Serviço_de_Extração SHALL extrair para cada transação: data, últimos 4 dígitos do cartão, descrição, valor, flag de estorno, flag de parcelamento, parcela atual/total e moeda original (para internacionais)
3. WHEN o mesmo PDF (identificado por hash SHA-256) é enviado novamente, THE Serviço_de_Extração SHALL retornar o resultado do cache sem chamar a API do Gemini
4. WHEN a chamada ao Gemini falha, THE Serviço_de_Extração SHALL realizar até 3 tentativas com exponential backoff antes de acionar o fallback
5. IF todas as tentativas ao Gemini falham, THEN THE Serviço_de_Extração SHALL utilizar pdfplumber com regex como mecanismo de fallback para faturas Nubank
6. THE Serviço_de_Extração SHALL validar o JSON retornado pelo Gemini contra um schema Pydantic e rejeitar respostas malformadas
7. WHEN o PDF contém seções de múltiplos titulares (cartões adicionais), THE Serviço_de_Extração SHALL separar as transações por seção/owner

### Requisito 6: Novo Fluxo de Upload (PDF → Preview → Confirmar)

**User Story:** Como usuário da plataforma, eu quero fazer upload de um PDF via drag & drop e revisar as transações extraídas antes de confirmar a importação, para que eu tenha controle sobre o que é salvo.

#### Critérios de Aceite

1. WHEN um arquivo PDF é enviado via `POST /upload`, THE Sistema SHALL processar a extração e retornar um preview das transações sem salvar no banco de dados
2. WHEN o usuário confirma a importação via `POST /upload/confirm`, THE Sistema SHALL cruzar o `card_last4` de cada transação com os cartões cadastrados no workspace para determinar o `card_type`
3. WHEN uma transação possui `card_last4` que não corresponde a nenhum cartão cadastrado, THE Sistema SHALL marcar a transação com flag `needs_review = true` e destacá-la visualmente no preview
4. THE Sistema SHALL aceitar arquivos nos formatos PDF e CSV no endpoint de upload
5. THE Sistema SHALL detectar automaticamente o tipo de arquivo (fatura de cartão ou extrato de conta corrente) a partir do conteúdo extraído
6. WHEN a importação é confirmada, THE Sistema SHALL registrar o upload na tabela `upload_history` com: filename, file_hash, statement_type, bank, período, quantidade de transações e status
7. THE Sistema SHALL extrair automaticamente o owner e o mês de referência a partir do conteúdo do PDF (sem input manual do usuário)
8. WHEN a importação é confirmada, THE Sistema SHALL classificar cada transação usando o Serviço_de_Classificação e salvar no banco com as colunas: card_last4, card_type, is_refund, transaction_source='pdf_extraction', upload_id e needs_review

### Requisito 7: Landing Page Pública

**User Story:** Como visitante não autenticado, eu quero acessar uma página de marketing que explique o produto e seus planos, para que eu possa decidir se quero me cadastrar.

#### Critérios de Aceite

1. THE Landing_Page SHALL ser acessível sem autenticação na rota raiz pública do frontend
2. THE Landing_Page SHALL conter as seções: Hero com proposta de valor, Como Funciona (3 passos), Bancos Suportados, Screenshots do produto, Planos e Preços (Free/Pro/Família), FAQ e CTA de cadastro
3. WHEN um usuário autenticado acessa a rota da Landing_Page, THE Sistema SHALL redirecionar automaticamente para o dashboard
4. THE Landing_Page SHALL incluir meta tags de SEO e Open Graph para compartilhamento em redes sociais
5. THE Landing_Page SHALL ser responsiva com abordagem mobile-first seguindo os princípios de design do guia (hierarquia visual, CRAP, zona do polegar)
6. THE Landing_Page SHALL exibir que o plano Free funciona sem necessidade de cartão de crédito

### Requisito 8: Integração de Billing com Mercado Pago

**User Story:** Como operador da plataforma, eu quero monetizar o produto com assinaturas recorrentes via Mercado Pago, para que usuários possam fazer upgrade de plano e a plataforma gere receita.

#### Critérios de Aceite

1. WHEN o usuário solicita assinatura via `POST /billing/create-subscription`, THE Serviço_de_Billing SHALL criar um `preapproval` no Mercado Pago e retornar a URL de checkout (`init_point`)
2. WHEN o Mercado Pago envia uma notificação IPN via `POST /billing/webhook`, THE Serviço_de_Billing SHALL atualizar o status da assinatura e o `plan_type` do workspace
3. WHEN o endpoint `GET /billing/status` é chamado, THE Serviço_de_Billing SHALL retornar o status atual da assinatura do workspace (active, paused, cancelled, pending)
4. WHEN o usuário cancela via `POST /billing/cancel`, THE Serviço_de_Billing SHALL cancelar o `preapproval` no Mercado Pago e atualizar o status local para 'cancelled'
5. THE Sistema SHALL aplicar limites de plano antes de cada operação restrita: uploads/mês (Free=2, Pro=ilimitado, Família=ilimitado), histórico (Free=3 meses, Pro=12 meses, Família=ilimitado), membros (Free=1, Pro=1, Família=4), cartões (Free=2, Pro=5, Família=10)
6. THE Sistema SHALL permitir que o plano Free funcione completamente sem exigir dados de cartão de crédito
7. THE Serviço_de_Billing SHALL armazenar para cada assinatura: id, workspace_id, mp_preapproval_id, plan_type, status, trial_ends_at, current_period_start, current_period_end, created_at, updated_at
8. IF o webhook do Mercado Pago falha na entrega, THEN THE Serviço_de_Billing SHALL aceitar reenvios idempotentes sem duplicar atualizações de status

### Requisito 9: Migração de Dados e Integridade

**User Story:** Como operador da plataforma, eu quero que a migração para o novo modelo de dados preserve todos os dados existentes e seja reversível, para que nenhuma informação financeira seja perdida.

#### Critérios de Aceite

1. THE Sistema SHALL adicionar as colunas `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id` e `needs_review` à tabela `transactions_gold` sem alterar dados existentes
2. THE Sistema SHALL preencher `transaction_source = 'legacy_csv'` e `card_last4 = NULL` para todas as transações existentes
3. THE Sistema SHALL criar as tabelas `cards`, `workspace_category_rules`, `subscriptions` e `upload_history` sem deletar tabelas existentes
4. WHEN uma migração é aplicada, THE Sistema SHALL fornecer um script de rollback correspondente que reverta as alterações de schema
5. THE Sistema SHALL manter o backup automatizado funcionando (local via script + cloud via GCS) após todas as migrações
6. THE Sistema SHALL preservar integralmente as 1.572 transações existentes (Victor: 1.112, Larissa: 460) com seus valores originais inalterados

### Requisito 10: Limpeza de Código e Arquivos

**User Story:** Como desenvolvedor da plataforma, eu quero que arquivos mortos e código duplicado sejam removidos, para que o repositório fique limpo e manutenível.

#### Critérios de Aceite

1. THE Sistema SHALL remover os arquivos identificados como stale: `finance-pilot/finance.db`, backups legados substituídos pelo sistema automatizado, e `type_model.py` (modelo ML não utilizado)
2. THE Sistema SHALL remover mapeamentos pessoais do `merchant_map.json`, mantendo apenas mapeamentos universais (Amazon, Netflix, Uber, etc.)
3. THE Sistema SHALL substituir o `category_map.json` (496 entradas pessoais) pelo sistema de categorias padrão + regras por workspace
4. THE Sistema SHALL remover referências ao projeto `portfolio` do script `deploy_financial_platform.sh`
5. WHEN todas as tasks da Fase 1 estiverem completas, THE Sistema SHALL conter zero arquivos mortos ou código duplicado no repositório
