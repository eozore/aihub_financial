# Requirements Document

## Introduction

This feature separates the PDF upload pipeline into two distinct phases:

1. **Upload/Confirm phase** — Persists raw extracted data (including original dates) without normalization or enrichment.
2. **Query/Display phase** — When transactions are served to the frontend (e.g., `GET /transactions`), the system enriches each transaction with card metadata and computes `month_ref` on the fly.

This ensures raw data is preserved for reprocessing and that enrichment logic (card lookup, owner assignment, type derivation) is applied consistently at read time rather than baked into stored records.

## Glossary

- **Upload_Service**: The backend component handling `POST /upload/confirm` that persists raw transactions to the database.
- **Enrichment_Service**: The backend component that enriches transactions with card data and computes `month_ref` at query time.
- **Transactions_Endpoint**: The `GET /transactions` API endpoint that serves enriched transaction data to the frontend.
- **Cards_Table**: The `cards` table storing registered card information per workspace (`workspace_id`, `owner`, `last4`, `card_type`, `bank`).
- **Transactions_Gold**: The `transactions_gold` table storing credit card transactions.
- **Raw_Date**: The original date extracted from the PDF (e.g., `2026-03-28`), representing the actual purchase date.
- **Month_Ref**: A derived `YYYY-MM` value used for grouping transactions by billing month, computed from the statement period rather than the transaction date.
- **Card_Last4**: The last 4 digits of the card number associated with a transaction.
- **Card_Type**: Classification of a card as `individual` or `shared`.
- **Owner**: The registered owner of a card in the workspace's Cards_Table.

## Requirements

### Requirement 1: Preserve Raw Dates at Upload Time

**User Story:** As a finance analyst, I want the upload process to save the original extracted dates without modification, so that raw data is preserved and can be reprocessed if the normalization logic changes.

#### Acceptance Criteria

1. WHEN a PDF upload is confirmed, THE Upload_Service SHALL persist each transaction's Raw_Date exactly as extracted from the PDF without computing or storing Month_Ref.
2. WHEN a PDF upload is confirmed, THE Upload_Service SHALL NOT perform date normalization or billing-month adjustment on the stored transaction date.
3. THE Upload_Service SHALL store a NULL or empty value for the `month_ref` column in Transactions_Gold at upload time.

### Requirement 2: Compute Month_Ref at Query Time

**User Story:** As a finance analyst, I want `month_ref` to be computed when I view transactions, so that I can change the grouping logic without re-uploading data.

#### Acceptance Criteria

1. WHEN the Transactions_Endpoint receives a request, THE Enrichment_Service SHALL compute `month_ref` for each transaction based on the statement's billing period or the transaction date.
2. THE Enrichment_Service SHALL derive `month_ref` as the `YYYY-MM` portion of the transaction's stored date field.
3. WHEN a transaction date falls outside the requested month range after Month_Ref computation, THE Transactions_Endpoint SHALL exclude that transaction from the response.
4. FOR ALL transactions, computing Month_Ref from a stored Raw_Date and then filtering by that Month_Ref SHALL produce the same result regardless of when the query is executed (idempotence property).

### Requirement 3: Enrich Transactions with Card Information at Query Time

**User Story:** As a finance analyst, I want each transaction to be enriched with card owner and type information when I view them, so that I always see up-to-date card metadata without re-uploading.

#### Acceptance Criteria

1. WHEN the Transactions_Endpoint serves transactions, THE Enrichment_Service SHALL look up each transaction's Card_Last4 in the workspace's Cards_Table.
2. WHEN a matching card is found in Cards_Table, THE Enrichment_Service SHALL set the transaction's `card_type` field to the card's registered Card_Type value (`individual` or `shared`).
3. WHEN a matching card is found in Cards_Table, THE Enrichment_Service SHALL set the transaction's `owner` field to the card's registered Owner value.
4. WHEN a matching card is found in Cards_Table, THE Enrichment_Service SHALL set the transaction's `type` field to the card's Card_Type value (`individual` or `shared`).
5. WHEN no matching card is found for a Card_Last4, THE Enrichment_Service SHALL preserve the transaction's existing `owner` and `type` values as stored in the database.
6. WHEN a Card_Last4 is NULL or empty, THE Enrichment_Service SHALL skip card enrichment for that transaction and preserve existing field values.

### Requirement 4: Upload Service Stores Only Raw Extracted Fields

**User Story:** As a developer, I want the upload confirm step to store only the raw extracted data, so that the persistence layer is simple and enrichment is decoupled.

#### Acceptance Criteria

1. WHEN a PDF upload is confirmed for a credit card statement, THE Upload_Service SHALL persist to Transactions_Gold only these raw fields: `id`, `tenant_id`, `date`, `amount`, `merchant_clean`, `card_last4`, `is_refund`, `transaction_source`, `upload_id`, `created_at`.
2. WHEN a PDF upload is confirmed, THE Upload_Service SHALL NOT set `owner`, `type`, or `card_type` based on card lookup during the confirm step.
3. WHEN a PDF upload is confirmed, THE Upload_Service SHALL still classify and store the `category` field using the ClassificationService, as this is not card-dependent enrichment.
4. IF the database write fails during upload confirm, THEN THE Upload_Service SHALL return an error response with a descriptive message and not partially commit transactions.

### Requirement 5: Enrichment Service Handles Missing or Unregistered Cards

**User Story:** As a finance analyst, I want to see transactions even when their card is not registered, so that no data is hidden from me.

#### Acceptance Criteria

1. WHEN a transaction has a Card_Last4 that does not match any entry in Cards_Table, THE Enrichment_Service SHALL return the transaction with `card_type` set to NULL.
2. WHEN a transaction has a Card_Last4 that does not match any entry in Cards_Table, THE Enrichment_Service SHALL return the transaction with `owner` set to the value stored in the database (which may be NULL or a user-provided value from upload).
3. WHEN a card is added or updated in Cards_Table, THE Enrichment_Service SHALL reflect the updated card information on subsequent queries without requiring data re-upload.
4. FOR ALL transactions in a workspace, enriching with card data and then enriching again SHALL produce identical results (idempotence property).

### Requirement 6: Backward Compatibility with Existing Data

**User Story:** As a user with existing uploaded transactions, I want the new enrichment to work with my previously uploaded data, so that I don't need to re-upload anything.

#### Acceptance Criteria

1. WHEN the Transactions_Endpoint queries transactions that were uploaded before this feature (with `month_ref` already stored), THE Enrichment_Service SHALL use the stored `month_ref` value if present and non-empty.
2. WHEN the Transactions_Endpoint queries transactions that have a NULL or empty `month_ref`, THE Enrichment_Service SHALL compute it from the transaction's date field.
3. WHEN the Transactions_Endpoint queries transactions that already have `owner` and `type` stored, THE Enrichment_Service SHALL override them with card-based enrichment if a matching card exists in Cards_Table.
4. THE Transactions_Endpoint SHALL return the same response schema as before this feature, ensuring frontend compatibility.
