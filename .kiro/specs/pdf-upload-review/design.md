# pdf-upload-review Bugfix Design

## Overview

O pipeline de upload de PDFs bancários (Nubank cartão de crédito e conta corrente) apresenta cinco grupos de bugs que comprometem extração, classificação e persistência. A estratégia de correção adota o **Gemini como caminho primário e robusto** para leitura de PDFs, com prompt reforçado (few-shot examples, `response_mime_type` para JSON estruturado, instruções explícitas para ambos os tipos de extrato). O fallback pdfplumber é mantido apenas como último recurso com correções cirúrgicas. As demais correções são pontuais e não alteram o comportamento de fluxos já funcionais (CSV, Gemini bem-sucedido, regras de workspace).

Pipeline atual (com bugs):
```
POST /upload → ExtractionService.extract()
  ├─ Cache hit → retorna cached
  ├─ Gemini (3 tentativas) → OK → retorna ExtractedStatement
  └─ Fallback pdfplumber → BUGADO para CC e sem suporte a CA
```

Pipeline corrigido:
```
POST /upload → ExtractionService.extract()
  ├─ Cache hit → retorna cached
  ├─ Gemini (3 tentativas, prompt reforçado) → OK → retorna ExtractedStatement
  └─ Fallback pdfplumber (corrigido) → suporte CC + CA
       └─ Detecção dinâmica de statement_type
       └─ Regex corrigido para layout real Nubank
       └─ Período derivado das transações extraídas

POST /upload/confirm
  ├─ statement_type == "credit_card" → salva em transactions_gold
  ├─ statement_type == "current_account" → salva em current_account_movements
  └─ upload_history com statement_type e bank reais

categories.py → DEFAULT_CATEGORIES unificado com keywords de classification_service.py
```


## Glossary

- **Bug_Condition (C)**: Conjunto de entradas que ativam qualquer um dos cinco grupos de bugs descritos no `bugfix.md`
- **Property (P)**: Comportamento correto esperado quando C(X) é verdadeiro — extração completa, classificação correta, persistência íntegra
- **Preservation**: Comportamentos que NÃO devem ser alterados — fluxo CSV, Gemini bem-sucedido, cache em memória, regras de workspace, validações de upload
- **ExtractionService**: Classe em `extraction_service.py` que orquestra o pipeline cache → Gemini → pdfplumber
- **ExtractedStatement**: Modelo Pydantic que representa o resultado validado da extração de um PDF
- **statement_type**: Campo `"credit_card"` ou `"current_account"` que determina o roteamento de persistência
- **isBugCondition**: Função pseudocódigo que identifica entradas que ativam os bugs
- **DEFAULT_CATEGORIES**: Dicionário em `categories.py` que é a fonte ativa de keywords de classificação no fluxo de upload
- **CATEGORY_KEYWORDS**: Dicionário em `classification_service.py` (módulo legado) com keywords mais completas que precisam ser unificadas no `DEFAULT_CATEGORIES`
- **upload_history**: Tabela SQLite que registra metadados de cada upload confirmado
- **transactions_gold**: Tabela SQLite/BigQuery para transações de cartão de crédito
- **current_account_movements**: Tabela SQLite/Firestore para movimentações de conta corrente


## Bug Details

### Bug Condition

Os bugs se manifestam em cinco cenários distintos, todos relacionados ao processamento de PDFs bancários Nubank ou à classificação/persistência de transações.

**Formal Specification:**
```
FUNCTION isBugCondition(X)
  INPUT: X de tipo UploadInput {
    file_bytes, filename, statement_type,
    description, mode, has_card_last4, action
  }
  OUTPUT: boolean

  RETURN (
    // Bug Group 1: PDF de cartão de crédito processado pelo fallback pdfplumber
    (X.filename ends_with ".pdf"
     AND X.statement_type = "credit_card"
     AND gemini_unavailable(X)
     AND (
       extracted_transactions_count(X) = 0
       OR holder_name(X) = "Titular"
       OR period_start(X) = "2026-01-01"  // hardcoded fallback
     ))
    OR
    // Bug Group 2: PDF de conta corrente (qualquer caminho)
    (X.filename ends_with ".pdf"
     AND X.statement_type = "current_account"
     AND (
       fallback_returns_credit_card_type(X)
       OR negative_amounts_discarded(X)
     ))
    OR
    // Bug Group 3: Merchant digital não classificado
    (X.description matches_any [
       "nutag", "sem parar", "conectcar",
       "ifd*", "apple.com/bill", "amazonprimebr",
       "prime canais", "youtube premium"
     ]
     AND classifier_used = "categories.DEFAULT_CATEGORIES"
     AND result.category = "Outros")
    OR
    // Bug Group 4: Ausência de inserção no BigQuery no bloco cloud
    (X.mode = "cloud"
     AND X.action = "confirm"
     AND bigquery_insert_missing(X))
    OR
    (X.action = "confirm"
     AND upload_history.statement_type = "credit_card"  // hardcoded
     AND upload_history.bank = None)
    OR
    // Bug Group 5: Conta corrente roteada para transactions_gold
    (X.statement_type = "current_account"
     AND X.action = "confirm"
     AND persisted_to = "transactions_gold")
  )
END FUNCTION
```

### Examples

