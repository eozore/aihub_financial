# Bugfix Requirements Document

## Introduction

Após a implementação do primeiro bugfix spec (`.kiro/specs/pdf-upload-review/`), o processo de upload de PDFs bancários Nubank continua não funcionando corretamente com o modelo **Gemini 3.1 Flash Lite** (`gemini-3.1-flash-lite-preview`). Os problemas residuais estão concentrados em três áreas:

1. **Pipeline Gemini 2-stage ineficaz**: O prompt genérico (`GEMINI_RAW_PROMPT`) usado no Stage 1 não fornece instruções suficientes para o Flash Lite produzir JSON estruturado confiável, e o parser Stage 2 (`_parse_raw_to_extracted`) tem suposições frágeis sobre nomes de campos que o modelo pode não seguir.
2. **Ausência de `response_mime_type`**: O `_call_gemini` não usa `response_mime_type="application/json"`, fazendo com que o Flash Lite retorne texto livre com markdown fences que falham no parsing.
3. **Testes de integração com PDFs invertidos**: Os paths `_CC_PDF` e `_CA_PDF` no arquivo de testes estão trocados — o teste de cartão de crédito usa o PDF de conta corrente e vice-versa, mascarando falhas reais.
4. **Normalização de datas no preview distorce transações**: O endpoint `/upload` normaliza datas de transações de cartão de crédito para o mês de vencimento da fatura, alterando datas reais (ex: 28 MAR vira 28 MAI) e potencialmente gerando datas inválidas.

O objetivo é garantir que o upload funcione de ponta a ponta com o modelo `gemini-3.1-flash-lite-preview` para ambos os tipos de PDF (fatura de cartão e extrato de conta corrente).

---

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the ExtractionService processes a PDF using Gemini Flash Lite with the generic `GEMINI_RAW_PROMPT` ("Identify all fields...return as structured JSON") THEN the model returns free-form JSON with unpredictable field names (e.g., `"customer_name"` vs `"holder_name"`, `"billing_period"` vs `"period"`) causing `_parse_raw_to_extracted()` to fail silently and produce empty transactions or incorrect metadata

1.2 WHEN the `_call_gemini` method sends a request to Gemini Flash Lite without `response_mime_type="application/json"` in the GenerateContentConfig THEN the model wraps its response in markdown code fences (```json...```) or includes explanatory text before/after the JSON, and the manual fence-stripping logic fails for edge cases (e.g., nested fences, partial fences), causing `json.loads()` to raise an exception on all 3 retry attempts

1.3 WHEN the detailed `GEMINI_EXTRACTION_PROMPT` (with Nubank-specific instructions, few-shot examples, and explicit JSON schema) is defined in `extraction_service.py` THEN it is never used in the primary extraction path — the code always uses `GEMINI_RAW_PROMPT` for Stage 1, making the detailed prompt dead code

1.4 WHEN `_parse_raw_to_extracted()` processes the raw JSON from Flash Lite for a credit card statement THEN it looks for transactions in `raw_dict.get("transactions", [])` at the top level, but Flash Lite may nest transactions inside sections (e.g., `raw_dict["sections"][0]["transactions"]` or `raw_dict["card_holders"][0]["transactions"]`), resulting in zero transactions extracted even when the model returned valid data

1.5 WHEN `_parse_raw_to_extracted()` processes the raw JSON from Flash Lite for a current account statement THEN it fails to extract transactions because the model may use different field names for amounts (e.g., `"value"` instead of `"amount"`, `"valor"` instead of `"amount"`) and dates (e.g., `"data"` instead of `"date"`), resulting in transactions with `amount=0.0` or `date="2026-01-01"`

1.6 WHEN the integration test file `test_integration_pdf_upload.py` defines `_CC_PDF = Nubank_2026-05-04.pdf` and `_CA_PDF = NU_45499351_01ABR2026_30ABR2026.pdf` THEN the paths are SWAPPED — `Nubank_2026-05-04.pdf` is actually the current account statement and `NU_45499351_01ABR2026_30ABR2026.pdf` is the credit card statement — causing tests to pass with wrong assertions or fail for the wrong reasons

1.7 WHEN the `/upload` preview endpoint processes a credit card PDF and normalizes transaction dates to the billing month (due_date month) THEN transactions from the previous billing cycle (e.g., "28 MAR" on a MAY invoice) have their dates changed to the billing month (e.g., "2026-05-28"), losing the original transaction date and potentially creating invalid dates (e.g., Feb 30)

1.8 WHEN `_parse_raw_to_extracted()` attempts to detect `statement_type` by scoring signal words in the raw JSON string THEN it may misclassify because the raw JSON from Flash Lite contains the prompt instructions echoed back or metadata fields that contain both credit card and current account keywords, leading to incorrect type detection

### Expected Behavior (Correct)

2.1 WHEN the ExtractionService processes a PDF using Gemini Flash Lite THEN the system SHALL use the detailed `GEMINI_EXTRACTION_PROMPT` (with Nubank-specific instructions, explicit JSON schema, few-shot examples, and exclusion rules) as the primary prompt instead of the generic `GEMINI_RAW_PROMPT`, ensuring the model returns structured JSON matching the expected schema

2.2 WHEN the `_call_gemini` method sends a request to Gemini Flash Lite THEN the system SHALL include `response_mime_type="application/json"` in the GenerateContentConfig to force the model to return pure JSON without markdown fences or explanatory text

