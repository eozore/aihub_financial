# 🏗️ Architecture

Technical architecture documentation for the AI Finance system.

---

## System Overview

AI Finance uses a **hybrid database architecture**:

- **Firestore**: Real-time CRUD operations (fast reads/writes)
- **BigQuery**: Analytics and aggregations (dashboard, trends)

This design optimizes for both interactive user experience and complex analytical queries.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                            CLIENT                                   │
│                         (Web Browser)                               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │ HTTPS
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                  │
│                   ┌───────────────────────┐                        │
│                   │     Next.js 15        │                        │
│                   │   React 19 + TS       │                        │
│                   │   TailwindCSS         │                        │
│                   │   Recharts            │                        │
│                   └───────────────────────┘                        │
│              Cloud Run: finance-frontend.run.app                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │ REST API (JSON)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           BACKEND                                   │
│                   ┌───────────────────────┐                        │
│                   │      FastAPI          │                        │
│                   │    Python 3.11        │                        │
│                   │     Pydantic          │                        │
│                   └───────────────────────┘                        │
│              Cloud Run: finance-backend.run.app                     │
└──────────┬─────────────────────┬────────────────────┬───────────────┘
           │                     │                    │
           │ Auth                │ CRUD               │ Analytics
           ▼                     ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐
│    FIREBASE      │  │    FIRESTORE     │  │       BIGQUERY          │
│  Authentication  │  │                  │  │                         │
│                  │  │  transactions    │  │  transactions_gold      │
│  Email/Password  │  │  collection      │  │  table                  │
│                  │  │                  │  │                         │
│  Users:          │  │  Fields:         │  │  Columns:               │
│  - Victor        │  │  - date          │  │  - date                 │
│  - Larissa       │  │  - amount        │  │  - amount               │
│                  │  │  - merchant      │  │  - merchant_clean       │
│                  │  │  - category      │  │  - category             │
│                  │  │  - owner         │  │  - owner                │
│                  │  │  - type          │  │  - type                 │
└──────────────────┘  └──────────────────┘  └─────────────────────────┘
```

---

## Data Flow

### 1. Upload Flow

```
CSV File → Backend → Processor → Classifier → Firestore + BigQuery
```

1. User uploads CSV via frontend
2. Backend receives file and parses it
3. `processor.py` normalizes merchant names
4. `classifier.py` assigns category and type
5. Data saved to Firestore (CRUD) and synced to BigQuery (analytics)

### 2. Read Flow

```
Frontend → Backend → Firestore (list/detail) or BigQuery (aggregations)
```

- **Transactions list**: Firestore query with filters
- **Dashboard summary**: BigQuery aggregation query
- **Trend data**: BigQuery daily/monthly grouping

### 3. Update/Delete Flow

```
Frontend → Backend → Firestore (immediate) → BigQuery (async)
```

Changes are immediately reflected in Firestore. BigQuery sync happens during next data migration.

---

## Classification Logic

The classifier uses a hierarchical rule system:

```
1. FORCE_SHARED_MERCHANTS     → Pedágio, NuTag, etc.
2. ALWAYS_SHARED_CATEGORIES   → Aluguel, Condomínio, Mercado, etc.
3. ALWAYS_INDIVIDUAL_CATEGORIES → Curso, Vestuário, Saúde, etc.
4. Historical Analysis        → Pattern from past transactions
5. Keyword Fallbacks          → Default category/type mappings
```

### Classification Categories

| Type | Categories |
|------|-----------|
| **Always Shared** | Aluguel, Condomínio, Luz/Internet, Faxina, Streaming, Mercado, ItensdeCasa, Manutenção |
| **Always Individual** | Projeto Pessoal, Vestuário, Curso, Luana, Saúde/Estética |
| **Contextual** | Bar/Restaurante, Transporte, Lazer, Delivery (depends on merchant) |

---

## Database Schema

### Firestore Document Structure

```javascript
{
  id: "abc123-20250615",
  date: "2025-06-15",
  month_ref: "2025-06",
  amount: 150.50,
  merchant_clean: "Supermercado Extra",
  category: "Mercado",
  subcategory: null,
  owner: "Victor",
  type: "Shared",
  created_at: "2026-02-03T10:00:00Z",
  migrated_at: "2026-02-03T19:54:00Z"
}
```

### BigQuery Table Schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | STRING | Unique transaction ID |
| `date` | DATE | Transaction date |
| `month_ref` | STRING | Month reference (YYYY-MM) |
| `amount` | FLOAT | Transaction amount |
| `merchant_clean` | STRING | Normalized merchant name |
| `category` | STRING | Expense category |
| `subcategory` | STRING | Sub-category (optional) |
| `owner` | STRING | Victor or Larissa |
| `type` | STRING | Shared or Individual |

---

## Security

### Authentication
- Firebase Authentication with Email/Password
- Frontend validates auth state before rendering
- No backend auth (relies on frontend)

### CORS
- Backend allows specific frontend origins
- Credentials allowed for cross-origin requests

### Data Access
- All users see all data (family finance app)
- No row-level security implemented

---

## Infrastructure

### GCP Services Used

| Service | Purpose |
|---------|---------|
| Cloud Run | Frontend & Backend hosting |
| Firestore | Real-time database |
| BigQuery | Analytics warehouse |
| Cloud Storage | CSV file uploads |

### Terraform Resources

Infrastructure defined in `infra/main.tf`:
- Cloud Run services
- BigQuery dataset and table
- Cloud Storage buckets
- IAM permissions

---

## Performance Considerations

1. **Firestore Queries**: Use composite indexes for filtered queries
2. **BigQuery**: Partition by date for large datasets
3. **Frontend**: useMemo for sorted transaction lists
4. **Caching**: No caching layer currently (future improvement)