**Bug 1 — Fallback pdfplumber, cartão de crédito:**
- Entrada: `NU_45499351_01ABR2026_30ABR2026.pdf`, Gemini indisponível
- Atual: `transactions = []`, `holder_name = "Titular"`, `period_start = "2026-01-01"`
- Esperado: lista completa de transações, nome real do titular, período derivado das datas

**Bug 2 — Conta corrente:**
- Entrada: `Nubank_2026-05-04.pdf`
- Atual: `statement_type = "credit_card"`, movimentações negativas descartadas em `_process_chunk`
- Esperado: `statement_type = "current_account"`, todos os débitos e créditos extraídos

**Bug 3 — Merchant digital:**
- Entrada: transação com `description = "NuTag 0001 Rodovia SP-330"`
- Atual: `category = "Outros"`, `needs_review = True`
- Esperado: `category = "Transporte"`, `needs_review = False`

- Entrada: transação com `description = "IFD*RESTAURANTE XPTO"`
- Atual: `category = "Outros"` (wildcard `ifd*` não funciona como substring)
- Esperado: `category = "Delivery"`, `needs_review = False`

**Bug 4 — BigQuery payload ausente:**
- Entrada: confirmação de upload em modo cloud com `card_last4 = "4535"`
- Atual: Firestore recebe payload completo com campos SaaS, mas NÃO há inserção no BigQuery — apenas Firestore é usado no bloco cloud
- Esperado: inserção no BigQuery com todos os campos SaaS presentes (além do Firestore que já funciona)

**Bug 5 — Roteamento conta corrente:**
- Entrada: `POST /upload/confirm` com `statement_type = "current_account"`
- Atual: transações salvas em `transactions_gold`
- Esperado: movimentações salvas em `current_account_movements`


## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Upload de arquivos CSV (cartão de crédito e conta corrente) deve continuar funcionando exatamente como antes via `processor.py`
- Quando o Gemini retorna JSON válido na primeira tentativa, o `ExtractedStatement` validado pelo Pydantic deve ser retornado sem acionar o fallback
- O cache em memória (`self._cache`) deve continuar retornando o resultado na segunda chamada com o mesmo PDF na mesma instância
- Regras de workspace (`workspace_category_rules`) devem continuar tendo prioridade máxima sobre keywords padrão
- Validações de upload (tamanho máximo 10 MB, extensões permitidas) devem continuar funcionando
- Limite de uploads mensais por plano deve continuar sendo verificado antes do processamento
- Quando `card_last4` não está registrado, `needs_review = True` e o card deve aparecer em `unregistered_cards`
- O fluxo de 3 tentativas com backoff exponencial (1s, 2s) do Gemini deve ser preservado

**Scope:**
Todas as entradas que NÃO ativam `isBugCondition(X)` devem produzir exatamente o mesmo resultado antes e depois da correção. Isso inclui:
- PDFs processados com sucesso pelo Gemini
- Arquivos CSV de qualquer tipo
- Transações com merchants já classificados corretamente
- Uploads em modo SQLite com campos já corretos
- Qualquer endpoint não relacionado ao fluxo de upload/confirm


## Hypothesized Root Cause

### Bug Group 1 — Fallback pdfplumber, cartão de crédito

1. **Regex de transações muito restritivo**: O padrão `tx_pattern` em `_extract_transactions_from_text` usa `(.+?)\s+` para a descrição, mas o `$` no final exige que o valor esteja no final da linha sem espaços extras. PDFs Nubank frequentemente têm espaços múltiplos entre campos e caracteres especiais (asteriscos, barras) nas descrições que quebram o match.

2. **Regex de titular incompatível com layout real**: `_extract_holder_name` busca `"Olá, Nome"` ou linhas capitalizadas, mas o PDF real da Nubank (`NU_45499351_01ABR2026_30ABR2026.pdf`) usa layout gerado por `openhtmltopdf` com fontes customizadas (Graphik), e o texto extraído pelo pdfplumber pode não seguir esse padrão exato.

3. **Período hardcoded como fallback**: `_extract_period` retorna `("2026-01-01", "2026-01-31")` quando nenhum padrão é encontrado, em vez de derivar das datas das transações já extraídas.

4. **`statement_type` hardcoded como `"credit_card"`**: O método `_fallback_pdfplumber` retorna `statement_type="credit_card"` incondicionalmente, sem inspecionar o conteúdo do PDF.

4.1. **`_extract_sections` não captura transações do titular principal**: O código real já tem `_extract_sections()` que busca por `"NOME - final XXXX"` e extrai seções por titular adicional. Porém, o titular PRINCIPAL não tem sufixo "- final XXXX", então suas transações ficam ANTES da primeira seção encontrada e são perdidas. Se nenhuma seção é encontrada, cai no fallback de seção única com `_extract_transactions_from_text(full_text)` — mas o regex de transações falha pelos motivos do item 1.

### Bug Group 2 — Conta corrente

5. **Ausência de parser para conta corrente no fallback**: `_fallback_pdfplumber` não possui lógica para o layout do extrato de conta corrente Nubank (`Nubank_2026-05-04.pdf`), que usa formato diferente (movimentações com sinal, sem seções por titular).

6. **`if amount < 0: continue` em `_process_chunk`**: O `processor.py` descarta valores negativos, o que é correto para faturas de cartão (onde negativos são estornos), mas incorreto para conta corrente (onde negativos são débitos legítimos). Este bug afeta o fluxo CSV de conta corrente também.

