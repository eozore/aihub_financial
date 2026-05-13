# Implementation Plan

## pdf-upload-review — Plano de Implementação

---

- [x] 1. Escrever teste exploratório de bug condition (ANTES de implementar qualquer fix)
  - **Property 1: Bug Condition** - Extração, Classificação e Persistência com Entradas Bugadas
  - **CRITICAL**: Este teste DEVE FALHAR no código não corrigido — a falha confirma que os bugs existem
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: Este teste codifica o comportamento esperado — ele validará os fixes quando passar após a implementação
  - **GOAL**: Surfaçar contraexemplos que demonstram os bugs existentes
  - **Scoped PBT Approach**: Para bugs determinísticos, escopar a propriedade aos casos concretos de falha para garantir reprodutibilidade
  - Criar `finance-pilot/backend/tests/test_bug_condition_exploration.py`
  - **Bug 1 — Fallback pdfplumber CC (transações vazias)**:
    - Mockar Gemini para lançar exceção em todas as tentativas
    - Chamar `ExtractionService().extract(pdf_bytes)` com `NU_45499351_01ABR2026_30ABR2026.pdf`
    - Assertar `len(result.sections[0].transactions) > 0` — **ESPERADO: FALHA** (lista vazia)
    - Documentar contraexemplo: `sections[0].transactions = []`
  - **Bug 1.4 — Titular padrão**:
    - Mesmo setup (Gemini mockado para falhar)
    - Assertar `result.holder_name != "Titular"` — **ESPERADO: FALHA** (retorna "Titular")
    - Documentar contraexemplo: `holder_name = "Titular"`
  - **Bug 1.5 — Período hardcoded**:
    - Mesmo setup
    - Assertar `result.period_start != "2026-01-01"` — **ESPERADO: FALHA** (retorna data hardcoded)
    - Documentar contraexemplo: `period_start = "2026-01-01"`
  - **Bug 2 — Conta corrente: statement_type errado**:
    - Mockar Gemini para falhar, chamar com `Nubank_2026-05-04.pdf`
    - Assertar `result.statement_type == "current_account"` — **ESPERADO: FALHA** (retorna "credit_card")
    - Documentar contraexemplo: `statement_type = "credit_card"`
  - **Bug 3 — Classificação NuTag**:
    - Chamar `ClassificationService().classify("NuTag 0001 Rodovia SP-330", workspace_id="test")`
    - Assertar `result.category == "Transporte"` e `result.needs_review == False` — **ESPERADO: FALHA**
    - Documentar contraexemplo: `category = "Outros", needs_review = True`
  - **Bug 3 — Classificação IFD***:
    - Chamar `ClassificationService().classify("IFD*RESTAURANTE XPTO", workspace_id="test")`
    - Assertar `result.category == "Delivery"` — **ESPERADO: FALHA** (wildcard não funciona)
    - Documentar contraexemplo: `category = "Outros"`
  - **Bug 3 — Classificação Apple.Com/Bill**:
    - Chamar `ClassificationService().classify("Apple.Com/Bill", workspace_id="test")`
    - Assertar `result.category == "Streaming"` — **ESPERADO: FALHA**
    - Documentar contraexemplo: `category = "Outros"`
  - **Bug 5 — upload_history hardcoded**:
    - Executar `POST /upload/confirm` com `statement_type = "current_account"` via TestClient
    - Verificar `upload_history.statement_type` no SQLite — **ESPERADO: FALHA** (retorna "credit_card")
    - Documentar contraexemplo: `statement_type = "credit_card"` hardcoded
  - **Bug 5 — Roteamento conta corrente**:
    - Executar `POST /upload/confirm` com `statement_type = "current_account"`
    - Verificar que transações foram salvas em `current_account_movements` — **ESPERADO: FALHA** (salva em `transactions_gold`)
    - Documentar contraexemplo: `persisted_to = "transactions_gold"`
  - Executar testes: `pytest finance-pilot/backend/tests/test_bug_condition_exploration.py -v`
  - **EXPECTED OUTCOME**: Todos os testes FALHAM (isso é correto — prova que os bugs existem)
  - Documentar todos os contraexemplos encontrados para entender as causas raiz
  - Marcar tarefa como completa quando os testes estiverem escritos, executados e as falhas documentadas
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.10, 1.14, 1.16_

