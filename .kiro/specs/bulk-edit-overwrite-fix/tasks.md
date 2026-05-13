# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Enrichment Overwrites User-Edited Owner/Type Fields
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate `enrich_card_data()` unconditionally overwrites non-NULL owner/type fields
  - **Scoped PBT Approach**: Use Hypothesis to generate transactions with non-NULL owner and/or type fields that have a matching card_last4 in the card map. Assert that enrichment preserves the non-NULL values.
  - Test file: `finance-pilot/backend/tests/test_enrichment_bug_condition.py`
  - Property: For all transactions where `card_last4 IN card_map AND (owner IS NOT NULL OR type IS NOT NULL)`, assert `enrich_card_data(tx, card_map).owner == tx.owner` when `tx.owner IS NOT NULL`, and `enrich_card_data(tx, card_map).type == tx.type` when `tx.type IS NOT NULL`
  - Also assert `card_type` is always enriched from card data (unconditional)
  - Include concrete deterministic cases: `{owner: "Victor", type: "individual", card_last4: "1234"}` with card map `{"1234": CardInfo("Maria", "shared")}`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists: enrichment returns owner="Maria" instead of preserving "Victor")
  - Document counterexamples found (e.g., "enrich_card_data({owner: 'Victor', card_last4: '1234'}, {'1234': CardInfo('Maria', 'shared')}) returns owner='Maria' instead of 'Victor'")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - NULL Fields Still Enriched From Card Data
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `finance-pilot/backend/tests/test_enrichment_preservation.py`
  - Observe: `enrich_card_data({owner: None, type: None, card_last4: "1234"}, {"1234": CardInfo("Maria", "shared")})` returns `{owner: "Maria", type: "shared", card_type: "shared"}` on unfixed code
  - Observe: `enrich_card_data({owner: "Victor", type: "individual", card_last4: "9999"}, {"1234": CardInfo("Maria", "shared")})` returns `{owner: "Victor", type: "individual"}` on unfixed code (no matching card)
  - Observe: `enrich_card_data({owner: None, type: None, card_last4: None}, {"1234": CardInfo("Maria", "shared")})` returns unchanged transaction on unfixed code
  - Write property-based test with Hypothesis: For all transactions where `NOT isBugCondition(tx)` (i.e., owner AND type are both NULL, OR card_last4 not in card_map), assert `enrich_card_data(tx, card_map)` produces the same result as the original function
  - Also write preservation property for `card_type`: For all transactions with matching card_last4, assert `card_type` is always set from card data regardless of owner/type values
  - Also write preservation property for `compute_month_ref()`: For transactions with NULL month_ref, assert month_ref is derived from date[:7]
  - Verify tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix for enrichment overwrite, month_ref overwrite, and dashboard inconsistency

  - [x] 3.1 Fix `enrich_card_data()` to only enrich NULL owner/type fields
    - In `finance-pilot/backend/enrichment_service.py`, modify `enrich_card_data()` method
    - Change `result["owner"] = card_info.owner` to only set when `result.get("owner")` is None or empty
    - Change `result["type"] = card_info.card_type` to only set when `result.get("type")` is None or empty
    - Keep `result["card_type"] = card_info.card_type` unconditional (card_type is metadata, always enriched)
    - _Bug_Condition: isBugCondition(input) where input.transaction.card_last4 IN card_map AND (input.transaction.owner IS NOT NULL OR input.transaction.type IS NOT NULL)_
    - _Expected_Behavior: Non-NULL owner/type preserved; NULL fields enriched from card; card_type always enriched_
    - _Preservation: Transactions with NULL owner/type still enriched identically to original behavior_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Fix PUT /transactions to preserve existing month_ref when date is edited
    - In `finance-pilot/backend/main.py`, modify `update_transaction()` endpoint (SQLite mode)
    - Before setting `month_ref = date[:7]`, fetch the current transaction's month_ref
    - If existing month_ref is non-NULL AND differs from date[:7], preserve it (do NOT overwrite)
    - If existing month_ref is NULL, derive from new date as before
    - Apply same logic in Firestore mode path
    - _Bug_Condition: isBugCondition(input) where input.operation = "update_date" AND input.transaction.month_ref IS NOT NULL AND input.transaction.month_ref != input.transaction.date[:7]_
    - _Expected_Behavior: Existing non-NULL month_ref preserved when date is edited_
    - _Preservation: NULL month_ref still derived from date for new transactions_
    - _Requirements: 2.6, 3.5, 3.6_

  - [x] 3.3 Fix dashboard-summary to apply enrichment before aggregation
    - In `finance-pilot/backend/main.py`, modify `get_dashboard_summary()` endpoint (SQLite mode)
    - After fetching raw transactions from DB, apply `EnrichmentService.enrich_transactions()` before aggregating
    - Build card_map from cards table (same pattern as GET /transactions)
    - Aggregate totals from enriched data instead of raw SQL GROUP BY
    - This ensures dashboard uses same enriched values as GET /transactions
    - _Bug_Condition: isBugCondition(input) where input.operation = "dashboard_query" AND enriched values differ from stored values_
    - _Expected_Behavior: Dashboard totals consistent with GET /transactions for same filters_
    - _Preservation: Dashboard results unchanged when enrichment produces same values as stored (NULL fields case)_
    - _Requirements: 2.5_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Enrichment Preserves User-Edited Owner/Type Fields
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (non-NULL owner/type preserved)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1: `pytest finance-pilot/backend/tests/test_enrichment_bug_condition.py`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - NULL Fields Still Enriched From Card Data
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2: `pytest finance-pilot/backend/tests/test_enrichment_preservation.py`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest finance-pilot/backend/tests/test_enrichment_bug_condition.py finance-pilot/backend/tests/test_enrichment_preservation.py --run`
  - Verify bug condition exploration test passes (bug is fixed)
  - Verify preservation tests pass (no regressions)
  - Run existing test suite to ensure no other tests broken: `pytest finance-pilot/backend/tests/ -x`
  - Ensure all tests pass, ask the user if questions arise.