### Bug Group 3 — Classificação de merchants digitais

7. **Divergência entre `DEFAULT_CATEGORIES` (ativo) e `CATEGORY_KEYWORDS` (legado)**: O `categories.py` é o módulo ativo no fluxo de upload, mas seu `DEFAULT_CATEGORIES` não contém keywords de pedágio (`nutag`, `sem parar`, `conectcar`), streaming completo (`apple.com/bill`, `amazonprimebr`, `youtube premium`) e outros merchants digitais presentes apenas no `CATEGORY_KEYWORDS` do `classification_service.py`.

8. **Wildcard `ifd*` interpretado como substring literal**: Em `_match_default_keywords`, a verificação `if kw.lower() in desc_lower` trata `"ifd*"` como string literal, não como padrão glob. A string `"ifd*"` nunca aparece em descrições reais — o prefixo real é `"ifd"` seguido de qualquer caractere.

### Bug Group 4 — Persistência

9. **BigQuery não é inserido no bloco cloud**: No bloco cloud do `upload_confirm` em `main.py`, o código envia para Firestore com payload completo (incluindo campos SaaS), mas **não há inserção no BigQuery**. O Firestore já recebe `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id`, `needs_review` corretamente. O bug é a ausência total de inserção BigQuery no fluxo cloud de upload.

10. **`upload_history` com valores hardcoded**: No `upload_confirm`, os campos `statement_type = "credit_card"` e `bank = None` são hardcoded. O `ExtractedStatement` retornado pelo `ExtractionService` contém os valores reais, mas eles não são propagados até o momento do `confirm` (o `file_hash` é o único elo entre preview e confirm).

### Bug Group 5 — Roteamento

11. **`upload_confirm` sem roteamento por `statement_type`**: O endpoint `POST /upload/confirm` salva todas as transações em `transactions_gold` independentemente do `statement_type`. O `UploadConfirmRequest` não carrega o `statement_type`, então o endpoint não tem como diferenciar o destino de persistência.


## Correctness Properties

Property 1: Bug Condition — Extração completa via Gemini (caminho primário)

_For any_ PDF de extrato bancário Nubank (cartão de crédito ou conta corrente) onde o Gemini está disponível, o `ExtractionService.extract()` corrigido SHALL retornar um `ExtractedStatement` com `transactions_count > 0`, `statement_type` correto (`"credit_card"` ou `"current_account"`), `holder_name` não vazio e diferente de `"Titular"`, e `period_start`/`period_end` derivados do conteúdo real do PDF.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

Property 2: Bug Condition — Fallback pdfplumber corrigido

_For any_ PDF de extrato bancário Nubank onde o Gemini falha nas 3 tentativas, o fallback `_fallback_pdfplumber` corrigido SHALL detectar dinamicamente o `statement_type`, extrair transações com regex compatível com o layout real do PDF, retornar o nome real do titular (ou `"Nubank"` como fallback seguro), e derivar o período das datas das transações extraídas em vez de retornar datas hardcoded.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

Property 3: Bug Condition — Classificação correta de merchants digitais

_For any_ transação com descrição contendo `"nutag"`, `"sem parar"`, `"conectcar"`, `"veloe"` (pedágios), `"ifd"` (prefixo iFood), `"apple.com/bill"`, `"amazonprimebr"`, `"youtube premium"` ou `"prime canais"`, o `ClassificationService` de `categories.py` corrigido SHALL retornar a categoria correta (`"Transporte"` para pedágios, `"Delivery"` para iFood, `"Streaming"` para streaming) com `needs_review = False`.

**Validates: Requirements 2.8, 2.9, 2.10**

Property 4: Bug Condition — Inserção no BigQuery adicionada

_For any_ confirmação de upload em modo cloud (`USE_SQLITE = False`), o sistema SHALL inserir as transações no BigQuery (além do Firestore que já funciona), incluindo os campos `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id` e `needs_review` em cada linha de `transactions_gold`.

**Validates: Requirements 2.13**

Property 5: Bug Condition — upload_history com metadados reais

_For any_ confirmação de upload, o registro em `upload_history` SHALL conter o `statement_type` real extraído do PDF (não hardcoded `"credit_card"`) e o `bank` real (ex: `"Nubank"`, não `None`).

**Validates: Requirements 2.14**

Property 6: Bug Condition — Roteamento correto por statement_type

_For any_ confirmação de upload com `statement_type = "current_account"`, o endpoint `POST /upload/confirm` corrigido SHALL persistir as movimentações na tabela `current_account_movements` (SQLite) ou coleção equivalente (Firestore), e NÃO em `transactions_gold`.

**Validates: Requirements 2.16**

Property 7: Preservation — Comportamentos inalterados

_For any_ entrada onde `isBugCondition(X)` é falso (CSV uploads, Gemini bem-sucedido, regras de workspace, validações de tamanho/extensão, limite de plano), o sistema corrigido SHALL produzir exatamente o mesmo resultado que o sistema original.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12**


## Fix Implementation

### Fix 1 — Gemini como caminho primário robusto

**Arquivo**: `finance-pilot/backend/extraction_service.py`

