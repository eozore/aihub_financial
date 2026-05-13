# Implementation Plan: Upload Data Enrichment

## Overview

This plan implements the separation of raw data persistence (upload phase) from read-time enrichment (query phase). The EnrichmentService is created as a stateless pure function, the upload confirm endpoint is simplified to store only raw fields, and the transactions endpoint is updated to enrich on the fly.

## Tasks

- [ ] 1. Create EnrichmentService module with core logic
  - [x] 1.1 Create `finance-pilot/backend/enrichment_service.py` with `CardInfo` dataclass and `EnrichmentService` class
    - Define `CardInfo` dataclass with `owner` and `card_type` fields
    - Implement `compute_month_ref(transaction)` — returns stored `month_ref` if non-empty, otherwise derives YYYY-MM from `date`
    - Implement `enrich_card_data(transaction, card_map)` — looks up `card_last4` in card_map, sets `owner`/`type`/`card_type` if found, preserves existing values otherwise
    - Implement `enrich_transactions(transactions, card_map)` — applies both enrichments to a list of transactions
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.2, 6.1, 6.2, 6.3_

  - [ ]* 1.2 Write property test: Upload preserves raw date and stores NULL month_ref
    - **Property 1: Upload preserves raw date and stores NULL month_ref**
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ]* 1.3 Write property test: Month_ref computation derives YYYY-MM from date
    - **Property 3: Month_ref computation derives YYYY-MM from date**
    - **Validates: Requirements 2.1, 2.2, 6.1, 6.2**

  - [ ]* 1.4 Write property test: Enrichment is idempotent
    - **Property 4: Enrichment is idempotent**
    - **Validates: Requirements 2.4, 5.4**

  - [ ]* 1.5 Write property test: Card enrichment applies registered card data
    - **Property 5: Card enrichment applies registered card data**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 6.3**

  - [ ]* 1.6 Write property test: Missing or NULL card preserves stored values
    - **Property 6: Missing or NULL card preserves stored values**
    - **Validates: Requirements 3.5, 3.6, 5.1, 5.2**

- [ ] 2. Checkpoint - Verify EnrichmentService logic
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Modify Upload Confirm endpoint to store only raw fields
  - [x] 3.1 Update `POST /upload/confirm` in `finance-pilot/backend/main.py` to stop computing `month_ref` and card-derived fields
    - Remove card lookup logic from the confirm flow (owner, type, card_type assignment)
    - Store `month_ref` as NULL for new uploads
    - Store `owner`, `type`, `card_type` as NULL for new uploads
    - Keep `category` classification via ClassificationService (not card-dependent)
    - Keep `card_last4` as a raw extracted field
    - _Requirements: 1.1, 1.2, 1.3, 4.1, 4.2, 4.3, 4.4_

  - [ ]* 3.2 Write property test: Upload stores only raw fields without card-derived enrichment
    - **Property 2: Upload stores only raw fields without card-derived enrichment**
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 3.3 Write property test: Category is classified at upload time
    - **Property 8: Category is classified at upload time**
    - **Validates: Requirements 4.3**

- [ ] 4. Checkpoint - Verify upload changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Modify GET /transactions to use EnrichmentService
  - [x] 5.1 Update `GET /transactions` in `finance-pilot/backend/main.py` to call EnrichmentService before returning results
    - Load workspace card map from `cards` table (filtered by `workspace_id`)
    - Build `card_map: dict[str, CardInfo]` from active cards
    - Call `EnrichmentService.enrich_transactions()` on raw query results
    - Apply `month_ref` filtering on enriched data (not raw data)
    - Apply `owner`/`type` filters on enriched data
    - Return paginated, enriched results with same response schema
    - _Requirements: 2.1, 2.3, 3.1, 5.3, 6.3, 6.4_

  - [ ]* 5.2 Write property test: Enrichment reflects current card state
    - **Property 7: Enrichment reflects current card state**
    - **Validates: Requirements 5.3**

  - [ ]* 5.3 Write unit tests for GET /transactions enrichment integration
    - Test backward compatibility: transactions with pre-existing `month_ref` use stored value
    - Test transactions with NULL `month_ref` get computed value
    - Test response schema matches existing format
    - Test card CRUD changes are reflected in subsequent queries
    - _Requirements: 6.1, 6.2, 6.4_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (already in requirements.txt)
- The EnrichmentService is a pure function — no database access inside the service itself
- Implementation language: Python (as specified in the design document)
