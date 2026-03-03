# 📡 API Reference

Complete API documentation for the AI Finance backend.

**Base URL**: `https://finance-backend-930725375338.us-central1.run.app`

---

## Tenant Context

Every request must resolve a tenant through one of:
- Header `X-Tenant-ID` (or configured `TENANT_HEADER_NAME`)
- Firebase bearer token claim `tenant_id` or `firebase.tenant`

If both are sent, they must match.

---

## Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/transactions` | List transactions |
| POST | `/transactions` | Create transaction |
| PUT | `/transactions/{id}` | Update transaction |
| DELETE | `/transactions/{id}` | Delete transaction |
| GET | `/dashboard-summary` | Dashboard aggregations |
| GET | `/trend-data` | Chart trend data |
| POST | `/upload` | Upload CSV invoice |
| GET | `/me` | Current user profile and plan |
| PUT | `/me/plan` | Update user plan (`free`/`paid`) |
| GET | `/workspaces` | List user workspaces |
| POST | `/workspaces` | Create workspace |
| POST | `/workspaces/{id}/activate` | Set active workspace |
| GET | `/workspaces/{id}/members` | List workspace members |
| POST | `/workspaces/{id}/invites` | Create workspace invite |
| GET | `/invites` | List sent/received invites |
| POST | `/invites/{id}/accept` | Accept invite |

---

## Health Check

### `GET /`

Returns service status.

**Response**
```json
{
  "message": "AI Finance API",
  "status": "ok",
  "mode": "cloud"
}
```

---

## Transactions

### `GET /transactions`

List transactions with optional filters.

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start` | string | Yes | Start month (YYYY-MM) |
| `end` | string | No | End month (YYYY-MM), defaults to start |
| `owner` | string | No | Filter by owner: `Victor` or `Larissa` |
| `tx_type` | string | No | Filter by type: `Shared` or `Individual` |

**Example Request**
```
GET /transactions?start=2025-06&end=2025-06&owner=Victor
```

**Response**
```json
[
  {
    "id": "abc123-20250615",
    "date": "2025-06-15",
    "month_ref": "2025-06",
    "amount": 150.50,
    "merchant_clean": "Supermercado Extra",
    "category": "Mercado",
    "subcategory": null,
    "owner": "Victor",
    "type": "Shared",
    "tenant_id": "default"
  }
]
```

---

### `POST /transactions`

Create a new transaction.

**Request Body**
```json
{
  "date": "2025-06-20",
  "amount": 89.90,
  "merchant_clean": "Restaurante Italiano",
  "category": "Bar/Restaurante",
  "subcategory": null,
  "owner": "Larissa",
  "type": "Shared"
}
```

**Response**
```json
{
  "status": "created",
  "id": "d4f5e6a7-20250620"
}
```

---

### `PUT /transactions/{id}`

Update an existing transaction. All fields are optional.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Transaction ID |

**Request Body**
```json
{
  "category": "Lazer",
  "type": "Individual"
}
```

**Response**
```json
{
  "status": "updated",
  "id": "abc123-20250615"
}
```

---

### `DELETE /transactions/{id}`

Delete a transaction.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Transaction ID |

**Response**
```json
{
  "status": "deleted",
  "id": "abc123-20250615"
}
```

---

## Dashboard

### `GET /dashboard-summary`

Returns aggregated statistics for the dashboard.

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start` | string | Yes | Start month (YYYY-MM) |
| `end` | string | No | End month (YYYY-MM) |
| `owner` | string | No | Filter by owner |
| `tx_type` | string | No | Filter by type |

**Example Request**
```
GET /dashboard-summary?start=2025-06&end=2025-06
```