- [x] 2. Escrever testes de preservation (ANTES de implementar qualquer fix)
  - **Property 2: Preservation** - Comportamentos Inalterados para Entradas Não-Bugadas
  - **IMPORTANT**: Seguir metodologia observation-first
  - Observar comportamento no código NÃO CORRIGIDO para entradas não-bugadas
  - Escrever testes PBT que capturam os padrões de comportamento observados
  - Verificar que os testes PASSAM no código não corrigido antes de implementar os fixes
  - Criar `finance-pilot/backend/tests/test_preservation.py`
  - **Preservation 1 — CSV upload inalterado**:
    - Observar: `processor.process_file(csv_bytes, ...)` retorna `count > 0` para CSV válido
    - Escrever PBT: para qualquer CSV com colunas `date`, `amount`, `title` e valores válidos, `process_file` retorna `count > 0`
    - Usar `hypothesis` para gerar CSVs aleatórios com estrutura válida
    - Verificar que o teste PASSA no código não corrigido
  - **Preservation 2 — Gemini bem-sucedido não aciona fallback**:
    - Observar: quando Gemini retorna JSON válido, `extract()` retorna `ExtractedStatement` sem chamar `_fallback_pdfplumber`
    - Escrever teste: mockar Gemini para retornar JSON válido, assertar que `_fallback_pdfplumber` não é chamado
    - Verificar que o teste PASSA no código não corrigido
  - **Preservation 3 — Cache em memória funciona**:
    - Observar: segunda chamada com mesmo PDF retorna resultado do cache sem chamar Gemini
    - Escrever teste: chamar `extract()` duas vezes com mesmo PDF, assertar que Gemini é chamado apenas uma vez
    - Verificar que o teste PASSA no código não corrigido
  - **Preservation 4 — Regras de workspace têm prioridade máxima**:
    - Observar: `ClassificationService.classify()` retorna categoria da regra de workspace quando existe
    - Escrever PBT: para qualquer merchant com regra de workspace, a regra tem prioridade sobre keywords padrão
    - Verificar que o teste PASSA no código não corrigido
  - **Preservation 5 — Validações de upload inalteradas**:
    - Observar: arquivo > 10 MB retorna HTTP 413; extensão inválida retorna HTTP 400
    - Escrever testes: verificar que as validações continuam funcionando
    - Verificar que os testes PASSAM no código não corrigido
  - **Preservation 6 — Limite de plano inalterado**:
    - Observar: quando limite de uploads mensais é atingido, retorna HTTP 402
    - Escrever teste: verificar que o limite continua sendo verificado
    - Verificar que o teste PASSA no código não corrigido
  - **Preservation 7 — Fallback para "Outros" inalterado**:
    - Observar: merchant sem keyword em `DEFAULT_CATEGORIES` retorna `category = "Outros"` com `needs_review = True`
    - Escrever PBT: para qualquer merchant sem keyword conhecida, `needs_review = True`
    - Verificar que o teste PASSA no código não corrigido
  - Executar testes: `pytest finance-pilot/backend/tests/test_preservation.py -v`
  - **EXPECTED OUTCOME**: Todos os testes PASSAM (confirma comportamento baseline a preservar)
  - Marcar tarefa como completa quando os testes estiverem escritos, executados e passando no código não corrigido
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12_

