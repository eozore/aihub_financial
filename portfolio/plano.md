# Plano da Plataforma (GitHub + GCP)

## 1) Objetivo do produto

Evoluir o site/portfólio estático para uma plataforma com:

1. Gestão e escrita de artigos com IA Generativa.
2. Publicação de ferramentas de ML/IA para usuários autenticados (login e senha).
3. Operação confiável, segura e com custo controlado em GCP.

## 2) Modelo de trabalho (dono do produto + dev especialista)

### Dono do produto (você)
- Define visão, prioridades e backlog.
- Aprova roadmap, escopo de release e critérios de sucesso.
- Decide tom editorial, posicionamento e estratégia de aquisição.
- Valida entregas em staging/produção.

### Desenvolvedor especialista
- Define arquitetura técnica e implementa.
- Cria infra, CI/CD, observabilidade, segurança e deploy.
- Converte requisitos em entregas com prazo.
- Propõe melhorias com base em métricas de uso e custo.

### Cadência recomendada
- Planejamento semanal (30-45 min).
- Revisão quinzenal de roadmap.
- Release semanal (pequeno e incremental).

## 3) Arquitetura alvo (GCP)

### Domínios
- `www.seudominio.com`: site + blog público.
- `app.seudominio.com`: área logada com ferramentas.
- `api.seudominio.com`: backend de serviços.

### Camadas
1. **Frontend público (site/blog)**
   - Gerado estaticamente (ex: Astro/Next static export).
   - Hospedado em Cloud Storage + Cloud CDN (ou Cloud Run se preferir unificação).
2. **Frontend autenticado (tools)**
   - App web em Cloud Run.
3. **APIs**
   - Serviços em Cloud Run (REST/JSON).
4. **Orquestração de conteúdo IA**
   - Cloud Run Jobs + Cloud Scheduler + Pub/Sub.
5. **Dados**
   - Cloud SQL (PostgreSQL) para usuários, permissões, histórico e billing interno.
   - Cloud Storage para assets (imagens dos artigos, exports, datasets leves).
6. **IA Generativa**
   - Vertex AI (Gemini) para planejamento, rascunho, revisão e metadados SEO.

## 4) Serviços GCP por responsabilidade

- **Cloud Run**: APIs, app logado, workers de IA.
- **Cloud Run Jobs**: tarefas assíncronas de geração/revisão/publicação.
- **Vertex AI**: inferência e geração de conteúdo.
- **Cloud SQL (Postgres)**: dados transacionais.
- **Cloud Storage**: arquivos estáticos e mídia.
- **Secret Manager**: chaves/tokens (GitHub token, API keys).
- **Cloud Logging + Monitoring + Error Reporting**: observabilidade.
- **Cloud Build ou GitHub Actions**: pipelines de deploy.
- **IAM + Workload Identity Federation**: autenticação segura GitHub -> GCP sem chave estática.
- **Cloud Armor (opcional na fase inicial, recomendado depois)**: proteção de borda.

## 5) Estratégia de autenticação e autorização

### Autenticação
- Identity Platform (ou Firebase Auth) com email/senha.
- JWT validado no backend (Cloud Run API).

### Autorização
- RBAC simples:
  - `admin` (você),
  - `editor`,
  - `user_pro` (acesso a tools),
  - `user_free` (acesso limitado).

### Segurança mínima obrigatória
- Senhas nunca no banco (somente via provedor de autenticação).
- Segredos somente em Secret Manager.
- Princípio do menor privilégio em IAM.
- Logs de acesso e auditoria ligados.

## 6) Fluxo de artigos com IA (MVP)

1. `brief` do artigo (tema, persona, nível técnico).
2. Geração de outline com Vertex AI.
3. Geração de rascunho por seções.
4. Revisão automática (clareza, consistência, SEO técnico).
5. Aprovação humana (você).
6. Publicação:
   - gera arquivo Markdown/HTML,
   - abre PR no GitHub automaticamente,
   - deploy após merge.
7. Pós-publicação:
   - gera resumo para YouTube/LinkedIn.

