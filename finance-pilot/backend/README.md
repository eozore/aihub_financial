# 🔧 Backend - FastAPI Service

Finance management API built with FastAPI and Python.

## Tech Stack

- **FastAPI** - Modern async web framework
- **Python 3.11** - Runtime
- **Firestore** - Real-time CRUD operations
- **BigQuery** - Analytics queries
- **Pydantic** - Data validation

## Files Overview

| File | Description |
|------|-------------|
| `main.py` | API endpoints and route handlers |
| `classifier.py` | Transaction classification logic |
| `processor.py` | CSV file processing pipeline |
| `normalization.py` | Merchant name normalization |
| `database.py` | SQLite connection helper (local dev) |
| `merchant_map.json` | Merchant name mappings |

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with SQLite (local mode)
USE_SQLITE=true python -m uvicorn main:app --reload --port 8000
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_SQLITE` | false | Use local SQLite instead of cloud |
| `PROJECT_ID` | aifin-project | GCP project ID |
| `FIRESTORE_COLLECTION` | transactions | Firestore collection name |
| `TABLE_GOLD` | transactions.transactions_gold | BigQuery table |
| `TENANT_HEADER_NAME` | X-Tenant-ID | Header used to resolve tenant |
| `DEFAULT_TENANT_ID` | default | Fallback tenant for legacy rows |
| `TENANT_REQUIRED` | true | Reject requests without tenant context |
| `AUTO_JOIN_LEGACY_WORKSPACE` | true | Auto-associate first users to legacy workspace |
| `LEGACY_SHARED_EMAILS` | (empty) | Optional allowlist for legacy shared workspace bootstrap |

## API Endpoints

See [docs/api-reference.md](../docs/api-reference.md) for full documentation.

### Quick Reference

```
GET  /                        Health check
GET  /transactions            List transactions
POST /transactions            Create transaction
PUT  /transactions/{id}       Update transaction
DELETE /transactions/{id}     Delete transaction
GET  /dashboard-summary       Dashboard aggregations
GET  /trend-data              Chart data
POST /upload                  Upload CSV file
GET  /me                      User profile and limits
PUT  /me/plan                 Update plan (free/paid)
GET  /workspaces              List user workspaces
POST /workspaces              Create workspace
POST /workspaces/{id}/activate Activate workspace
GET  /workspaces/{id}/members List workspace members
POST /workspaces/{id}/invites Create invite
GET  /invites                 List invites
POST /invites/{id}/accept     Accept invite
```

## Multi-Tenant

- Every transaction includes `tenant_id`.
- CRUD, dashboard and trends are always scoped by tenant.
- Tenant is resolved from Firebase token claims (`tenant_id` or `firebase.tenant`) and/or `X-Tenant-ID`.
- Plan limits:
  - Free: 1 workspace, 1 member per workspace
  - Paid: up to 3 workspaces, 2 members per workspace

## Deployment

```bash
gcloud run deploy finance-backend \
  --source . \
  --region=us-central1 \
  --project=aifin-project \
  --allow-unauthenticated \
  --set-env-vars="PROJECT_ID=aifin-project"
```

## Classification Logic

The classifier assigns category and type using:

1. **Force rules** - Specific merchants always Shared (pedágio, etc.)
2. **Category rules** - Some categories always Shared or Individual
3. **Historical patterns** - Learns from past classifications
4. **Keyword fallbacks** - Default mappings

See `classifier.py` for implementation details.