- [x] 3. Fix 3 — Unificação de keywords em `categories.py`

  - [x] 3.1 Adicionar keywords ausentes ao `DEFAULT_CATEGORIES` em `categories.py`
    - Adicionar keywords de pedágio à categoria `"Transporte"`: `"nutag"`, `"sem parar"`, `"conectcar"`, `"veloe"`
    - Adicionar keywords de streaming ausentes à categoria `"Streaming"`: `"apple.com/bill"`, `"amazonprimebr"`, `"prime canais"`, `"apple tv"`
    - Adicionar keywords de delivery: substituir `"ifd*"` por `"ifd"` (sem wildcard) na categoria `"Delivery"`
    - Adicionar keywords de assinaturas à categoria `"Assinaturas"`: `"openai"`, `"notion"`, `"figma"`, `"digital ocean"`
    - Verificar consistência com `CATEGORY_KEYWORDS` em `classification_service.py` (módulo legado)
    - **NOTA**: A categoria `"Pedágio"` NÃO existe no sistema. Todas as keywords de pedágio devem ser adicionadas à categoria `"Transporte"` que já existe e é reconhecida pelo frontend
    - Arquivo: `finance-pilot/backend/categories.py`
    - _Bug_Condition: isBugCondition(X) where X.description matches ["nutag", "ifd*", "apple.com/bill", "amazonprimebr", "sem parar"]_
    - _Expected_Behavior: ClassificationService.classify() retorna categoria correta com needs_review=False_
    - _Preservation: Regras de workspace continuam com prioridade máxima; merchants sem keyword continuam retornando "Outros" com needs_review=True_
    - _Requirements: 2.8, 2.9, 2.10_

  - [x] 3.2 Corrigir matching de wildcard `ifd*` em `_match_default_keywords`
    - Confirmar que `"ifd*"` foi substituído por `"ifd"` (substring puro) no `DEFAULT_CATEGORIES`
    - O método `_match_default_keywords` usa `kw.lower() in desc_lower` — funciona corretamente com `"ifd"` como substring
    - Testar que `"IFD*RESTAURANTE XPTO"` → `"ifd"` está contido → categoria `"Delivery"`
    - Arquivo: `finance-pilot/backend/categories.py`
    - _Requirements: 2.9_

- [x] 4. Fix 1 — Gemini como caminho primário robusto

  - [x] 4.1 Reforçar o prompt `GEMINI_EXTRACTION_PROMPT` para PDFs Nubank
    - Substituir o prompt atual pelo prompt reforçado do design com instruções explícitas para:
      - Detectar `statement_type` pelo conteúdo ("fatura"/"cartão" → `credit_card`; "conta corrente"/"extrato" → `current_account`)
      - Datas em formato português (`"05 ABR 2026"`)
      - Valores em formato BRL (`"1.234,56"`)
      - Conta corrente: criar uma seção com `owner_name = holder_name`, incluir TODOS os movimentos
      - Cartão de crédito: criar uma seção por titular
    - Incluir exemplos concretos (few-shot) no prompt para melhorar a extração:
      - Exemplo de transação de cartão: `"05 ABR  UBER *TRIP  12,50"` → JSON
      - Exemplo de débito conta corrente: `"PIX enviado - João  -150,00"` → JSON com `is_refund=false`
      - Exemplo de crédito conta corrente: `"PIX recebido - Empresa  +3.500,00"` → JSON com `is_refund=true`
    - Semântica de `is_refund` para conta corrente no prompt:
      - `is_refund=False` para DÉBITOS (saídas de dinheiro: PIX enviado, pagamentos, boletos)
      - `is_refund=True` para CRÉDITOS (entradas: PIX recebido, salário, transferências recebidas)
    - Incluir `{schema}` no prompt para referência ao schema JSON
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 4.2 Usar `response_mime_type="application/json"` no config do Gemini
    - Adicionar `response_mime_type="application/json"` ao `GenerateContentConfig` em `_call_gemini`
    - Isso força o Gemini a retornar JSON estruturado, reduzindo erros de parsing e eliminando necessidade de strip de markdown fences
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Requirements: 2.1_

  - [x] 4.3 Adicionar validação pós-parse do resultado Gemini
    - Após `ExtractedStatement.model_validate_json(raw_json)`, verificar:
      - `len(validated.sections) > 0`
      - `any(len(s.transactions) > 0 for s in validated.sections)`
    - Se a validação falhar, lançar `ValueError` com mensagem descritiva para acionar retry
    - Isso garante que Gemini retornando JSON estruturalmente válido mas semanticamente vazio acione o fallback
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Bug_Condition: Gemini retorna JSON válido mas com sections vazias_
    - _Expected_Behavior: Retry é acionado; após 3 falhas, fallback pdfplumber é usado_
    - _Requirements: 2.1, 2.4, 2.5, 2.6_