**Função**: `GEMINI_EXTRACTION_PROMPT` e `_call_gemini`

**Mudanças específicas**:

1. **Reforçar o prompt para PDFs Nubank**: Adicionar instruções explícitas para lidar com os dois tipos de extrato Nubank, incluindo exemplos de formato de data em português (`"05 ABR 2026"`), formato de valor BRL (`"1.234,56"`), e estrutura de seções por titular adicional. O Gemini deve ser suficientemente robusto para lidar com AMBOS os tipos de PDF sem precisar do fallback na maioria dos casos. Adicionar exemplos concretos (few-shot) para melhorar a extração.

```python
GEMINI_EXTRACTION_PROMPT = """\
You are a financial document parser specialized in Brazilian bank statements.
Extract ALL transactions from the attached bank statement PDF and return a
single JSON object following the schema below.

IMPORTANT RULES FOR NUBANK STATEMENTS:
- Credit card statements (fatura): contain sections per card holder, dates in
  Portuguese format like "05 ABR" or "05 ABR 2026", amounts in BRL format
  "1.234,56". statement_type = "credit_card".
- Current account statements (extrato conta corrente): contain signed movements
  (positive = credit/PIX received, negative = debit/payment). statement_type =
  "current_account".
- Detect statement_type from content: presence of "fatura", "cartão", "vencimento"
  → "credit_card"; presence of "conta corrente", "extrato", "saldo" → "current_account".
- For current account: create ONE section with owner_name = holder_name.
  Include ALL movements (positive and negative).
  Use is_refund=false for DEBITS (money going out: PIX enviado, pagamentos, boletos).
  Use is_refund=true for CREDITS (money coming in: PIX recebido, salário, transferências recebidas).
  amount is always the absolute positive value.
- For credit card: create one section per card holder. The primary holder has no
  suffix; additional cards show "NOME - final XXXX".
- holder_name: extract the primary account holder's full name from the document.
- period_start / period_end: derive from the actual transaction dates if not
  explicitly stated.
- Return ONLY the JSON object, no markdown fences, no explanation.

EXAMPLES OF EXPECTED OUTPUT:

Example 1 - Credit card transaction line "05 ABR  UBER *TRIP  12,50":
  {{"date": "2026-04-05", "description": "UBER *TRIP", "amount": 12.50, "is_refund": false}}

Example 2 - Current account debit "PIX enviado - João  -150,00":
  {{"date": "2026-04-05", "description": "PIX enviado - João", "amount": 150.00, "is_refund": false}}

Example 3 - Current account credit "PIX recebido - Empresa  +3.500,00":
  {{"date": "2026-04-05", "description": "PIX recebido - Empresa", "amount": 3500.00, "is_refund": true}}

{schema}
"""
```

2. **Usar `response_mime_type` do Gemini** para forçar output JSON estruturado, reduzindo erros de parsing:

```python
config=types.GenerateContentConfig(
    max_output_tokens=8192,
    temperature=0,
    response_mime_type="application/json",  # Força JSON output
)
```

3. **Adicionar validação pós-Gemini**: Após `ExtractedStatement.model_validate_json(raw_json)`, verificar se `len(sections) > 0` e `any(len(s.transactions) > 0 for s in validated.sections)`. Se falhar, lançar exceção para acionar retry.

```python
# Após model_validate_json:
if not validated.sections or not any(
    len(s.transactions) > 0 for s in validated.sections
):
    raise ValueError(
        f"Gemini returned empty transactions for PDF "
        f"(statement_type={validated.statement_type})"
    )
```

---

### Fix 2 — Fallback pdfplumber corrigido

**Arquivo**: `finance-pilot/backend/extraction_service.py`

**Função**: `_fallback_pdfplumber` e helpers

**Mudanças específicas**:

1. **Detecção dinâmica de `statement_type`**:

```python
def _detect_statement_type(self, text: str) -> Literal["credit_card", "current_account"]:
    text_lower = text.lower()
    cc_signals = ["fatura", "cartão", "vencimento", "limite", "parcela"]
    ca_signals = ["conta corrente", "extrato", "saldo anterior", "saldo final", "pix enviado", "pix recebido"]
    cc_score = sum(1 for s in cc_signals if s in text_lower)
    ca_score = sum(1 for s in ca_signals if s in text_lower)
    return "current_account" if ca_score > cc_score else "credit_card"
```

2. **Regex de transações mais tolerante** (para cartão de crédito):

O padrão atual falha com múltiplos espaços. Usar `\s+` em vez de `\s` e tornar o match de valor mais robusto:

```python
tx_pattern = re.compile(
    r"^(\d{1,2})\s+([A-Za-zÀ-ú]{3})\s+"   # DD MMM
    r"(.+?)\s{2,}"                            # descrição (termina em 2+ espaços)
    r"(-?\s*[\d.,]+)\s*$",                    # valor no final
    re.MULTILINE,
)
```

Adicionar padrão alternativo para linhas com separação por tab ou alinhamento fixo:

```python
tx_pattern_alt = re.compile(
    r"^(\d{1,2})\s+([A-Za-zÀ-ú]{3})\s+"
    r"(.+?)\s+"
    r"([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*$",
    re.MULTILINE,
)
```

3. **Extração do nome do titular — múltiplos padrões**:

