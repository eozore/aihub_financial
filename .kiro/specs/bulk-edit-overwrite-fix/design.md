# Bulk Edit Overwrite Fix - Bugfix Design

## Overview

The `EnrichmentService.enrich_card_data()` method unconditionally overwrites `owner` and `type` fields with card-derived values at query time, even when the user has manually edited those fields via bulk edit. This causes user edits to be silently lost on every GET /transactions call. Additionally, the dashboard queries the database directly (without enrichment), creating inconsistencies between views, and the PUT /transactions endpoint unconditionally recalculates `month_ref` when the date is edited, losing intentional month assignments.

The fix makes enrichment conditional: only populate `owner` and `type` from card data when the stored values are NULL. This preserves user edits while maintaining backward compatibility for transactions that have never been manually edited.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a transaction has a matching card_last4 in the card map AND has non-NULL owner or type values (indicating user edits exist)
- **Property (P)**: The desired behavior — enrichment must preserve non-NULL owner/type values and only fill NULL fields from card data
- **Preservation**: Existing enrichment behavior for transactions with NULL owner/type must remain unchanged; card_type enrichment continues unconditionally
- **EnrichmentService**: The class in `finance-pilot/backend/enrichment_service.py` that applies card metadata to transactions at query time
- **card_map**: A dictionary mapping card_last4 digits to CardInfo (owner, card_type) built from the cards table
- **month_ref**: A YYYY-MM string indicating which billing month a transaction belongs to (may differ from the transaction date for credit card cycles)

## Bug Details

### Bug Condition

The bug manifests when a transaction has a matching card in the card map AND the user has previously set the `owner` or `type` fields (stored as non-NULL in the database). The `enrich_card_data()` method unconditionally overwrites these fields with card-derived values, discarding user edits. A secondary bug occurs when the PUT endpoint recalculates `month_ref` from the date, and a tertiary bug when the dashboard bypasses enrichment entirely.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {transaction: Transaction, card_map: CardMap, operation: string}
  OUTPUT: boolean
  
  // Primary bug: enrichment overwrites user edits
  IF input.operation = "enrich" THEN
    RETURN input.transaction.card_last4 IS NOT NULL
       AND input.transaction.card_last4 IN input.card_map
       AND (input.transaction.owner IS NOT NULL OR input.transaction.type IS NOT NULL)
  END IF
  
  // Secondary bug: month_ref overwrite on date edit
  IF input.operation = "update_date" THEN
    RETURN input.transaction.month_ref IS NOT NULL
       AND input.transaction.month_ref != input.transaction.date[:7]
  END IF
  
  // Tertiary bug: dashboard inconsistency
  IF input.operation = "dashboard_query" THEN
    RETURN EXISTS transaction WHERE
      enriched_owner(transaction) != stored_owner(transaction)
      OR enriched_type(transaction) != stored_type(transaction)
  END IF
  
  RETURN FALSE
