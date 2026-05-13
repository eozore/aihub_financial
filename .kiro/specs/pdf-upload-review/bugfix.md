# Bugfix Requirements Document

## Introduction

O processo de upload de PDFs de extrato bancário (cartão de crédito e conta corrente Nubank) apresenta múltiplos problemas que comprometem a extração, classificação e persistência correta dos dados de transações. Os bugs afetam desde a extração de texto dos PDFs via fallback pdfplumber, passando pela classificação de estabelecimentos digitais (NuTag, iFood, aplicativos), até a persistência incorreta ou incompleta dos dados no SQLite, BigQuery e Firestore.

Os dois tipos de extrato suportados são:
- **Extrato de cartão de crédito** (`NU_45499351_01ABR2026_30ABR2026.pdf`) — fatura Nubank com seções por titular
- **Extrato de conta corrente** (`Nubank_2026-05-04.pdf`) — movimentações da conta corrente Nubank

---

## Bug Analysis

### Current Behavior (Defect)

**1. Extração via fallback pdfplumber — Cartão de Crédito**

1.1 QUANDO o PDF de fatura de cartão de crédito Nubank é processado pelo fallback pdfplumber E o texto extraído contém linhas de transação no formato `DD MMM   DESCRIÇÃO   VALOR`, ENTÃO o sistema falha em extrair transações cujas descrições contêm múltiplos espaços ou caracteres especiais, retornando lista vazia ou incompleta

1.2 QUANDO o PDF de fatura Nubank contém seções de titulares adicionais no formato `NOME - final XXXX`, ENTÃO o sistema falha em identificar corretamente o titular principal (sem sufixo "- final XXXX"), resultando em seção única sem separação por titular

1.3 QUANDO o PDF de fatura Nubank é processado pelo fallback pdfplumber, ENTÃO o sistema retorna `statement_type = "credit_card"` hardcoded, sem detectar dinamicamente o tipo de extrato, causando classificação incorreta para extratos de conta corrente processados pelo mesmo fallback

1.4 QUANDO o fallback pdfplumber extrai o nome do titular, ENTÃO o sistema usa regex que busca padrão `"Olá, Nome"` ou linhas capitalizadas, mas o PDF real da Nubank não segue esse padrão exato, resultando em `holder_name = "Titular"` (valor padrão) em vez do nome real

1.5 QUANDO o fallback pdfplumber extrai o período do extrato, ENTÃO o sistema retorna `("2026-01-01", "2026-01-31")` como fallback hardcoded quando o padrão de período não é encontrado, em vez de derivar o período a partir das datas das transações extraídas

**2. Extração via fallback pdfplumber — Conta Corrente**

1.6 QUANDO um PDF de extrato de conta corrente Nubank (`Nubank_2026-05-04.pdf`) é enviado para upload, ENTÃO o sistema não possui lógica de extração específica para conta corrente no fallback pdfplumber, retornando `statement_type = "credit_card"` e falhando em extrair movimentações de débito/crédito no formato da conta corrente

1.7 QUANDO o extrato de conta corrente contém movimentações com valores negativos (débitos) e positivos (créditos/PIX recebidos), ENTÃO o sistema ignora valores negativos no `_process_chunk` do `processor.py` (`if amount < 0: continue`), descartando incorretamente transações de débito legítimas

**3. Classificação de estabelecimentos digitais e pedágios**

1.8 QUANDO uma transação de cartão de crédito tem descrição `"NuTag"` ou `"Sem Parar"` ou `"ConnectCar"`, ENTÃO o sistema classifica como `"Outros"` com `needs_review=True` usando o `ClassificationService` de `categories.py`, pois as palavras-chave de pedágio (`"nutag"`, `"sem parar"`, `"conectcar"`) existem apenas no `classification_service.py` (módulo legado) e não no `DEFAULT_CATEGORIES` do `categories.py` (módulo ativo no fluxo de upload)

1.9 QUANDO uma transação tem descrição `"IFD*"` ou `"Ifd*"` (prefixo iFood), ENTÃO o sistema classifica como `"Outros"` com `needs_review=True` usando o `ClassificationService` de `categories.py`, pois a keyword `"ifd*"` no `DEFAULT_CATEGORIES` usa wildcard que não é interpretado como regex na lógica de matching por substring