## 7) Repositório e organização de código (GitHub)

### Estrutura sugerida
- `apps/site` (site/blog público)
- `apps/tools-web` (frontend autenticado)
- `services/api` (APIs)
- `services/content-pipeline` (jobs IA)
- `infra/terraform` (infra declarativa)
- `docs/` (arquitetura, runbooks, ADRs)

### Branching
- `main` (produção)
- `develop` (integração, opcional)
- feature branches por card.

### Pull Request padrão
- checklist de segurança,
- checklist de observabilidade,
- evidência de teste,
- impacto em custo.

## 8) CI/CD (GitHub + GCP CLI)

### Pipeline mínimo por PR
1. lint + testes.
2. validação de links e HTML.
3. build de imagens/container.
4. deploy em ambiente `staging`.

### Pipeline em `main`
1. promoção para `prod`.
2. migração de banco versionada.
3. smoke test pós-deploy.

### Autenticação CI -> GCP
- Workload Identity Federation (evitar service account key em arquivo).

## 9) Ambientes

- `dev`: experimentação rápida.
- `staging`: homologação com dados de teste.
- `prod`: ambiente final.

Cada ambiente com projeto GCP separado (ou pelo menos recursos separados por prefixo).

## 10) Roadmap por fases

### Fase 0 (1-2 semanas): Fundação
- Padronizar stack e estrutura de repositório.
- Setup de projetos GCP (`dev/staging/prod`).
- CI/CD inicial + autenticação GitHub -> GCP.
- Observabilidade base.

**Saída da fase**: deploy automatizado funcional para staging.

### Fase 1 (2-4 semanas): Site e blog profissionalizados
- Migrar blog para conteúdo estruturado (Markdown + template único).
- SEO técnico completo (sitemap, robots, OG, canonical, schema).
- CDN + otimização de imagens.

**Saída da fase**: site rápido, indexável e com pipeline de publicação.

### Fase 2 (3-5 semanas): Pipeline de artigos com IA (MVP)
- Serviço de geração assistida de artigo com Vertex AI.
- Workflow de aprovação humana.
- PR automático no GitHub para publicação.

**Saída da fase**: artigo gerado com IA + revisão + deploy.

### Fase 3 (4-6 semanas): Área logada e tools IA/ML
- Login/senha.
- Gestão de usuários e planos.
- 1-2 tools iniciais com valor claro (ex: scoring demo, previsão, copiloto de análise).

**Saída da fase**: usuários autenticados usando tools em produção.

### Fase 4 (contínua): Escala e produto
- Métricas de uso, conversão e retenção.
- Billing/regras de limite.
- Hardening de segurança e custo.

## 11) Observabilidade e métricas de sucesso

### Produto
- visitantes únicos/mês,
- CTR blog -> YouTube,
- conversão visitante -> usuário cadastrado,
- MAU de tools.

### Plataforma
- disponibilidade API (SLO >= 99.5% no início),
- p95 de latência por endpoint,
- taxa de erro 5xx,
- custo por usuário ativo.

## 12) Custo e governança

- Definir orçamento mensal por ambiente.
- Alertas de billing no GCP (50/80/100%).
- Limites por serviço para evitar explosão de custo.
- Revisão quinzenal de custo por feature.

## 13) Backlog inicial (próximos 14 dias)

1. Escolher stack final do frontend (`Astro` recomendado para blog).
2. Criar estrutura monorepo e convenções.
3. Provisionar ambientes GCP + IAM mínimo.
4. Implementar CI com Workload Identity Federation.
5. Publicar site em staging via GCP.
6. Definir modelo de dados inicial (usuários, artigos, jobs, tool_usage).
7. Criar primeiro serviço de geração de outline com Vertex AI.

## 14) Definição de pronto (Definition of Done)

Uma entrega só é considerada pronta se tiver:

- código revisado por PR,
- testes mínimos e smoke test,
- logs e métricas instrumentados,
- documentação curta de operação,
- impacto de custo estimado,
- deploy em staging validado.