- [x] 5. Fix 2 — Fallback pdfplumber corrigido

  - [x] 5.1 Implementar `_detect_statement_type()` com detecção dinâmica
    - Criar método `_detect_statement_type(self, text: str) -> Literal["credit_card", "current_account"]`
    - Sinais de cartão de crédito: `["fatura", "cartão", "vencimento", "limite", "parcela"]`
    - Sinais de conta corrente: `["conta corrente", "extrato", "saldo anterior", "saldo final", "pix enviado", "pix recebido"]`
    - Calcular score para cada tipo e retornar o vencedor; empate → `"credit_card"` (conservador)
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Bug_Condition: _fallback_pdfplumber retorna statement_type="credit_card" hardcoded para qualquer PDF_
    - _Expected_Behavior: statement_type detectado dinamicamente pelo conteúdo do PDF_
    - _Requirements: 2.3_

  - [x] 5.2 Corrigir regex de transações para layout real Nubank (cartão de crédito)
    - Substituir `tx_pattern` atual por padrão mais tolerante com `\s{2,}` para separar descrição do valor
    - Adicionar `tx_pattern_alt` como padrão alternativo para linhas com separação por tab ou alinhamento fixo
    - Testar com linhas reais do PDF `NU_45499351_01ABR2026_30ABR2026.pdf`
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Bug_Condition: tx_pattern falha com múltiplos espaços ou caracteres especiais nas descrições_
    - _Expected_Behavior: todas as transações do PDF real são extraídas_
    - _Requirements: 2.1_

  - [x] 5.3 Corrigir `_extract_holder_name()` com múltiplos padrões de regex
    - Adicionar padrões adicionais ao método existente:
      - `r"Fatura\s+de\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)+)"`
      - `r"Titular[:\s]+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)+)"`
      - `r"^([A-ZÀ-Ú]{2,}(?:\s+[A-ZÀ-Ú]{2,})+)\s*$"` (nome em CAPS)
    - Alterar fallback de `"Titular"` para `"Nubank"` (fallback seguro e não ambíguo)
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Bug_Condition: holder_name retorna "Titular" quando nenhum padrão é encontrado_
    - _Expected_Behavior: holder_name retorna nome real ou "Nubank" como fallback seguro_
    - _Requirements: 2.4_

  - [x] 5.4 Corrigir `_extract_period()` para derivar período das transações
    - Após tentativas de regex existentes, adicionar fallback que deriva período das transações já extraídas
    - `dates = [t.date for t in transactions if t.date and len(t.date) == 10]`
    - `return min(dates), max(dates)` se `dates` não estiver vazio
    - Último recurso: usar mês atual (não datas hardcoded de 2026)
    - Atualizar assinatura: `_extract_period(self, text: str, transactions: list = None)`
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Bug_Condition: period_start retorna "2026-01-01" hardcoded quando padrão não é encontrado_
    - _Expected_Behavior: period_start/period_end derivados das datas reais das transações_
    - _Requirements: 2.5_

  - [x] 5.5 Implementar `_fallback_pdfplumber_current_account()` para conta corrente
    - Criar método dedicado para extrair movimentações de conta corrente Nubank
    - Padrão de movimentação: `DD/MM/YYYY  DESCRIÇÃO  [+-]VALOR`
    - Implementar `_parse_ddmmyyyy(date_str)` para converter `"05/04/2026"` → `"2026-04-05"`
    - Semântica de `is_refund` para conta corrente:
      - `is_refund=False` para DÉBITOS (saídas de dinheiro: PIX enviado, pagamentos, boletos)
      - `is_refund=True` para CRÉDITOS (entradas: PIX recebido, salário, transferências recebidas)
    - `amount` sempre positivo; `amount_signed` calculado no momento da persistência
    - Derivar `period_start`/`period_end` das datas das transações extraídas
    - Retornar `ExtractedStatement` com `statement_type="current_account"`, `bank="Nubank"`
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Bug_Condition: fallback não possui lógica para conta corrente, retorna statement_type="credit_card"_
    - _Expected_Behavior: movimentações de CC extraídas corretamente com statement_type="current_account"_
    - _Requirements: 2.6, 2.7_

  - [x] 5.6 Refatorar `_fallback_pdfplumber()` para orquestrar por tipo detectado
    - Após extrair `full_text`, chamar `_detect_statement_type(full_text)`
    - Se `"current_account"`: delegar para `_fallback_pdfplumber_current_account(full_text)`
    - Se `"credit_card"`: manter lógica atual (renomear para `_fallback_pdfplumber_credit_card`)
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Requirements: 2.3, 2.6_

  - [x] 5.7 Corrigir `_extract_sections()` para capturar transações do titular principal
    - O código atual busca por `"NOME - final XXXX"` e extrai seções por titular adicional
    - O titular PRINCIPAL não tem sufixo "- final XXXX", então suas transações ficam ANTES da primeira seção encontrada e são perdidas
    - Adicionar lógica para capturar o texto entre o início do bloco de transações e o primeiro match de seção como a seção do titular principal
    - Extrair transações do `primary_text = text[:matches[0].start()]` usando `_extract_transactions_from_text`
    - Se houver transações no bloco primário, criar seção com `owner_name = holder_name` e inseri-la como primeira seção
    - Arquivo: `finance-pilot/backend/extraction_service.py`
    - _Bug_Condition: _extract_sections perde transações do titular principal que aparecem antes da primeira seção "- final XXXX"_
    - _Expected_Behavior: transações do titular principal são capturadas na primeira seção_
    - _Requirements: 2.1, 2.2_