2.3 WHEN the ExtractionService receives JSON from Gemini Flash Lite THEN the system SHALL attempt to parse the response directly as an `ExtractedStatement` (using `model_validate` or equivalent) before falling back to the `_parse_raw_to_extracted()` heuristic parser, ensuring that well-structured responses are handled efficiently

2.4 WHEN `_parse_raw_to_extracted()` processes raw JSON that has transactions nested inside sections or card holder groups THEN the system SHALL search for transactions at multiple levels (top-level `"transactions"`, inside `"sections"`, inside `"card_holders"`, inside `"movements"`) to maximize extraction success regardless of the model's chosen structure

2.5 WHEN `_parse_raw_to_extracted()` processes individual transaction objects THEN the system SHALL recognize multiple field name variants for amount (`"amount"`, `"value"`, `"valor"`, `"total"`), date (`"date"`, `"data"`, `"transaction_date"`), and description (`"description"`, `"descricao"`, `"merchant"`, `"name"`) to handle Flash Lite's variable output format

2.6 WHEN the integration test file defines PDF paths THEN the system SHALL correctly map `_CC_PDF` to `NU_45499351_01ABR2026_30ABR2026.pdf` (credit card fatura) and `_CA_PDF` to `Nubank_2026-05-04.pdf` (current account extrato) matching the actual content of each file

2.7 WHEN the `/upload` preview endpoint processes a credit card PDF THEN the system SHALL preserve the original transaction dates as extracted from the PDF and use the billing `month_ref` only for the `month_ref` field (for grouping/filtering purposes), without altering the actual `date` field of each transaction

2.8 WHEN `_parse_raw_to_extracted()` detects the statement type THEN the system SHALL base the detection on the original PDF content signals (passed as metadata or detected from transaction patterns) rather than scoring keywords in the raw JSON string which may contain echoed prompt text

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the Gemini model returns valid JSON that matches the ExtractedStatement schema on the first attempt THEN the system SHALL CONTINUE TO return the validated result without triggering retries or the pdfplumber fallback

3.2 WHEN the Gemini model fails on all 3 retry attempts THEN the system SHALL CONTINUE TO fall back to the pdfplumber extraction pipeline with exponential backoff (1s, 2s delays)

3.3 WHEN the same PDF is processed twice within the same instance THEN the system SHALL CONTINUE TO return the cached result from `self._cache` without calling Gemini again

3.4 WHEN a CSV file is uploaded via `POST /upload` THEN the system SHALL CONTINUE TO process it using the pandas-based CSV parsing flow without any changes to the CSV path behavior

3.5 WHEN the ClassificationService classifies a merchant THEN the system SHALL CONTINUE TO use the unified `DEFAULT_CATEGORIES` keywords with workspace rules having highest priority

3.6 WHEN `POST /upload/confirm` receives transactions with `statement_type="current_account"` THEN the system SHALL CONTINUE TO persist them in `current_account_movements` (not `transactions_gold`)

3.7 WHEN `POST /upload/confirm` receives transactions with `statement_type="credit_card"` THEN the system SHALL CONTINUE TO persist them in `transactions_gold` with all SaaS fields (`card_last4`, `card_type`, `is_refund`, `transaction_source`, `upload_id`, `needs_review`)

3.8 WHEN the upload file exceeds 10 MB or has an invalid extension THEN the system SHALL CONTINUE TO reject the upload with HTTP 413 or HTTP 400 respectively

3.9 WHEN the monthly upload limit for the plan is reached THEN the system SHALL CONTINUE TO reject the upload with HTTP 402 before processing

---

## Bug Condition (Bug Condition Methodology)

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type PDFUploadInput {pdf_bytes, filename, model}
  OUTPUT: boolean

  // Bug triggers when using Gemini Flash Lite with the generic prompt
  // and the 2-stage pipeline fails to produce valid structured output
  RETURN (
    // Primary bug: generic prompt + no response_mime_type + fragile parser
    (X.model = "gemini-3.1-flash-lite-preview"
     AND prompt_used = GEMINI_RAW_PROMPT
     AND (
       response_has_markdown_fences(X)
       OR transactions_nested_in_sections(X)
       OR field_names_non_standard(X)
     ))
    OR
    // Test infrastructure bug: swapped PDF paths
    (X.context = "integration_test"
     AND pdf_path_assignment_swapped(X))
    OR
    // Date normalization bug: dates altered in preview
    (X.statement_type = "credit_card"
     AND billing_month != transaction_month
     AND date_normalized_to_billing_month(X))
  )
END FUNCTION
```

### Property Specification (Fix Checking)

```pascal
// Property: Fix Checking — Gemini Flash Lite produces valid extraction
FOR ALL X WHERE isBugCondition(X) DO
  result ← ExtractionService'.extract(X.pdf_bytes)
  ASSERT (
    result.sections IS NOT EMPTY
    AND ANY section IN result.sections: section.transactions IS NOT EMPTY
    AND result.statement_type IN ["credit_card", "current_account"]
    AND result.holder_name NOT IN ["Unknown", "", None]
    AND result.period_start matches YYYY-MM-DD format
    AND ALL tx IN result.all_transactions: tx.amount > 0
    AND ALL tx IN result.all_transactions: tx.date matches YYYY-MM-DD format
    AND ALL tx IN result.all_transactions: tx.description IS NOT EMPTY
  )
END FOR
```

### Preservation Goal

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT ExtractionService(X) = ExtractionService'(X)
END FOR
```

This ensures that for all non-buggy inputs (CSV uploads, successful Gemini responses with standard structure, cached results), the fixed code behaves identically to the original.