```python
def _extract_holder_name(self, text: str) -> str:
    patterns = [
        r"(?:Olá|Oi),?\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)+)",
        r"Fatura\s+de\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)+)",
        r"Titular[:\s]+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)+)",
        r"^([A-ZÀ-Ú]{2,}(?:\s+[A-ZÀ-Ú]{2,})+)\s*$",  # ALL CAPS name
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            return m.group(1).strip().title()
    return "Nubank"  # fallback seguro (não "Titular")
```

4. **Período derivado das transações**:

```python
def _extract_period(self, text: str, transactions: list[ExtractedTransaction] = None) -> tuple[str, str]:
    # ... tentativas de regex existentes ...
    
    # Novo fallback: derivar das transações já extraídas
    if transactions:
        dates = [t.date for t in transactions if t.date and len(t.date) == 10]
        if dates:
            return min(dates), max(dates)
    
    # Último recurso: mês atual
    import datetime
    today = datetime.date.today()
    first = today.replace(day=1).isoformat()
    last = today.replace(day=28).isoformat()  # conservador
    return first, last
```

4.1. **Corrigir `_extract_sections` para capturar transações do titular principal**:

O `_extract_sections` atual busca por padrões `"NOME - final XXXX"` e extrai seções por titular adicional. O problema é que o titular PRINCIPAL não tem sufixo "- final XXXX", então suas transações ficam ANTES da primeira seção encontrada e são perdidas. A correção deve capturar o texto entre o início das transações e o primeiro match de seção como a seção do titular principal:

```python
def _extract_sections(self, text: str) -> list[ExtractedSection]:
    sections: list[ExtractedSection] = []
    
    section_pattern = re.compile(
        r"(?:Cartão\s+(?:de\s+)?)?([A-ZÀ-Ú][A-ZÀ-Ú ]+?)\s*[-–]\s*final\s+(\d{4})",
        re.IGNORECASE,
    )
    
    matches = list(section_pattern.finditer(text))
    
    if not matches:
        return []
    
    year_match = re.search(r"(\d{4})", text[:500])
    ref_year = year_match.group(1) if year_match else "2026"
    
    # NOVO: Capturar transações do titular principal (antes da primeira seção "- final XXXX")
    # O titular principal NÃO tem sufixo "- final XXXX", suas transações aparecem
    # entre o início do bloco de transações e o primeiro match de seção adicional.
    primary_text = text[:matches[0].start()]
    primary_transactions = self._extract_transactions_from_text(
        primary_text, card_last4=None, ref_year=ref_year,
    )
    if primary_transactions:
        holder_name = self._extract_holder_name(text)
        subtotal = sum(
            t.amount if not t.is_refund else -t.amount
            for t in primary_transactions
        )
        sections.append(ExtractedSection(
            owner_name=holder_name,
            subtotal=round(subtotal, 2),
            transactions=primary_transactions,
        ))
    
    # Seções de titulares adicionais (comportamento existente)
    for i, match in enumerate(matches):
        owner_name = match.group(1).strip().title()
        card_last4 = match.group(2)
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start_pos:end_pos]
        
        transactions = self._extract_transactions_from_text(
            section_text, card_last4=card_last4, ref_year=ref_year,
        )
        subtotal = sum(
            t.amount if not t.is_refund else -t.amount
            for t in transactions
        )
        sections.append(ExtractedSection(
            owner_name=owner_name,
            subtotal=round(subtotal, 2),
            transactions=transactions,
        ))
    
    return sections
```

5. **Parser para conta corrente**:

```python
def _fallback_pdfplumber_current_account(
    self, full_text: str
) -> ExtractedStatement:
    holder_name = self._extract_holder_name(full_text)
    
    # Padrão de movimentação conta corrente Nubank:
    # "05/04/2026  PIX enviado - Fulano  -150,00"
    # "05/04/2026  PIX recebido - Empresa  +3.500,00"
    ca_pattern = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(.+?)\s+"
        r"([+-]?\s*[\d.,]+)\s*$",
        re.MULTILINE,
    )
    
    transactions = []
    for m in ca_pattern.finditer(full_text):
        date_str, description, amount_str = m.groups()
        date_iso = self._parse_ddmmyyyy(date_str)
        amount_raw = self._parse_brl_amount(amount_str.replace("+", ""))
        is_credit = "+" in amount_str or (amount_raw > 0 and "-" not in amount_str)
        
        transactions.append(ExtractedTransaction(
            date=date_iso,
            description=description.strip(),
            amount=abs(amount_raw),
            # Semântica para conta corrente:
            # is_refund=False para DÉBITOS (saídas de dinheiro)
            # is_refund=True para CRÉDITOS (entradas: PIX recebido, salário)
            is_refund=is_credit,
        ))
    
    dates = [t.date for t in transactions if t.date]
    period_start = min(dates) if dates else datetime.date.today().replace(day=1).isoformat()
    period_end = max(dates) if dates else datetime.date.today().isoformat()
    total = sum(t.amount for t in transactions if not t.is_refund)
    
    return ExtractedStatement(
        statement_type="current_account",
        bank="Nubank",
        holder_name=holder_name,
        period_start=period_start,
        period_end=period_end,
        total_amount=round(total, 2),
        sections=[ExtractedSection(
            owner_name=holder_name,
            subtotal=round(total, 2),
            transactions=transactions,
        )],
    )
```