1.10 QUANDO uma transação tem descrição de aplicativo de streaming como `"Apple.Com/Bill"` ou `"Amazonprimebr"`, ENTÃO o sistema classifica como `"Outros"` com `needs_review=True` usando o `ClassificationService` de `categories.py`, pois essas keywords existem apenas no `CATEGORY_KEYWORDS` do `classification_service.py` legado, não no `DEFAULT_CATEGORIES` ativo

1.11 QUANDO uma transação tem descrição de compra online como `"Shopee"` ou `"Mercado Livre"`, ENTÃO o sistema classifica na categoria `"Compras"` usando `DEFAULT_CATEGORIES`, mas o `ClassificationService` de `categories.py` retorna `needs_review=False` mesmo para merchants que requerem revisão de tipo (individual vs. shared), pois a lógica de `card_type` não é aplicada na classificação

**4. Persistência de dados — SQLite e BigQuery**

1.12 QUANDO o endpoint `POST /upload/confirm` salva transações no SQLite, ENTÃO o sistema insere `card_type` duplicado nos campos `type` e `card_type` da tabela `transactions_gold`, mas o campo `type` deveria representar o tipo de transação (individual/shared) derivado do cartão registrado, não uma cópia do `card_type`

1.13 QUANDO o endpoint `POST /upload/confirm` salva transações no BigQuery (modo cloud), ENTÃO o sistema não insere os campos `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id` e `needs_review` no BigQuery, pois o payload enviado ao BigQuery não inclui esses campos adicionados pela migração 001

1.14 QUANDO o endpoint `POST /upload/confirm` registra o upload no `upload_history`, ENTÃO o sistema hardcoda `statement_type = "credit_card"` e `bank = None`, em vez de usar os valores reais extraídos do PDF (disponíveis no `ExtractedStatement` retornado pelo `ExtractionService`)

1.15 QUANDO o `ExtractionService` armazena o resultado em cache em memória (`self._cache`), ENTÃO o cache não é compartilhado entre requisições em ambientes com múltiplos workers (Cloud Run), fazendo com que o mesmo PDF seja reprocessado pelo Gemini em cada instância, gerando custos desnecessários e inconsistências

**5. Fluxo de upload — validação e roteamento**

1.16 QUANDO o endpoint `POST /upload` recebe um PDF de conta corrente, ENTÃO o sistema roteia para o `ExtractionService` que retorna `statement_type = "current_account"`, mas o endpoint de confirmação `POST /upload/confirm` não possui lógica diferenciada para persistir movimentações de conta corrente na tabela `current_account_movements`, salvando tudo em `transactions_gold` independentemente do tipo

1.17 QUANDO o `processor.py` processa um arquivo CSV de conta corrente, ENTÃO o campo `type` das transações é definido como `None` (`"type": None`) e nunca é preenchido com o `card_type` do cartão registrado, pois o comentário no código indica que isso "será feito pelo card_type lookup" mas a integração não foi implementada

---

### Expected Behavior (Correct)

**1. Extração via fallback pdfplumber — Cartão de Crédito**

2.1 QUANDO o PDF de fatura de cartão de crédito Nubank é processado pelo fallback pdfplumber, ENTÃO o sistema SHALL extrair todas as transações presentes no PDF, incluindo aquelas com descrições contendo múltiplos espaços, caracteres especiais e sufixos de parcelamento

2.2 QUANDO o PDF de fatura Nubank contém seções de titulares adicionais, ENTÃO o sistema SHALL identificar corretamente o titular principal e criar seções separadas por titular, associando cada transação ao seu respectivo titular e `card_last4`

2.3 QUANDO o fallback pdfplumber processa um PDF, ENTÃO o sistema SHALL detectar dinamicamente o `statement_type` com base no conteúdo do PDF (presença de "fatura", "cartão" para `credit_card`; presença de "conta corrente", "extrato" para `current_account`)

2.4 QUANDO o fallback pdfplumber extrai o nome do titular, ENTÃO o sistema SHALL retornar o nome real do titular conforme presente no PDF, usando múltiplos padrões de regex compatíveis com o layout real dos PDFs Nubank

2.5 QUANDO o fallback pdfplumber não encontra o padrão de período no texto, ENTÃO o sistema SHALL derivar `period_start` e `period_end` a partir das datas mínima e máxima das transações extraídas, em vez de retornar datas hardcoded

