# PDF Upload Fix V2 — Bugfix Design

## Overview

The PDF upload pipeline for Nubank bank statements fails when using the `gemini-3.1-flash-lite-preview` model because: (1) the generic `GEMINI_RAW_PROMPT` is used instead of the detailed `GEMINI_EXTRACTION_PROMPT` that provides Nubank-specific instructions, (2) `response_mime_type="application/json"` is missing from the API call causing markdown fences in responses, (3) the `_parse_raw_to_extracted()` parser assumes a rigid top-level structure that Flash Lite may not follow, (4) integration test PDF paths are swapped masking real failures, and (5) date normalization in the preview endpoint distorts transaction dates by forcing them into the billing month.

The fix strategy is to switch to the detailed prompt with `response_mime_type`, attempt direct schema validation before heuristic parsing, make the parser resilient to field name variants and nested structures, correct the test paths, and remove date normalization from the preview endpoint.

## Glossary

- **Bug_Condition (C)**: The set of inputs where the Gemini Flash Lite extraction pipeline fails to produce valid structured output due to prompt/config/parser issues, OR where test infrastructure masks failures, OR where date normalization distorts transaction dates
- **Property (P)**: The desired behavior — valid `ExtractedStatement` with non-empty transactions, correct dates, and proper statement type detection
- **Preservation**: Existing behaviors that must remain unchanged — CSV upload flow, pdfplumber fallback, caching, plan limit checks, confirm endpoint persistence logic
- **`_call_gemini`**: The method in `extraction_service.py` that sends PDF bytes + prompt to the Gemini API and returns raw text
- **`_parse_raw_to_extracted`**: The method that converts free-form Gemini JSON into an `ExtractedStatement` Pydantic model
- **`GEMINI_RAW_PROMPT`**: Generic 4-line prompt currently used in Stage 1 — insufficient for Flash Lite
- **`GEMINI_EXTRACTION_PROMPT`**: Detailed prompt with Nubank-specific rules, few-shot examples, and JSON schema — currently dead code
- **`billing_month_ref`**: The year-month derived from `due_date` or `period_end` used to normalize transaction dates in the preview endpoint

## Bug Details

### Bug Condition

The bug manifests across five interrelated issues in the PDF upload pipeline. The primary failure path is: Flash Lite receives a vague prompt → returns unstructured or markdown-fenced JSON → parser fails to extract transactions → all 3 retries fail → fallback to pdfplumber (which works but defeats the purpose of using Gemini). Secondary issues in tests and date normalization compound the problem.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {pdf_bytes, model, context, statement_type}
  OUTPUT: boolean

  // Bug 1+2+3: Gemini pipeline produces invalid/empty extraction
  gemini_pipeline_fails :=
    input.model = "gemini-3.1-flash-lite-preview"
    AND prompt_used = GEMINI_RAW_PROMPT
    AND (
      response_contains_markdown_fences(input)
      OR transactions_at_top_level_empty(input)
      OR field_names_unrecognized(input)
    )

  // Bug 4: Test infrastructure has swapped PDF paths
  test_paths_swapped :=
    input.context = "integration_test"
    AND _CC_PDF points to "Nubank_2026-05-04.pdf"  // actually current account
    AND _CA_PDF points to "NU_45499351_01ABR2026_30ABR2026.pdf"  // actually credit card

  // Bug 5: Date normalization distorts transaction dates
  date_normalization_distorts :=
    input.statement_type = "credit_card"
    AND EXISTS tx IN transactions:
      tx.original_date[:7] != billing_month_ref
      AND tx.date is changed to billing_month_ref + day

  RETURN gemini_pipeline_fails OR test_paths_swapped OR date_normalization_distorts