6. **Orquestração do fallback com detecção de tipo**:

```python
def _fallback_pdfplumber(self, pdf_bytes: bytes) -> ExtractedStatement:
    # ... extração de texto existente ...
    
    statement_type = self._detect_statement_type(full_text)
    
    if statement_type == "current_account":
        return self._fallback_pdfplumber_current_account(full_text)
    else:
        return self._fallback_pdfplumber_credit_card(full_text)
```

---

### Fix 3 — Unificação de keywords em `categories.py`

**Arquivo**: `finance-pilot/backend/categories.py`

**Função**: `DEFAULT_CATEGORIES` e `_match_default_keywords`

**Mudanças específicas**:

1. **Adicionar keywords ausentes ao `DEFAULT_CATEGORIES`**:

```python
DEFAULT_CATEGORIES: dict[str, list[str]] = {
    # ... categorias existentes ...
    "Delivery": ["ifood", "rappi", "uber eats", "ifd"],  # "ifd*" → "ifd" (sem wildcard)
    "Transporte": [
        "uber", "99", "combustivel", "posto", "estacionamento", "pedagio",
        "nutag", "sem parar", "conectcar", "veloe",  # ADICIONADOS (pedágios)
    ],
    "Streaming": [
        "netflix", "spotify", "disney", "hbo", "amazon prime", "youtube premium",
        "apple.com/bill", "amazonprimebr", "prime canais",  # ADICIONADOS
        "apple tv",
    ],
    "Compras": ["shopee", "mercado livre", "amazon", "magazine"],
    "Assinaturas": [
        "google one", "icloud", "canva", "chatgpt", "github",
        "openai", "notion", "figma",  # ADICIONADOS
    ],
    # ... demais categorias ...
}
```

**Nota sobre "Pedágio" vs "Transporte"**: A categoria `"Pedágio"` NÃO existe no `DEFAULT_CATEGORIES` e não é exibida no frontend. As keywords de pedágio (`nutag`, `sem parar`, `conectcar`, `veloe`) devem ser adicionadas à categoria **"Transporte"** que já existe e é reconhecida pelo frontend. Isso é a decisão mais conservadora e evita criar uma categoria nova que precisaria de mudanças no frontend.

2. **Corrigir matching de wildcard**: Remover o `*` das keywords e usar substring matching puro. O `*` em `"ifd*"` era uma tentativa de glob que nunca funcionou como substring. A keyword correta é `"ifd"` (prefixo real do iFood nas faturas Nubank).

3. **Não criar categoria "Pedágio" separada**: Usar `"Transporte"` para todas as keywords de pedágio, mantendo consistência com o que o frontend já exibe.

---

### Fix 4 — Adicionar inserção BigQuery no bloco cloud

**Arquivo**: `finance-pilot/backend/main.py`

**Função**: `upload_confirm` (bloco cloud/Firestore+BigQuery)

**Mudanças específicas**:

O bloco cloud atual envia para Firestore com payload completo (incluindo todos os campos SaaS: `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id`, `needs_review`), mas **NÃO há inserção no BigQuery**. O Firestore já está correto. O fix é ADICIONAR a inserção BigQuery:

```python
# Após batch.commit() do Firestore:
if bq_client is not None:
    bq_rows = []
    for tx_payload in all_tx_payloads:  # lista acumulada durante o loop
        bq_rows.append({
            "id": tx_payload["id"],
            "tenant_id": tx_payload["tenant_id"],
            "date": tx_payload["date"],
            "month_ref": tx_payload["month_ref"],
            "amount": tx_payload["amount"],
            "merchant_clean": tx_payload["merchant_clean"],
            "category": tx_payload["category"],
            "subcategory": tx_payload["subcategory"],
            "owner": tx_payload["owner"],
            "type": tx_payload["type"],
            "created_at": tx_payload["created_at"],
            # Campos SaaS (já presentes no Firestore, agora também no BigQuery):
            "card_last4": tx_payload.get("card_last4"),
            "card_type": tx_payload.get("card_type"),
            "is_refund": tx_payload.get("is_refund", False),
            "transaction_source": tx_payload.get("transaction_source", "pdf_extraction"),
            "upload_id": tx_payload.get("upload_id"),
            "needs_review": tx_payload.get("needs_review", False),
        })
    errors = bq_client.insert_rows_json(TABLE_GOLD, bq_rows)
    if errors:
        logger.error("BigQuery insert errors: %s", errors)
```

**Nota**: O payload do Firestore já está correto e não precisa de alteração. O fix é exclusivamente adicionar a inserção no BigQuery que está ausente.

---

### Fix 5 — `upload_history` com metadados reais e contrato da API

**Arquivo**: `finance-pilot/backend/main.py`

**Função**: `upload_confirm`

**Mudanças específicas**:

1. **Adicionar `statement_type` e `bank` ao `UploadConfirmRequest`**:

```python
class UploadConfirmRequest(BaseModel):
    file_hash: str
    statement_type: Literal["credit_card", "current_account"] = "credit_card"
    bank: Optional[str] = None
    transactions: List[ConfirmedTransaction]
```

**Nota sobre contrato da API**: O `UploadPreviewResponse` já retorna `statement_type` e `bank`. O frontend DEVE enviar esses valores de volta no body do `UploadConfirmRequest`. Isso é uma mudança no contrato da API que requer atualização no frontend (página de upload) para incluir esses campos no POST de confirmação.