**2. Extração via fallback pdfplumber — Conta Corrente**

2.6 QUANDO um PDF de extrato de conta corrente Nubank é enviado para upload, ENTÃO o sistema SHALL extrair corretamente as movimentações de débito e crédito, identificando o tipo de movimentação (PIX enviado, PIX recebido, pagamento de fatura, transferência, etc.)

2.7 QUANDO o extrato de conta corrente contém movimentações com valores negativos (débitos), ENTÃO o sistema SHALL preservar e processar essas transações, representando-as com `amount` positivo e `is_refund=False` para débitos, ou com flag adequado para créditos recebidos

**3. Classificação de estabelecimentos digitais e pedágios**

2.8 QUANDO uma transação tem descrição `"NuTag"`, `"Sem Parar"` ou `"ConnectCar"`, ENTÃO o sistema SHALL classificar como categoria `"Pedágio"` (ou equivalente) com `needs_review=False`, usando keywords unificadas no `DEFAULT_CATEGORIES` do `categories.py`

2.9 QUANDO uma transação tem descrição com prefixo `"IFD*"` ou `"Ifd*"` (iFood), ENTÃO o sistema SHALL classificar como categoria `"Delivery"` com `needs_review=False`, usando matching que interprete o wildcard `*` como prefixo ou usando substring matching adequado

2.10 QUANDO uma transação tem descrição `"Apple.Com/Bill"`, `"Amazonprimebr"` ou outros serviços de streaming/assinatura, ENTÃO o sistema SHALL classificar na categoria correta (`"Streaming"` ou `"Assinaturas"`) com `needs_review=False`, usando keywords unificadas no `DEFAULT_CATEGORIES`

2.11 QUANDO uma transação é classificada pelo `ClassificationService` de `categories.py`, ENTÃO o sistema SHALL aplicar a lógica de `card_type` para determinar se a transação é `individual` ou `shared` com base no cartão registrado, preenchendo o campo `type` corretamente

**4. Persistência de dados — SQLite e BigQuery**

2.12 QUANDO o endpoint `POST /upload/confirm` salva transações no SQLite, ENTÃO o sistema SHALL preencher o campo `type` com o valor de `card_type` do cartão registrado (individual/shared), mantendo semântica consistente entre os campos `type` e `card_type`

2.13 QUANDO o endpoint `POST /upload/confirm` salva transações no BigQuery (modo cloud), ENTÃO o sistema SHALL incluir os campos `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id` e `needs_review` no payload enviado ao BigQuery

2.14 QUANDO o endpoint `POST /upload/confirm` registra o upload no `upload_history`, ENTÃO o sistema SHALL usar os valores reais de `statement_type` e `bank` extraídos do PDF, em vez de valores hardcoded

2.15 QUANDO o `ExtractionService` é usado em ambiente de produção com múltiplos workers, ENTÃO o sistema SHALL utilizar um mecanismo de cache persistente (ex: Redis ou Firestore) ou aceitar o reprocessamento como comportamento esperado, documentando a limitação do cache em memória

**5. Fluxo de upload — validação e roteamento**

2.16 QUANDO o endpoint `POST /upload/confirm` recebe transações de um extrato de conta corrente (`statement_type = "current_account"`), ENTÃO o sistema SHALL persistir as movimentações na tabela `current_account_movements` em vez de `transactions_gold`, ou alternativamente persistir em `transactions_gold` com `transaction_source = "current_account_pdf"` para diferenciação

2.17 QUANDO o `processor.py` processa um arquivo CSV e o campo `type` não pode ser determinado pelo `card_type` lookup, ENTÃO o sistema SHALL preencher o campo `type` com `None` de forma explícita e documentada, e o endpoint de upload SHALL retornar `needs_review=True` para essas transações

---

### Unchanged Behavior (Regression Prevention)

3.1 QUANDO um arquivo CSV válido de extrato Nubank (conta corrente ou cartão) é enviado para upload, ENTÃO o sistema SHALL CONTINUE TO processar o CSV corretamente usando o fluxo existente do `processor.py`, sem alterações no comportamento de parsing de CSV