END FUNCTION
```

### Examples

- **Example 1 (Prompt issue)**: Upload `NU_45499351_01ABR2026_30ABR2026.pdf` (credit card). Flash Lite receives "Identify all fields..." prompt → returns `{"document_info": {"customer_name": "Victor"}, "transactions": [...]}` with `"card_last_digits"` instead of `"card_last4"` and `"valor"` instead of `"amount"` → parser extracts 0 transactions → retries exhaust → falls back to pdfplumber.

- **Example 2 (Markdown fences)**: Flash Lite returns ````json\n{...}\n```` with nested triple backticks inside a description field → fence-stripping regex removes wrong lines → `json.loads()` fails → retry loop exhausts.

- **Example 3 (Nested transactions)**: Flash Lite returns `{"sections": [{"card_holder": "Victor", "transactions": [...]}]}` → `raw_dict.get("transactions", [])` returns empty list → 0 transactions extracted despite valid data being present.

- **Example 4 (Swapped tests)**: `test_fallback_credit_card_real_pdf()` loads `_CC_PDF = Nubank_2026-05-04.pdf` which is actually a current account PDF → test asserts `statement_type == "credit_card"` → may pass incorrectly or fail for wrong reason.

- **Example 5 (Date normalization)**: Credit card invoice due May 4, 2026. Transaction "28 MAR UBER *TRIP" has date `2026-03-28` → preview normalizes to `2026-05-28` → user sees wrong date → confirms → wrong date persisted in database.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- CSV upload flow (`file_type == "csv"` branch in `/upload`) must continue to work identically
- pdfplumber fallback must continue to work when Gemini fails all retries
- In-memory cache (`self._cache`) must continue to prevent redundant Gemini calls for the same PDF
- `POST /upload/confirm` persistence logic for both `transactions_gold` and `current_account_movements` must remain unchanged
- File validation (size limits, extension checks) must remain unchanged
- Plan limit checks (uploads/month) must remain unchanged
- Classification service behavior must remain unchanged
- Exponential backoff timing (1s, 2s) between retries must remain unchanged

**Scope:**
All inputs that do NOT involve the Gemini extraction pipeline bugs should be completely unaffected by this fix. This includes:
- CSV file uploads (no Gemini involvement)
- PDFs that hit the cache (no re-extraction)
- PDFs where Gemini returns a perfect `ExtractedStatement`-compatible JSON on first try (already works)
- All `/upload/confirm` requests regardless of source
- All non-upload API endpoints

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Wrong Prompt Selection**: In `ExtractionService.extract()`, the call `self._call_gemini(pdf_bytes, prompt=GEMINI_RAW_PROMPT)` uses the 4-line generic prompt. The detailed `GEMINI_EXTRACTION_PROMPT` (150+ lines with Nubank-specific rules, few-shot examples, exclusion patterns, and explicit JSON schema) exists in the same file but is never referenced in the primary extraction path. Flash Lite needs explicit guidance to produce consistent output.

2. **Missing `response_mime_type`**: In `_call_gemini()`, the `GenerateContentConfig` only sets `max_output_tokens` and `temperature`. Without `response_mime_type="application/json"`, Flash Lite may wrap output in markdown fences. The manual fence-stripping (`if raw_text.startswith("```")`) is fragile and fails for edge cases.

3. **Rigid Parser Assumptions**: `_parse_raw_to_extracted()` only looks for transactions at `raw_dict.get("transactions", [])`. Flash Lite with the generic prompt may nest them under `"sections"`, `"card_holders"`, or other keys. Additionally, it only recognizes `"amount"` (not `"value"`, `"valor"`) and `"date"` (not `"data"`, `"transaction_date"`).

4. **Swapped Test Paths**: The variable names `_CC_PDF` and `_CA_PDF` are assigned to the wrong files based on filename analysis — `NU_45499351_01ABR2026_30ABR2026.pdf` is the credit card fatura (contains "fatura" content) and `Nubank_2026-05-04.pdf` is the current account extrato.

5. **Aggressive Date Normalization**: The preview endpoint forces all credit card transaction dates into the billing month. This is incorrect — the `date` field should reflect when the purchase happened, while `month_ref` (used for grouping) can reflect the billing cycle. The normalization creates misleading data and potential invalid dates.

## Correctness Properties

Property 1: Bug Condition - Gemini Flash Lite Extraction Produces Valid Output

_For any_ PDF input processed by the fixed ExtractionService using `gemini-3.1-flash-lite-preview`, the extraction SHALL return an `ExtractedStatement` with at least one section containing at least one transaction, where each transaction has a valid ISO date (YYYY-MM-DD), a positive amount, and a non-empty description.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation - Non-Gemini Paths Unchanged

_For any_ input that does NOT trigger the Gemini extraction pipeline (CSV uploads, cached PDFs, confirm requests), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality for non-PDF-extraction paths.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**

Property 3: Bug Condition - Transaction Dates Preserved in Preview

_For any_ credit card PDF where transactions span multiple months, the fixed `/upload` preview endpoint SHALL return each transaction with its original extracted date unchanged, using `month_ref` only for grouping metadata.

**Validates: Requirements 2.7**

Property 4: Bug Condition - Integration Tests Use Correct PDFs

_For any_ execution of the integration test suite, `_CC_PDF` SHALL point to the actual credit card PDF and `_CA_PDF` SHALL point to the actual current account PDF, ensuring test assertions validate the correct document type.

**Validates: Requirements 2.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `finance-pilot/backend/extraction_service.py`

**Function**: `ExtractionService.extract()` and `_call_gemini()`

**Specific Changes**:

1. **Switch to detailed prompt**: Change the `_call_gemini` call in `extract()` from `prompt=GEMINI_RAW_PROMPT` to `prompt=GEMINI_EXTRACTION_PROMPT`. This gives Flash Lite the Nubank-specific instructions, few-shot examples, and explicit JSON schema it needs.

2. **Add `response_mime_type`**: In `_call_gemini()`, add `response_mime_type="application/json"` to the `GenerateContentConfig`. This forces the model to return pure JSON without markdown fences, eliminating the need for fragile fence-stripping logic.

3. **Try direct schema validation first**: In `extract()`, after receiving the JSON from Gemini, attempt to validate it directly as an `ExtractedStatement` using Pydantic's `model_validate()`. Only fall back to `_parse_raw_to_extracted()` if direct validation fails. This handles the case where Flash Lite returns perfectly structured output matching the schema.

4. **Make parser resilient to nested structures**: In `_parse_raw_to_extracted()`, search for transactions at multiple levels: `raw_dict.get("transactions")`, inside `raw_dict.get("sections", [])`, inside `raw_dict.get("card_holders", [])`, and inside `raw_dict.get("movements", [])`.

5. **Recognize field name variants**: In `_parse_raw_to_extracted()`, when extracting individual transaction fields, check multiple key names: amount → `["amount", "value", "valor", "total"]`, date → `["date", "data", "transaction_date"]`, description → `["description", "descricao", "merchant", "name"]`.

---

**File**: `finance-pilot/backend/tests/test_integration_pdf_upload.py`

**Variables**: `_CC_PDF` and `_CA_PDF`

**Specific Changes**:

6. **Swap PDF path assignments**: Change `_CC_PDF` to point to `NU_45499351_01ABR2026_30ABR2026.pdf` (the actual credit card fatura) and `_CA_PDF` to point to `Nubank_2026-05-04.pdf` (the actual current account extrato).

---

**File**: `finance-pilot/backend/main.py`

**Function**: `upload_preview()` (the `/upload` POST endpoint)

**Specific Changes**:

7. **Remove date normalization**: Remove the block that normalizes `tx_date` to `billing_month_ref` for credit card statements. Instead, pass through the original `tx.date` unchanged. The `month_ref` field (used for grouping in the confirm step) can still be derived from the billing period without altering individual transaction dates.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that mock Gemini to return realistic Flash Lite responses (with nested structures, field name variants, and markdown fences) and verify that the current code fails to extract transactions. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **Generic Prompt Test**: Mock Gemini returning JSON with `"customer_name"` instead of `"holder_name"` and transactions nested in `"sections"` — verify current parser returns 0 transactions (will fail on unfixed code)
2. **Markdown Fences Test**: Mock Gemini returning response wrapped in ````json ... ```` — verify current code fails to parse when fences contain nested backticks (will fail on unfixed code)
3. **Field Name Variants Test**: Mock Gemini returning transactions with `"valor"` instead of `"amount"` and `"data"` instead of `"date"` — verify current parser produces `amount=0.0` (will fail on unfixed code)
4. **Date Normalization Test**: Create a credit card extraction with transactions from March on a May invoice — verify current preview changes dates to May (will demonstrate the bug on unfixed code)

**Expected Counterexamples**:
- Parser returns empty transactions list despite valid data being present in nested structures
- `json.loads()` raises exception on markdown-fenced responses with edge cases
- Transaction amounts are 0.0 and dates default to `"2026-01-01"` due to unrecognized field names

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := ExtractionService_fixed.extract(input.pdf_bytes)
  ASSERT result.sections IS NOT EMPTY
  ASSERT ANY section: len(section.transactions) > 0
  ASSERT ALL tx: tx.amount > 0
  ASSERT ALL tx: tx.date matches YYYY-MM-DD
  ASSERT ALL tx: tx.description IS NOT EMPTY
  ASSERT result.statement_type IN ["credit_card", "current_account"]
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT ExtractionService_original.extract(input) = ExtractionService_fixed.extract(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (various JSON structures, field combinations)
- It catches edge cases that manual unit tests might miss (unusual field name combinations, empty sections)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for CSV uploads, cached results, and confirm requests, then write property-based tests capturing that behavior.

**Test Cases**:
1. **CSV Upload Preservation**: Verify CSV upload flow produces identical preview responses before and after fix
2. **Cache Preservation**: Verify that cached PDF results are returned without re-extraction
3. **Confirm Endpoint Preservation**: Verify that `/upload/confirm` persists transactions identically for both statement types
4. **Fallback Preservation**: Verify pdfplumber fallback continues to work when Gemini fails all retries

### Unit Tests

- Test `_call_gemini` with `response_mime_type` produces clean JSON (mock Gemini client)
- Test `_parse_raw_to_extracted` with nested transaction structures
- Test `_parse_raw_to_extracted` with field name variants (`valor`, `data`, `descricao`)
- Test direct `ExtractedStatement` validation path (well-formed Gemini response)
- Test that preview endpoint preserves original transaction dates
- Test integration test PDF path assignments match actual file content

### Property-Based Tests

- Generate random valid `ExtractedStatement` JSON structures and verify the parser extracts all transactions correctly regardless of nesting level
- Generate random transaction field name combinations from the recognized variants and verify amounts/dates/descriptions are extracted
- Generate random credit card statements with transactions spanning multiple months and verify dates are preserved unchanged in preview

### Integration Tests

- Test full extraction pipeline with real PDFs using mocked Gemini returning detailed-prompt-compatible JSON
- Test fallback path still works end-to-end when Gemini is unavailable
- Test preview → confirm flow with corrected test PDF paths
- Test that CSV upload regression suite continues to pass unchanged