2. **Usar os valores reais no INSERT de `upload_history`**:

```python
c.execute(
    """INSERT INTO upload_history (..., statement_type, bank, ...) VALUES (...)""",
    (
        ...,
        body.statement_type,  # antes: "credit_card" hardcoded
        body.bank,            # antes: None hardcoded
        ...,
    ),
)
```

3. **Frontend deve enviar `statement_type` e `bank` no body do confirm**, usando os valores retornados pelo `UploadPreviewResponse`. Exemplo de mudança no frontend:

```typescript
// No upload/page.tsx, ao chamar POST /upload/confirm:
const confirmBody = {
  file_hash: previewData.file_hash,
  statement_type: previewData.statement_type,  // NOVO
  bank: previewData.bank,                       // NOVO
  transactions: confirmedTransactions,
};
```

---

### Fix 6 — Roteamento por `statement_type` no confirm

**Arquivo**: `finance-pilot/backend/main.py`

**Função**: `upload_confirm`

**Mudanças específicas**:

Adicionar bloco condicional após a classificação de cada transação:

```python
if body.statement_type == "current_account":
    # Persistir em current_account_movements
    movement_id = f"pdf-{tx_id}"
    amount_signed = -tx.amount if not tx.is_refund else tx.amount
    c.execute(
        """
        INSERT OR REPLACE INTO current_account_movements
        (tenant_id, owner, movement_id, date, month_ref, amount_signed,
         description, source_file, is_card_invoice_payment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workspace_id, tx.owner, movement_id, tx.date, month_ref,
            amount_signed, tx.description,
            f"pdf_{body.file_hash[:8]}", 0, now,
        ),
    )
    saved_count += 1
else:
    # Persistir em transactions_gold (comportamento atual)
    c.execute("""INSERT OR REPLACE INTO transactions_gold ...""", (...))
    saved_count += 1
```

**Nota sobre campo `owner` para conta corrente**: O `ConfirmedTransaction` já possui o campo `owner`. Para conta corrente, o frontend deve preencher `owner` com o `holder_name` retornado pelo `UploadPreviewResponse` (que é derivado do `ExtractedStatement.holder_name`). O backend usa `tx.owner` diretamente no INSERT, então a responsabilidade de preencher corretamente é do frontend na tela de confirmação.

---

### Fix 7 — `_process_chunk` para conta corrente (processor.py)

**Arquivo**: `finance-pilot/backend/processor.py`

**Função**: `_process_chunk`

**Mudanças específicas**:

Adicionar parâmetro `allow_negative: bool = False` e usar no contexto de conta corrente:

```python
def _process_chunk(
    self, df, date_col, amt_col, merch_col, owner, month_ref,
    tenant_id, filename, offset, allow_negative: bool = False
):
    # ...
    # Antes: if amount < 0: continue
    # Depois:
    if amount < 0 and not allow_negative:
        continue
    # Para conta corrente, amount negativo = débito legítimo
    # amount = abs(amount) para manter consistência no campo amount
```

**Nota**: Este fix afeta o fluxo CSV de conta corrente. O endpoint `/current-account/upload` já trata valores negativos corretamente via `_parse_signed_amount`. O `_process_chunk` é usado pelo `process_file` que é chamado pelo endpoint `/upload` para CSVs — verificar se o endpoint CSV de conta corrente usa `process_file` ou o endpoint dedicado `/current-account/upload`.


## Testing Strategy

### Validation Approach

A estratégia segue duas fases: primeiro, executar testes exploratórios no código **não corrigido** para confirmar os root causes e obter contraexemplos concretos; depois, executar testes de fix checking e preservation checking no código **corrigido**.

---

### Exploratory Bug Condition Checking

**Goal**: Confirmar ou refutar as hipóteses de root cause ANTES de implementar as correções. Se refutarmos, precisamos re-hipotetizar.

**Test Plan**: Escrever testes que exercitam cada bug condition com os PDFs reais (`NU_45499351_01ABR2026_30ABR2026.pdf` e `Nubank_2026-05-04.pdf`) e com merchants digitais conhecidos. Executar no código não corrigido e observar as falhas.

**Test Cases**:

1. **Fallback CC — Transações vazias** (Bug 1): Mockar Gemini para falhar, chamar `ExtractionService.extract()` com `NU_45499351_01ABR2026_30ABR2026.pdf`, assertar que `len(sections[0].transactions) > 0` — **vai falhar no código não corrigido**

2. **Fallback CC — Titular padrão** (Bug 1.4): Mesmo setup, assertar que `holder_name != "Titular"` — **vai falhar**

3. **Fallback CC — Período hardcoded** (Bug 1.5): Mesmo setup, assertar que `period_start != "2026-01-01"` — **vai falhar**

4. **Fallback CA — statement_type errado** (Bug 2): Mockar Gemini para falhar, chamar com `Nubank_2026-05-04.pdf`, assertar `statement_type == "current_account"` — **vai falhar**

5. **Classificação NuTag** (Bug 3): Chamar `ClassificationService().classify("NuTag", workspace_id)`, assertar `category == "Transporte"` e `needs_review == False` — **vai falhar**

