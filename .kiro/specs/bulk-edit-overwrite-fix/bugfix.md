# Bugfix Requirements Document

## Introduction

The bulk edit feature allows users to change `owner`, `type` (shared/individual), and other fields on transactions after upload. However, user edits made via bulk edit (PUT /transactions/{id}) are silently overwritten every time transactions are queried (GET /transactions). This happens because `EnrichmentService.enrich_card_data()` unconditionally replaces `owner` and `type` with card-derived values at query time, regardless of whether the user has manually set those fields.

Additionally, the dashboard (`GET /dashboard-summary`) queries the database directly without applying enrichment, causing inconsistencies between the transaction list and the dashboard views.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user bulk-edits the `owner` field of a transaction that has a matching card_last4 in the card map THEN the system overwrites the user's saved `owner` value with the card-derived owner on the next GET /transactions call

1.2 WHEN a user bulk-edits the `type` field (shared/individual) of a transaction that has a matching card_last4 in the card map THEN the system overwrites the user's saved `type` value with the card-derived card_type on the next GET /transactions call

1.3 WHEN a user edits a transaction's owner or type and then refreshes the page THEN the system displays the card-derived values instead of the user's saved edits, making it appear as though the edit was never saved

1.4 WHEN a card is updated (owner or card_type changed) THEN all historical transactions with that card_last4 retroactively change their displayed owner/type on the next query, even though the original transaction was made under the old card configuration

1.5 WHEN the dashboard-summary endpoint queries transactions by owner THEN it uses the raw database values (without enrichment), while GET /transactions uses enriched values, causing the dashboard and transaction list to show different data for the same period/filters

1.6 WHEN a user edits the `date` field of a transaction that has a manually-set month_ref (e.g., a credit card bill from a different month) THEN the system unconditionally recalculates month_ref from the new date, losing the user's intentional month assignment

### Expected Behavior (Correct)

2.1 WHEN a user bulk-edits the `owner` field of a transaction that has a matching card_last4 in the card map THEN the system SHALL preserve the user's saved `owner` value and NOT overwrite it with card-derived data during enrichment

2.2 WHEN a user bulk-edits the `type` field of a transaction that has a matching card_last4 in the card map THEN the system SHALL preserve the user's saved `type` value and NOT overwrite it with card-derived data during enrichment

2.3 WHEN a user edits a transaction's owner or type and then refreshes the page THEN the system SHALL display the user's saved values consistently across page loads

2.4 WHEN a card is updated THEN historical transactions that already have non-NULL owner/type values SHALL preserve those values (enrichment only applies to NULL fields)

2.5 WHEN the dashboard-summary endpoint queries transactions THEN it SHALL produce results consistent with GET /transactions for the same filters (both should respect user edits over card-derived values)

2.6 WHEN a user edits only the `date` field of a transaction THEN the system SHALL NOT recalculate month_ref if it was already set (preserving intentional month assignments like credit card billing cycles)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a transaction has a matching card_last4 AND the `owner` field is NULL (never manually edited) THEN the system SHALL CONTINUE TO enrich the owner from the card map

3.2 WHEN a transaction has a matching card_last4 AND the `type` field is NULL (never manually edited) THEN the system SHALL CONTINUE TO enrich the type from the card map

3.3 WHEN a transaction has no matching card_last4 in the card map THEN the system SHALL CONTINUE TO preserve existing owner and type values unchanged

3.4 WHEN a transaction has a matching card_last4 THEN the system SHALL CONTINUE TO enrich the `card_type` field from the card map regardless of other field values

3.5 WHEN enrichment computes `month_ref` from the transaction date THEN the system SHALL CONTINUE TO derive month_ref correctly for transactions with NULL month_ref

3.6 WHEN a transaction has no stored month_ref (NULL) and the user edits the date THEN the system SHALL recalculate month_ref from the new date (existing behavior for new transactions)

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type Transaction
  OUTPUT: boolean
  
  // Returns true when the transaction has a matching card AND has non-NULL owner or type
  // (indicating the user has manually set these values)
  RETURN X.card_last4 IS NOT NULL
     AND X.card_last4 IN card_map
     AND (X.owner IS NOT NULL OR X.type IS NOT NULL)
END FUNCTION
```

## Property Specification

```pascal
// Property 1: Fix Checking - User edits are preserved during enrichment
FOR ALL X WHERE isBugCondition(X) DO
  result ← enrich_card_data'(X, card_map)
  IF X.owner IS NOT NULL THEN
    ASSERT result.owner = X.owner
  END IF
  IF X.type IS NOT NULL THEN
    ASSERT result.type = X.type
  END IF
END FOR

// Property 2: Dashboard Consistency - Dashboard and transaction list agree
FOR ALL query(start, end, owner_filter, type_filter) DO
  transactions ← GET_transactions(start, end, owner_filter, type_filter)
  dashboard ← GET_dashboard_summary(start, end, owner_filter, type_filter)
  ASSERT dashboard.total_spend = SUM(transactions.amount)
END FOR

// Property 3: Month_ref Preservation - Editing date preserves existing month_ref
FOR ALL X WHERE X.month_ref IS NOT NULL DO
  result ← update_transaction(X.id, {date: new_date})
  ASSERT result.month_ref = X.month_ref  // preserved, not recalculated
END FOR
```

## Preservation Goal

```pascal
// Property: Preservation Checking - NULL fields still get enriched from card
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT enrich_card_data(X, card_map) = enrich_card_data'(X, card_map)
END FOR
```

This ensures that for transactions where owner and type are both NULL (never manually edited), the enrichment behavior remains identical to the original implementation.

---

## Verified Test Results

The following tests were executed against the live codebase to confirm the bugs:

### Test 1: Enrichment Overwrite (CONFIRMED ❌)
```
Input:  transaction with owner="Victor", type="individual", card_last4="1234"
Card:   card_last4="1234" → owner="Maria", card_type="shared"
Output: owner="Maria", type="shared"  (user edit lost!)
```

### Test 2: End-to-End API Flow (CONFIRMED ❌)
```
1. POST /transactions → created (owner=Maria, type=shared from card)
2. PUT /transactions/{id} → updated owner=Victor, type=individual (saved to DB ✓)
3. GET /transactions → returns owner=Maria, type=shared (enrichment overwrote!)
4. Filter owner=Victor → 0 results (should be 1)
5. Filter owner=Maria → 1 result (should be 0)
```

### Test 3: Card Update Retroactive Change (CONFIRMED ⚠️)
```
1. Card 4444: owner=Ana, card_type=individual
2. Transaction with card_last4=4444 → shows owner=Ana
3. Update card 4444: owner=Pedro, card_type=shared
4. Same transaction now shows owner=Pedro, type=shared (retroactive change!)
```

### Test 4: Dashboard Inconsistency (CONFIRMED ⚠️)
```
1. Transaction in DB: owner=Ana (original value)
2. GET /transactions → shows owner=Pedro (enriched from updated card)
3. GET /dashboard-summary?owner=Pedro → total_spend=0 (queries DB directly)
4. GET /dashboard-summary?owner=Ana → total_spend=200 (uses DB value)
Result: Dashboard and transaction list show different owners for same transaction!
```

### Test 5: Month_ref Overwrite on Date Edit (CONFIRMED ⚠️)
```
1. Transaction: date=2026-04-05, month_ref=2026-03 (intentional: March bill)
2. PUT /transactions/{id} with date=2026-04-10
3. Result: month_ref changed to 2026-04 (lost the March assignment!)
```