- [x] 6. Fix 7 — `_process_chunk` para conta corrente em `processor.py`

  - [x] 6.1 Adicionar parâmetro `allow_negative` ao `_process_chunk`
    - Adicionar `allow_negative: bool = False` à assinatura do método
    - Substituir `if amount < 0: continue` por `if amount < 0 and not allow_negative: continue`
    - Para conta corrente: `amount = abs(amount)` para manter consistência no campo `amount`
    - Verificar se o endpoint `/current-account/upload` usa `process_file` ou endpoint dedicado
    - Se `process_file` for usado para CSV de conta corrente, passar `allow_negative=True`
    - Arquivo: `finance-pilot/backend/processor.py`
    - _Bug_Condition: _process_chunk descarta valores negativos (débitos legítimos de conta corrente)_
    - _Expected_Behavior: débitos de conta corrente são preservados com amount positivo_
    - _Preservation: CSV de cartão de crédito continua descartando valores negativos (estornos)_
    - _Requirements: 2.7, 3.1_

- [x] 7. Fix 5 — `upload_history` com metadados reais e contrato da API

  - [x] 7.1 Adicionar `statement_type` e `bank` ao `UploadConfirmRequest`
    - Adicionar campos ao modelo Pydantic em `main.py`:
      ```python
      statement_type: Literal["credit_card", "current_account"] = "credit_card"
      bank: Optional[str] = None
      ```
    - Arquivo: `finance-pilot/backend/main.py`
    - _Bug_Condition: UploadConfirmRequest não carrega statement_type nem bank_
    - _Requirements: 2.14_

  - [x] 7.2 Usar `body.statement_type` e `body.bank` no INSERT de `upload_history`
    - Localizar o INSERT de `upload_history` no endpoint `upload_confirm`
    - Substituir `"credit_card"` hardcoded por `body.statement_type`
    - Substituir `None` hardcoded por `body.bank`
    - Arquivo: `finance-pilot/backend/main.py`
    - _Bug_Condition: upload_history.statement_type = "credit_card" hardcoded; upload_history.bank = None_
    - _Expected_Behavior: upload_history contém statement_type e bank reais do PDF extraído_
    - _Preservation: upload_history continua sendo registrado com status="completed" e contagem correta_
    - _Requirements: 2.14, 3.11_

  - [x] 7.3 Atualizar frontend para enviar `statement_type` e `bank` no body do confirm
    - Arquivo: `finance-pilot/frontend/app/(app)/upload/page.tsx`
    - O `UploadPreviewResponse` já retorna `statement_type` e `bank`
    - Ao chamar `POST /upload/confirm`, incluir esses campos no body da requisição:
      ```typescript
      const confirmBody = {
        file_hash: previewData.file_hash,
        statement_type: previewData.statement_type,  // NOVO
        bank: previewData.bank,                       // NOVO
        transactions: confirmedTransactions,
      };
      ```
    - Isso é uma mudança no contrato da API que requer atualização no frontend
    - _Requirements: 2.14_

