# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Gemini Flash Lite Extraction Pipeline Fails
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the Gemini extraction pipeline bug
  - **Scoped PBT Approach**: Use Hypothesis to generate realistic Flash Lite responses with:
    - Transactions nested inside `"sections"` or `"card_holders"` (not at top level)
    - Field name variants: `"valor"` instead of `"amount"`, `"data"` instead of `"date"`, `"descricao"` instead of `"description"`
    - Markdown fences wrapping JSON responses (```json ... ```)
  - Test file: `finance-pilot/backend/tests/test_bug_condition_exploration.py`
  - Mock `_call_gemini` to return JSON with nested structures and variant field names
  - Assert that `ExtractionService.extract()` returns an `ExtractedStatement` with:
    - At least one section containing at least one transaction
    - All transactions have `amount > 0`
    - All transactions have a valid ISO date (YYYY-MM-DD, not "2026-01-01" default)
    - All transactions have a non-empty description
    - `statement_type` is correctly detected
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (parser returns 0 transactions or default values due to nested structures and unrecognized field names)
  - Document counterexamples: e.g., `_parse_raw_to_extracted({"sections": [{"transactions": [...]}]})` returns empty sections
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.8_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Gemini Paths Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `finance-pilot/backend/tests/test_preservation.py`
  - Observe on UNFIXED code:
    - CSV upload via `/upload` produces a valid preview response with transactions
    - Cached PDF results are returned without re-calling Gemini
    - pdfplumber fallback produces valid `ExtractedStatement` when Gemini fails
    - `/upload/confirm` persists credit card transactions to `transactions_gold`
    - `/upload/confirm` persists current account movements to `current_account_movements`
  - Write property-based tests using Hypothesis:
    - **CSV path preservation**: For any valid CSV content, the upload preview returns transactions with correct structure (no Gemini involvement)
    - **Cache preservation**: For any PDF processed once, a second call returns the cached result without invoking `_call_gemini` again
    - **Fallback preservation**: When `_call_gemini` raises an exception on all retries, `extract()` falls back to pdfplumber and returns a valid `ExtractedStatement`
    - **Confirm persistence preservation**: For any valid `UploadConfirmRequest`, the confirm endpoint persists the correct number of records to the correct table
  - Verify tests PASS on UNFIXED code (confirms baseline behavior to preserve)
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [ ] 3. Fix Gemini extraction pipeline and related bugs

  - [x] 3.1 Switch `extract()` from `GEMINI_RAW_PROMPT` to `GEMINI_EXTRACTION_PROMPT`
    - In `ExtractionService.extract()`, change `prompt=GEMINI_RAW_PROMPT` to `prompt=GEMINI_EXTRACTION_PROMPT`
    - This gives Flash Lite the Nubank-specific instructions, few-shot examples, and explicit JSON schema
    - _Bug_Condition: isBugCondition(input) where prompt_used = GEMINI_RAW_PROMPT AND model = "gemini-3.1-flash-lite-preview"_
    - _Expected_Behavior: Flash Lite receives detailed prompt and returns structured JSON matching ExtractedStatement schema_
    - _Preservation: Fallback to pdfplumber still triggered when Gemini fails all 3 retries_
    - _Requirements: 2.1, 1.1, 1.3_

  - [x] 3.2 Add `response_mime_type="application/json"` to `_call_gemini()` config
    - In `_call_gemini()`, add `response_mime_type="application/json"` to the `GenerateContentConfig`
    - This forces the model to return pure JSON without markdown fences
    - The existing fence-stripping logic can remain as a safety net but should no longer be needed
    - _Bug_Condition: isBugCondition(input) where response_contains_markdown_fences(input)_
    - _Expected_Behavior: Gemini returns clean JSON without markdown fences; json.loads() succeeds on first parse_
    - _Preservation: max_output_tokens=65536 and temperature=0 remain unchanged_
    - _Requirements: 2.2, 1.2_

  - [x] 3.3 Try direct `ExtractedStatement` schema validation before `_parse_raw_to_extracted()` fallback
    - In `extract()`, after `json.loads(raw_json_str)`, attempt `ExtractedStatement.model_validate(raw_dict)`
    - If validation succeeds AND has non-empty transactions, use the validated result directly
    - If validation fails (ValidationError), fall back to `_parse_raw_to_extracted(raw_dict)`
    - _Bug_Condition: When Flash Lite returns perfectly structured JSON matching the schema, the current code still runs through the lossy heuristic parser_
    - _Expected_Behavior: Well-structured responses are handled efficiently via direct validation_
    - _Preservation: _parse_raw_to_extracted() still used as fallback for non-conforming responses_
    - _Requirements: 2.3_

  - [x] 3.4 Make `_parse_raw_to_extracted()` resilient to nested structures and field name variants
    - Search for transactions at multiple levels:
      - `raw_dict.get("transactions", [])`
      - Inside `raw_dict.get("sections", [])` → each section's `"transactions"`
      - Inside `raw_dict.get("card_holders", [])` → each holder's `"transactions"`
      - Inside `raw_dict.get("movements", [])`
    - Recognize field name variants for each transaction:
      - amount: `["amount", "value", "valor", "total"]`
      - date: `["date", "data", "transaction_date"]`
      - description: `["description", "descricao", "merchant", "name"]`
    - _Bug_Condition: isBugCondition(input) where transactions_nested_in_sections(input) OR field_names_non_standard(input)_
    - _Expected_Behavior: Parser extracts transactions regardless of nesting level or field name variant used_
    - _Preservation: Existing top-level "transactions" path still works as before_
    - _Requirements: 2.4, 2.5, 1.4, 1.5_

  - [x] 3.5 Fix swapped PDF paths in `test_integration_pdf_upload.py`
    - Change `_CC_PDF` to point to `NU_45499351_01ABR2026_30ABR2026.pdf` (credit card fatura)
    - Change `_CA_PDF` to point to `Nubank_2026-05-04.pdf` (current account extrato)
    - _Bug_Condition: isBugCondition(input) where pdf_path_assignment_swapped(input)_
    - _Expected_Behavior: _CC_PDF points to actual credit card PDF, _CA_PDF points to actual current account PDF_
    - _Preservation: All test assertions remain valid with correct PDF assignments_
    - _Requirements: 2.6, 1.6_

  - [x] 3.6 Remove date normalization from the `/upload` preview endpoint in `main.py`
    - Remove the block that normalizes `tx_date` to `billing_month_ref` (lines ~2001-2019 in main.py)
    - Pass through `tx.date` unchanged to `PreviewTransaction`
    - The `month_ref` field for grouping can still be derived from billing period in the confirm step
    - _Bug_Condition: isBugCondition(input) where date_normalized_to_billing_month(input)_
    - _Expected_Behavior: Transaction dates preserved as extracted; month_ref used only for grouping metadata_
    - _Preservation: month_ref derivation for confirm step remains unchanged_
    - _Requirements: 2.7, 1.7_

  - [x] 3.7 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Gemini Flash Lite Extraction Produces Valid Output
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (valid extraction with non-empty transactions)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — parser now handles nested structures and field variants)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.8 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Gemini Paths Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in CSV upload, caching, fallback, confirm persistence)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest finance-pilot/backend/tests/ -v`
  - Ensure bug condition exploration test (task 1) now PASSES
  - Ensure preservation tests (task 2) still PASS
  - Ensure integration tests with corrected PDF paths PASS
  - Ensure CSV regression test still PASSES
  - Ask the user if questions arise