**Response**
```json
{
  "total_spend": 23374.09,
  "total_spend_change": -8,
  "victor_spend": 9306.09,
  "victor_spend_change": -25,
  "larissa_spend": 14068.00,
  "larissa_spend_change": 15,
  "shared_spend": 15200.00,
  "individual_spend": 8174.09,
  "settlement": {
    "direction": "victor_owes_larissa",
    "amount": 2602.24,
    "message": "Victor deve a Larissa"
  },
  "category_breakdown": [
    {"category": "Aluguel", "amount": 3895.00},
    {"category": "Mercado", "amount": 2500.00}
  ]
}
```

---

### `GET /trend-data`

Returns time-series data for spend evolution charts.

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start` | string | Yes | Start month (YYYY-MM) |
| `end` | string | No | End month (YYYY-MM) |
| `owner` | string | No | Filter by owner |
| `tx_type` | string | No | Filter by type |

**Response** (Daily aggregation for short ranges)
```json
{
  "aggregation": "daily",
  "data": [
    {"date": "2025-06-01", "amount": 450.00},
    {"date": "2025-06-02", "amount": 120.50},
    {"date": "2025-06-03", "amount": 89.00}
  ]
}
```

**Response** (Monthly aggregation for long ranges)
```json
{
  "aggregation": "monthly",
  "data": [
    {"date": "2025-01", "amount": 18500.00},
    {"date": "2025-02", "amount": 21200.00}
  ]
}
```

---

## File Upload

### `POST /upload`

Upload a CSV invoice file for processing.

**Content-Type**: `multipart/form-data`

**Form Fields**

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | CSV file to upload |
| `owner` | string | Owner name: `Victor` or `Larissa` |
| `month_ref` | string | Month reference (YYYY-MM) |

**Example (curl)**
```bash
curl -X POST https://finance-backend.../upload \
  -H "X-Tenant-ID: default" \
  -F "file=@fatura_junho.csv" \
  -F "owner=Victor" \
  -F "month_ref=2025-06"
```

**Response**
```json
{
  "status": "success",
  "message": "Processed 45 transactions",
  "transactions_created": 45,
  "duplicates_skipped": 3
}
```

---

## Workspaces And Plans

### `GET /me`

Returns current user profile, plan and workspace limits.

### `PUT /me/plan`

Request:
```json
{
  "plan_type": "paid"
}
```

Plan limits:
- `free`: 1 workspace, 1 member per workspace
- `paid`: up to 3 workspaces, 2 members per workspace

### `GET /workspaces`

Lists user memberships and active workspace.

### `POST /workspaces`

Request:
```json
{
  "name": "Casa"
}
```

### `POST /workspaces/{id}/invites`

Request:
```json
{
  "invitee_email": "user@example.com",
  "invite_mode": "shared"
}
```

`invite_mode`:
- `shared`: joins the same workspace (used by paid shared panel)
- `isolated`: invited user creates/uses own isolated workspace

### `POST /invites/{id}/accept`

Accepts a pending invite and sets active workspace for the user.

---

## Error Responses

All endpoints return standard error format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common Status Codes**

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Not Found |
| 500 | Internal Server Error |

---

## Data Types

### Transaction Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier |
| `date` | string | Date (YYYY-MM-DD) |
| `month_ref` | string | Month (YYYY-MM) |
| `amount` | number | Transaction amount |
| `merchant_clean` | string | Normalized merchant name |
| `category` | string | Expense category |
| `subcategory` | string? | Optional sub-category |
| `owner` | string | Victor or Larissa |
| `type` | string | Shared or Individual |
| `tenant_id` | string | Tenant identifier |

### Categories

Valid category values:
- Alimentação, Bar/Restaurante, Transporte, Combustivel
- Aluguel, Condominio, Moradia, Lazer
- Saúde/Estética, Mercado, Delivery, Streaming
- Projeto Pessoal, Uber/Onibus, Presentes, Faxina
- Curso, Luz/Internet, Manutenção/Revisão, Vestuário
- Voos, Airbnb/Hotel, Pedagio, ItensdeCasa, Luana, Outro