- [x] 8. Fix 6 — Roteamento por `statement_type` no confirm

  - [x] 8.1 Implementar roteamento condicional no endpoint `upload_confirm`
    - Localizar o loop de persistência de transações no endpoint `upload_confirm` em `main.py`
    - Adicionar bloco condicional: `if body.statement_type == "current_account":`
    - Para conta corrente: INSERT em `current_account_movements` com campos:
      - `tenant_id`, `owner`, `movement_id` (`f"pdf-{tx_id}"`), `date`, `month_ref`
      - `amount_signed`: negativo para débitos (`not tx.is_refund`), positivo para créditos (`tx.is_refund`)
      - Semântica: `is_refund=False` → DÉBITO (saída) → `amount_signed = -tx.amount`
      - Semântica: `is_refund=True` → CRÉDITO (entrada) → `amount_signed = +tx.amount`
      - `description`, `source_file` (`f"pdf_{body.file_hash[:8]}"`), `is_card_invoice_payment=0`
    - Para cartão de crédito: manter lógica atual de INSERT em `transactions_gold`
    - **NOTA sobre campo `owner`**: Para conta corrente, o frontend deve preencher `owner` com o `holder_name` retornado pelo `UploadPreviewResponse` (derivado do `ExtractedStatement.holder_name`). O backend usa `tx.owner` diretamente no INSERT, então a responsabilidade de preencher corretamente é do frontend na tela de confirmação.
    - Arquivo: `finance-pilot/backend/main.py`
    - _Bug_Condition: upload_confirm salva todas as transações em transactions_gold independente do statement_type_
    - _Expected_Behavior: current_account → current_account_movements; credit_card → transactions_gold_
    - _Preservation: fluxo de cartão de crédito inalterado; upload_history continua sendo registrado_
    - _Requirements: 2.16, 3.11_

- [x] 9. Fix 4 — Adicionar inserção BigQuery no bloco cloud

  - [x] 9.1 Adicionar inserção BigQuery no endpoint `upload_confirm` (modo cloud)
    - **NOTA**: O Firestore JÁ está correto e recebe payload completo com campos SaaS (`card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id`, `needs_review`). O fix é ADICIONAR a inserção no BigQuery que está AUSENTE — não é necessário corrigir o Firestore.
    - Localizar o bloco cloud (Firestore) no endpoint `upload_confirm` em `main.py`
    - Acumular `all_tx_payloads` durante o loop de transações (usar o mesmo `payload` dict já construído para Firestore)
    - Após `batch.commit()` do Firestore, construir `bq_rows` com todos os campos SaaS:
      - `id`, `tenant_id`, `date`, `month_ref`, `amount`, `merchant_clean`, `category`, `subcategory`, `owner`, `type`, `created_at`
      - `card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id`, `needs_review`
    - Chamar `bq_client.insert_rows_json(TABLE_GOLD, bq_rows)` com tratamento de erros
    - Se `bq_client` for `None`, pular a inserção (graceful degradation)
    - Arquivo: `finance-pilot/backend/main.py`
    - _Bug_Condition: bloco cloud do upload_confirm envia para Firestore mas NÃO insere no BigQuery_
    - _Expected_Behavior: todos os campos SaaS presentes no payload BigQuery (além do Firestore que já funciona)_
    - _Preservation: fluxo SQLite inalterado; Firestore continua sendo atualizado normalmente_
    - _Requirements: 2.13_

- [x] 10. Verificar que o teste de bug condition (Property 1) agora passa

  - [x] 10.1 Re-executar o teste de bug condition exploration do passo 1
    - **Property 1: Expected Behavior** - Extração, Classificação e Persistência Corrigidas
    - **IMPORTANT**: Re-executar o MESMO teste do passo 1 — NÃO escrever um novo teste
    - O teste do passo 1 codifica o comportamento esperado
    - Quando este teste passar, confirma que o comportamento esperado foi satisfeito
    - Executar: `pytest finance-pilot/backend/tests/test_bug_condition_exploration.py -v`
    - **EXPECTED OUTCOME**: Todos os testes PASSAM (confirma que os bugs foram corrigidos)
    - Se algum teste ainda falhar, revisar o fix correspondente antes de prosseguir
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.13, 2.14, 2.16_

  - [x] 10.2 Re-executar os testes de preservation do passo 2
    - **Property 2: Preservation** - Comportamentos Inalterados Confirmados
    - **IMPORTANT**: Re-executar os MESMOS testes do passo 2 — NÃO escrever novos testes
    - Executar: `pytest finance-pilot/backend/tests/test_preservation.py -v`
    - **EXPECTED OUTCOME**: Todos os testes PASSAM (confirma que não há regressões)
    - Se algum teste falhar, revisar o fix correspondente para garantir que o comportamento preservado não foi alterado
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12_