3.2 QUANDO o `ExtractionService` é chamado com um PDF e o Gemini retorna JSON válido na primeira tentativa, ENTÃO o sistema SHALL CONTINUE TO retornar o `ExtractedStatement` validado pelo Pydantic sem acionar o fallback pdfplumber

3.3 QUANDO o `ExtractionService` é chamado com o mesmo PDF duas vezes na mesma instância, ENTÃO o sistema SHALL CONTINUE TO retornar o resultado do cache em memória na segunda chamada, sem chamar o Gemini novamente

3.4 QUANDO o Gemini falha nas 3 tentativas com backoff exponencial (1s, 2s), ENTÃO o sistema SHALL CONTINUE TO acionar o fallback pdfplumber como terceira etapa do pipeline

3.5 QUANDO uma transação tem `card_last4` registrado no workspace, ENTÃO o sistema SHALL CONTINUE TO resolver o `card_type` (individual/shared) a partir do mapa de cartões registrados

3.6 QUANDO uma transação tem `card_last4` não registrado no workspace, ENTÃO o sistema SHALL CONTINUE TO marcar `needs_review=True` e retornar o `card_last4` na lista `unregistered_cards` da resposta de preview

3.7 QUANDO o endpoint `POST /upload` recebe um arquivo maior que 10 MB, ENTÃO o sistema SHALL CONTINUE TO rejeitar o upload com HTTP 413

3.8 QUANDO o endpoint `POST /upload` recebe um arquivo com extensão diferente de `.pdf` ou `.csv`, ENTÃO o sistema SHALL CONTINUE TO rejeitar o upload com HTTP 400

3.9 QUANDO o `ClassificationService` de `categories.py` encontra uma regra de workspace para o merchant, ENTÃO o sistema SHALL CONTINUE TO usar essa regra com prioridade máxima sobre as keywords padrão

3.10 QUANDO o `ClassificationService` de `categories.py` não encontra correspondência nas keywords padrão, ENTÃO o sistema SHALL CONTINUE TO retornar `category = "Outros"` com `needs_review=True`

3.11 QUANDO transações são salvas no SQLite via `POST /upload/confirm`, ENTÃO o sistema SHALL CONTINUE TO registrar o upload na tabela `upload_history` com `status = "completed"` e a contagem correta de transações salvas

3.12 QUANDO o limite de uploads mensais do plano é atingido, ENTÃO o sistema SHALL CONTINUE TO rejeitar o upload com HTTP 402 antes de processar o arquivo

---

## Condição de Bug (Bug Condition Methodology)

### Função de Condição de Bug

```pascal
FUNCTION isBugCondition(X)
  INPUT: X de tipo UploadInput {file_bytes, filename, statement_type}
  OUTPUT: boolean

  RETURN (
    // Bug 1: PDF de cartão com fallback pdfplumber
    (X.filename ends_with ".pdf" AND X.statement_type = "credit_card" AND gemini_unavailable(X))
    OR
    // Bug 2: PDF de conta corrente
    (X.filename ends_with ".pdf" AND X.statement_type = "current_account")
    OR
    // Bug 3: Transação com merchant digital (NuTag, iFood, Apple)
    (X.description matches ["nutag", "ifd*", "apple.com/bill", "amazonprimebr", "sem parar"])
    OR
    // Bug 4: Persistência no BigQuery sem campos SaaS
    (X.mode = "cloud" AND X.has_card_last4 = true)
    OR
    // Bug 5: Conta corrente roteada para transactions_gold
    (X.statement_type = "current_account" AND X.action = "confirm")
  )
END FUNCTION
```

### Propriedade de Correção (Fix Checking)

```pascal
// Propriedade: Verificação de Correção
FOR ALL X WHERE isBugCondition(X) DO
  result ← processUpload'(X)
  ASSERT (
    result.transactions_count > 0
    AND result.statement_type = X.expected_statement_type
    AND ALL tx IN result.transactions: tx.category != "Outros" OR tx.needs_review = true
    AND ALL tx IN result.transactions: tx.card_type IS NOT NULL OR tx.card_last4 IS NULL
    AND result.upload_history.statement_type = X.expected_statement_type
    AND result.upload_history.bank IS NOT NULL
  )
END FOR
```

### Propriedade de Preservação (Preservation Checking)

```pascal
// Propriedade: Verificação de Preservação
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT processUpload(X) = processUpload'(X)
END FOR
```