6. **Classificação IFD*** (Bug 3): Chamar com `"IFD*RESTAURANTE XPTO"`, assertar `category == "Delivery"` — **vai falhar** (wildcard não funciona)

7. **Classificação Apple.Com/Bill** (Bug 3): Chamar com `"Apple.Com/Bill"`, assertar `category == "Streaming"` — **vai falhar**

8. **upload_history hardcoded** (Bug 4): Executar `POST /upload/confirm` com PDF de conta corrente, verificar `upload_history.statement_type` — **vai retornar `"credit_card"`**

9. **Roteamento CA** (Bug 5): Executar `POST /upload/confirm` com `statement_type="current_account"`, verificar que `current_account_movements` foi populado — **vai falhar**

**Expected Counterexamples**:
- `ExtractionService._fallback_pdfplumber()` retorna `sections[0].transactions = []` para o PDF real
- `ClassificationService.classify("NuTag", ws)` retorna `ClassificationResult(category="Outros", needs_review=True)`
- `upload_history` contém `statement_type = "credit_card"` mesmo para PDFs de conta corrente

---

### Fix Checking

**Goal**: Verificar que para todas as entradas onde `isBugCondition(X)` é verdadeiro, o sistema corrigido produz o comportamento esperado.

**Pseudocode:**
```
FOR ALL X WHERE isBugCondition(X) DO
  result := processUpload_fixed(X)
  ASSERT (
    result.transactions_count > 0
    AND result.statement_type IN ["credit_card", "current_account"]
    AND result.holder_name NOT IN ["Titular", None, ""]
    AND result.period_start != "2026-01-01"  // não hardcoded
    AND ALL tx IN result.transactions:
        tx.category != "Outros" OR tx.needs_review = True
    AND result.upload_history.statement_type = X.expected_statement_type
    AND result.upload_history.bank IS NOT NULL
    AND (
      X.statement_type = "current_account"
        IMPLIES persisted_to(result) = "current_account_movements"
    )
  )
END FOR
```

---

### Preservation Checking

**Goal**: Verificar que para todas as entradas onde `isBugCondition(X)` é falso, o sistema corrigido produz o mesmo resultado que o sistema original.

**Pseudocode:**
```
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT processUpload_original(X) = processUpload_fixed(X)
END FOR
```

**Testing Approach**: Property-based testing é recomendado para preservation checking porque:
- Gera automaticamente muitos casos de teste no domínio de entrada
- Captura edge cases que testes manuais podem perder
- Fornece garantias fortes de que o comportamento é preservado para todas as entradas não-bugadas

**Test Plan**: Observar o comportamento no código não corrigido para entradas CSV e Gemini bem-sucedido, depois escrever testes PBT que capturam esse comportamento e verificam que ele continua após a correção.

**Test Cases**:

1. **CSV preservation**: Gerar CSVs aleatórios com colunas válidas, verificar que `process_file` retorna o mesmo resultado antes e depois das correções

2. **Gemini success preservation**: Mockar Gemini para retornar JSON válido, verificar que `ExtractionService.extract()` retorna o `ExtractedStatement` sem acionar fallback

3. **Workspace rule preservation**: Criar regra de workspace para merchant, verificar que a regra tem prioridade sobre keywords padrão após as correções em `DEFAULT_CATEGORIES`

4. **Upload validation preservation**: Verificar que arquivos > 10 MB e extensões inválidas continuam sendo rejeitados

5. **Plan limit preservation**: Verificar que limite de uploads mensais continua sendo verificado

---

### Unit Tests

- Testar `_detect_statement_type()` com textos de CC e CA
- Testar `_extract_holder_name()` com múltiplos layouts de PDF Nubank
- Testar `_extract_period()` com e sem transações disponíveis para derivação
- Testar `_extract_transactions_from_text()` com linhas contendo múltiplos espaços e caracteres especiais
- Testar `_match_default_keywords()` para cada merchant digital corrigido
- Testar que `"ifd*"` foi substituído por `"ifd"` e funciona como substring
- Testar `upload_confirm` com `statement_type="current_account"` e verificar tabela de destino
- Testar payload BigQuery com todos os campos SaaS presentes

### Property-Based Tests

- Gerar descrições aleatórias de merchants e verificar que a classificação é determinística e consistente
- Gerar PDFs sintéticos (texto) com diferentes layouts e verificar que `_detect_statement_type` classifica corretamente
- Gerar listas de transações aleatórias e verificar que `period_start <= period_end` sempre
- Gerar payloads de confirm aleatórios e verificar que `statement_type` determina a tabela de destino corretamente
- Verificar que para qualquer merchant com keyword em `DEFAULT_CATEGORIES`, `needs_review = False`

### Integration Tests

- Upload completo de `NU_45499351_01ABR2026_30ABR2026.pdf` com Gemini mockado para falhar → verificar extração via fallback com transações reais
- Upload completo de `Nubank_2026-05-04.pdf` → verificar `statement_type = "current_account"` e persistência em `current_account_movements`
- Fluxo completo preview → confirm com PDF de cartão de crédito → verificar `upload_history` com `statement_type` e `bank` corretos
- Fluxo completo com merchant `"NuTag"` → verificar `category = "Transporte"` no preview e no confirm
- Verificar que CSV upload não é afetado pelas correções (regression test)