- [x] 11. Testes de integração com PDFs reais

  - [x] 11.1 Criar testes de integração com os PDFs reais da pasta `data/`
    - Criar `finance-pilot/backend/tests/test_integration_pdf_upload.py`
    - **Teste 1 — Fallback CC com PDF real**:
      - Ler `data/NU_45499351_01ABR2026_30ABR2026.pdf`
      - Mockar Gemini para falhar nas 3 tentativas
      - Chamar `ExtractionService().extract(pdf_bytes)`
      - Assertar: `result.statement_type == "credit_card"`
      - Assertar: `result.holder_name not in ["Titular", "", None]`
      - Assertar: `result.period_start != "2026-01-01"`
      - Assertar: `len(result.sections) > 0`
      - Assertar: `sum(len(s.transactions) for s in result.sections) > 0`
    - **Teste 2 — Conta corrente com PDF real**:
      - Ler `data/Nubank_2026-05-04.pdf`
      - Mockar Gemini para falhar (forçar fallback)
      - Chamar `ExtractionService().extract(pdf_bytes)`
      - Assertar: `result.statement_type == "current_account"`
      - Assertar: `result.bank == "Nubank"`
      - Assertar: `len(result.sections[0].transactions) > 0`
      - Verificar semântica de `is_refund`:
        - Transações de débito (PIX enviado, pagamentos): `is_refund == False`
        - Transações de crédito (PIX recebido, salário): `is_refund == True`
    - **Teste 3 — Fluxo completo preview → confirm (cartão de crédito)**:
      - Usar TestClient para `POST /upload` com `NU_45499351_01ABR2026_30ABR2026.pdf`
      - Verificar resposta de preview: `statement_type`, `bank`, `holder_name`, `transactions`
      - Chamar `POST /upload/confirm` com `statement_type` e `bank` do preview
      - Verificar `upload_history` no SQLite: `statement_type` e `bank` corretos
      - Verificar que transações foram salvas em `transactions_gold`
    - **Teste 4 — Fluxo completo preview → confirm (conta corrente)**:
      - Usar TestClient para `POST /upload` com `Nubank_2026-05-04.pdf`
      - Verificar resposta de preview: `statement_type == "current_account"`
      - Chamar `POST /upload/confirm` com `statement_type = "current_account"`
      - Verificar que movimentações foram salvas em `current_account_movements`
      - Verificar que `transactions_gold` NÃO foi alterado
      - Verificar semântica de `amount_signed`: negativo para débitos, positivo para créditos
    - **Teste 5 — Classificação de merchant NuTag no fluxo completo**:
      - Simular transação com `description = "NuTag 0001 Rodovia SP-330"` no preview
      - Verificar `suggested_category == "Transporte"` e `needs_review == False`
    - **Teste 6 — Regressão CSV inalterado**:
      - Usar TestClient para `POST /upload` com `data/fatura_victor_2026-03.csv`
      - Verificar que o fluxo CSV continua funcionando sem alterações
      - Verificar que transações são salvas em `transactions_gold`
    - Executar: `pytest finance-pilot/backend/tests/test_integration_pdf_upload.py -v`
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.14, 2.16, 3.1_

- [x] 12. Checkpoint — Garantir que todos os testes passam

  - Executar a suite completa de testes: `pytest finance-pilot/backend/tests/ -v`
  - Verificar que todos os testes novos passam (bug condition, preservation, integração)
  - Verificar que todos os testes existentes continuam passando (sem regressões)
  - Se algum teste falhar, investigar e corrigir antes de considerar o bugfix completo
  - Perguntar ao usuário se houver dúvidas sobre comportamentos ambíguos
  - _Requirements: todos_