END FUNCTION
```

### Examples

- **Enrichment overwrite**: Transaction has `owner="Victor"`, `type="individual"`, `card_last4="1234"`. Card map has `"1234" → {owner: "Maria", card_type: "shared"}`. After enrichment, `owner` becomes "Maria" and `type` becomes "shared" — user edit lost.
- **Page refresh data loss**: User edits owner to "Victor" via PUT (saved to DB). On next GET /transactions, enrichment overwrites back to "Maria". User sees their edit disappeared.
- **Card update retroactive change**: Card 4444 changes from `owner=Ana` to `owner=Pedro`. All historical transactions with `card_last4=4444` now show `owner=Pedro`, even those made when Ana owned the card.
- **Dashboard inconsistency**: Transaction in DB has `owner=Ana`. GET /transactions enriches to `owner=Pedro`. Dashboard queries DB directly and shows `owner=Ana`. Same transaction, different owner in different views.
- **Month_ref overwrite**: Transaction has `date=2026-04-05`, `month_ref=2026-03` (March credit card bill). User edits date to `2026-04-10`. System recalculates `month_ref=2026-04`, losing the intentional March assignment.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Transactions with NULL owner and matching card_last4 must still be enriched with card-derived owner
- Transactions with NULL type and matching card_last4 must still be enriched with card-derived type
- The `card_type` field must continue to be enriched unconditionally from card data (it's metadata, not user-editable)
- Transactions with no matching card_last4 must preserve their existing owner/type values unchanged
- The `compute_month_ref()` method must continue to derive month_ref from date for transactions with NULL month_ref
- New transactions created via POST must still derive month_ref from date
- Mouse/UI interactions, pagination, filtering, and all other API behaviors remain unchanged

**Scope:**
All inputs that do NOT involve the bug condition should be completely unaffected by this fix. This includes:
- Transactions with NULL owner/type fields (enrichment fills them as before)
- Transactions with no matching card in the card map
- All non-enrichment operations (create, delete, category edits, etc.)
- The `card_type` field enrichment (always applied)

## Hypothesized Root Cause

Based on the bug description and code analysis, the confirmed root causes are:

1. **Unconditional field overwrite in `enrich_card_data()`**: Lines in `enrichment_service.py` set `result["owner"] = card_info.owner` and `result["type"] = card_info.card_type` without checking whether the transaction already has non-NULL values for these fields. The method should only enrich NULL fields.

2. **Dashboard bypasses enrichment**: The `GET /dashboard-summary` endpoint in `main.py` queries `transactions_gold` directly with SQL aggregation, using raw DB values for `owner` and `type` filters. Meanwhile, `GET /transactions` applies enrichment after fetching. When enrichment changes values, the two endpoints disagree.

3. **Unconditional month_ref recalculation in PUT**: The PUT /transactions endpoint always sets `month_ref = date[:7]` when the date field is updated, regardless of whether the transaction already has a manually-assigned month_ref that differs from the date.

4. **No "user edited" tracking**: The system has no explicit flag to distinguish user-edited fields from card-derived fields. However, the NULL-check approach works because: newly uploaded transactions have NULL owner/type (to be enriched), while user edits via PUT always write non-NULL values.

## Correctness Properties

Property 1: Bug Condition - User Edits Preserved During Enrichment

_For any_ transaction where the bug condition holds (card_last4 matches a card in the map AND owner or type is non-NULL), the fixed `enrich_card_data()` function SHALL preserve the existing non-NULL owner and type values, only enriching fields that are NULL.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - NULL Fields Still Enriched From Card Data

_For any_ transaction where the bug condition does NOT hold (owner and type are both NULL, or no matching card exists), the fixed `enrich_card_data()` function SHALL produce the same result as the original function, preserving backward-compatible enrichment of NULL fields.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

Property 3: Bug Condition - Month_ref Preserved on Date Edit

_For any_ transaction update where only the date field is changed AND the transaction has an existing non-NULL month_ref, the fixed PUT endpoint SHALL preserve the existing month_ref value and NOT recalculate it from the new date.

**Validates: Requirements 2.6**

Property 4: Preservation - Month_ref Derived for NULL Cases

_For any_ transaction update where the date field is changed AND the transaction has a NULL month_ref, the fixed PUT endpoint SHALL derive month_ref from the new date (existing behavior preserved).

**Validates: Requirements 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `finance-pilot/backend/enrichment_service.py`

**Function**: `enrich_card_data()`

**Specific Changes**:
1. **Conditional owner enrichment**: Only set `result["owner"] = card_info.owner` when `result.get("owner")` is None or empty string
2. **Conditional type enrichment**: Only set `result["type"] = card_info.card_type` when `result.get("type")` is None or empty string
3. **Keep card_type unconditional**: The `result["card_type"] = card_info.card_type` line remains unchanged (card_type is metadata, always enriched)

---

**File**: `finance-pilot/backend/main.py`

**Function**: `update_transaction()` (PUT /transactions/{transaction_id})

**Specific Changes**:
4. **Conditional month_ref update (SQLite mode)**: Before setting `month_ref = date[:7]`, fetch the current transaction's month_ref. If it's already non-NULL, do NOT overwrite it. Only derive month_ref from date when the existing value is NULL.
5. **Conditional month_ref update (Firestore mode)**: Same logic — check existing month_ref before overwriting in the Firestore update path.

---

**File**: `finance-pilot/backend/main.py`

**Function**: `get_dashboard_summary()` (GET /dashboard-summary)

**Specific Changes**:
6. **Apply enrichment to dashboard queries (SQLite mode)**: After fetching raw transactions from the database, apply `EnrichmentService.enrich_transactions()` before aggregating totals. This ensures the dashboard uses the same enriched values as GET /transactions.
7. **Alternatively, use enriched field values in SQL**: Since the fix makes enrichment only fill NULLs, and user edits are stored in the DB, the dashboard can use `COALESCE(owner, card_derived_owner)` logic. However, the simpler approach is to fetch raw data, enrich, then aggregate in Python — matching the GET /transactions pattern.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that create transactions with non-NULL owner/type, run them through `enrich_card_data()`, and assert the user values are preserved. Run these tests on the UNFIXED code to observe failures and confirm the root cause.

**Test Cases**:
1. **Owner overwrite test**: Transaction with `owner="Victor"`, card maps to `owner="Maria"` — assert owner stays "Victor" (will fail on unfixed code)
2. **Type overwrite test**: Transaction with `type="individual"`, card maps to `card_type="shared"` — assert type stays "individual" (will fail on unfixed code)
3. **Month_ref overwrite test**: PUT with new date on transaction with existing month_ref — assert month_ref preserved (will fail on unfixed code)
4. **Dashboard consistency test**: Compare dashboard totals with transaction list totals for same filters (will fail on unfixed code)

**Expected Counterexamples**:
- `enrich_card_data({owner: "Victor", card_last4: "1234"}, {"1234": CardInfo("Maria", "shared")})` returns `{owner: "Maria"}` instead of `{owner: "Victor"}`
- Possible causes: unconditional assignment without NULL check (confirmed by code inspection)

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL transaction WHERE isBugCondition(transaction) DO
  result := enrich_card_data_fixed(transaction, card_map)
  IF transaction.owner IS NOT NULL THEN
    ASSERT result.owner = transaction.owner
  END IF
  IF transaction.type IS NOT NULL THEN
    ASSERT result.type = transaction.type
  END IF
  // card_type is always enriched
  ASSERT result.card_type = card_map[transaction.card_last4].card_type
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL transaction WHERE NOT isBugCondition(transaction) DO
  ASSERT enrich_card_data_original(transaction, card_map) = enrich_card_data_fixed(transaction, card_map)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (various combinations of NULL/non-NULL fields, matching/non-matching cards)
- It catches edge cases that manual unit tests might miss (empty strings, whitespace-only values)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for transactions with NULL owner/type, then write property-based tests capturing that behavior.

**Test Cases**:
1. **NULL field enrichment preservation**: Verify transactions with NULL owner/type still get enriched from card data after the fix
2. **No-card preservation**: Verify transactions with no matching card_last4 are unchanged by both old and new code
3. **card_type always enriched**: Verify card_type field is always set from card data regardless of other field values
4. **Month_ref derivation for NULL**: Verify transactions with NULL month_ref still get month_ref derived from date

### Unit Tests

- Test `enrich_card_data()` with non-NULL owner — assert owner preserved
- Test `enrich_card_data()` with non-NULL type — assert type preserved
- Test `enrich_card_data()` with NULL owner — assert owner enriched from card
- Test `enrich_card_data()` with NULL type — assert type enriched from card
- Test `enrich_card_data()` with no matching card — assert all fields unchanged
- Test PUT /transactions date edit with existing month_ref — assert month_ref preserved
- Test PUT /transactions date edit with NULL month_ref — assert month_ref derived from date
- Test dashboard consistency with enriched transactions

### Property-Based Tests

- Generate random transactions with various NULL/non-NULL field combinations and verify enrichment only fills NULL fields (fix checking)
- Generate random transactions with both owner and type NULL and verify enrichment produces identical results to original code (preservation checking)
- Generate random date edits on transactions with/without existing month_ref and verify correct month_ref behavior
- Generate random card map configurations and verify card_type is always enriched regardless of other fields

### Integration Tests

- Full API flow: POST transaction → PUT to edit owner → GET transactions → verify owner preserved
- Full API flow: PUT to edit date on transaction with custom month_ref → GET → verify month_ref preserved
- Dashboard vs transaction list consistency: same filters produce consistent totals
- Card update does not retroactively change transactions with non-NULL owner/type
- Bulk edit multiple transactions → refresh → all edits preserved
