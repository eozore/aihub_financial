# 🏦 AI Finance - Personal Finance Manager

> Sistema de gestão financeira pessoal com classificação inteligente de transações e dashboard analítico.

![Dashboard Preview](data/assets/logo.png)

## 🎯 Overview

AI Finance é uma aplicação full-stack para gerenciamento de finanças pessoais de casal, com:

- **Upload de faturas CSV** (Nubank, cartões de crédito)
- **Classificação automática** de transações por categoria e tipo
- **Dashboard interativo** com gráficos de evolução de gastos
- **Acerto de contas** automático entre usuários
- **Histórico completo** com filtros e ordenação

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         FRONTEND                            │
│              (Next.js 15 + React + TailwindCSS)            │
│         Cloud Run: finance-frontend.run.app                 │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST API
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                         BACKEND                             │
│                 (FastAPI + Python 3.11)                    │
│         Cloud Run: finance-backend.run.app                  │
└──────────┬────────────────────────────┬─────────────────────┘
           │ CRUD                       │ Analytics
           ▼                            ▼
┌──────────────────────┐    ┌──────────────────────────────────┐
│      FIRESTORE       │    │          BIGQUERY                │
│  (Real-time CRUD)    │    │  (Aggregations & Reports)        │
│   transactions       │    │  transactions_gold table         │
└──────────────────────┘    └──────────────────────────────────┘
```

## 📂 Project Structure

```
finance-pilot/
├── backend/                # FastAPI backend service
│   ├── main.py            # API endpoints
│   ├── classifier.py      # Transaction classification logic
│   ├── processor.py       # CSV processing pipeline
│   └── requirements.txt   # Python dependencies
│
├── frontend/              # Next.js frontend application
│   ├── app/              # App router pages
│   ├── components/       # React components
│   ├── services/         # API client
│   └── lib/              # Firebase config
│
├── scripts/              # Utility and migration scripts
│   ├── migration/        # Data migration scripts
│   ├── setup/           # Firebase/GCP setup
│   └── utils/           # Helper utilities
│
├── data/                 # Data files
│   ├── exports/         # Generated data exports
│   ├── backups/         # Database backups
│   └── assets/          # Static assets (logo, etc.)
│
├── infra/               # Terraform infrastructure
│   └── main.tf         # GCP resource definitions
│
└── docs/                # Documentation
    ├── setup.md        # Setup guide
    ├── architecture.md # Architecture details
    └── api-reference.md # API documentation
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Google Cloud SDK (for cloud deployment)
- Firebase project configured

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
USE_SQLITE=true python -m uvicorn main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

### Cloud Deployment

```bash
# Deploy backend
cd backend && gcloud run deploy finance-backend --source .

# Deploy frontend
cd frontend && gcloud run deploy finance-frontend --source .
```

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, TailwindCSS, Recharts |
| Backend | FastAPI, Python 3.11, Pydantic |
| Database | Firestore (CRUD), BigQuery (Analytics) |
| Auth | Firebase Authentication |
| Infra | Google Cloud Run, Terraform |
| Storage | Google Cloud Storage |

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/transactions` | List transactions with filters |
| POST | `/transactions` | Create new transaction |
| PUT | `/transactions/{id}` | Update transaction |
| DELETE | `/transactions/{id}` | Delete transaction |
| GET | `/dashboard-summary` | Aggregated dashboard data |
| GET | `/trend-data` | Chart data for spend evolution |
| POST | `/upload` | Upload CSV invoice file |

See [docs/api-reference.md](docs/api-reference.md) for full documentation.

## 🔐 Environment Variables

### Backend
```env
PROJECT_ID=aifin-project
FIRESTORE_COLLECTION=transactions
TABLE_GOLD=transactions.transactions_gold
USE_SQLITE=false  # true for local dev
TENANT_HEADER_NAME=X-Tenant-ID
DEFAULT_TENANT_ID=default
AUTO_JOIN_LEGACY_WORKSPACE=true
LEGACY_SHARED_EMAILS=victor@example.com,larissa@example.com
```

### Frontend
```env
NEXT_PUBLIC_API_URL=https://finance-backend-xxx.run.app
NEXT_PUBLIC_TENANT_HEADER_NAME=X-Tenant-ID
NEXT_PUBLIC_DEFAULT_TENANT_ID=default
```

## 📊 Features

- **Smart Classification**: Automatic categorization based on merchant, keywords, and history
- **Shared/Individual Split**: Tracks expenses for couples with settlement calculation
- **Trend Analysis**: Daily/monthly spend evolution charts
- **Sortable Tables**: Click column headers to sort data
- **Multi-owner Filters**: Filter by person and transaction type
- **Workspace Multi-tenant**: Free (1 painel / 1 membro) e Paid (até 3 painéis / 2 membros cada)

## 📖 Documentation

- [Setup Guide](docs/setup.md) - Firebase and GCP configuration
- [Architecture](docs/architecture.md) - System design and data flow
- [API Reference](docs/api-reference.md) - Complete endpoint documentation

## 📝 License

Private project - All rights reserved.

---

**Deployed URLs:**
- Frontend: https://finance-frontend-930725375338.us-central1.run.app
- Backend: https://finance-backend-930725375338.us-central1.run.app
