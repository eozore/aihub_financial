# 🔧 Setup Guide

Complete guide for configuring Firebase Authentication and GCP services.

---

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- Firebase project (we use `aifin-project`)
- Node.js 18+ and Python 3.11+

---

## 1. Firebase Web App Configuration

### Step 1: Create Web App

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select project `aifin-project`
3. Click **⚙️ Settings** > **Project Settings**
4. Scroll to **"Your apps"** section
5. Click **"</> Web"** to add a web app
6. Name it "AI Finance Web"
7. **Copy the `firebaseConfig`** that appears

### Step 2: Update Frontend Code

Paste the credentials in `frontend/lib/firebase.ts`:

```javascript
const firebaseConfig = {
  apiKey: "AIzaSy...",
  authDomain: "aifin-project.firebaseapp.com",
  projectId: "aifin-project",
  storageBucket: "aifin-project.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abc123"
};
```

---

## 2. Enable Email/Password Authentication

1. In Firebase Console, go to **Authentication** (sidebar)
2. Click on **"Sign-in method"** tab
3. Click **"Email/Password"**
4. Enable the toggle
5. Click **"Save"**

---

## 3. Create Users

### Option A: Via Firebase Console (Recommended)

1. Go to **Authentication** > **Users**
2. Click **"Add user"**
3. Create two users:
   - **Victor**: `victor@aifinance.com` / [secure password]
   - **Larissa**: `larissa@aifinance.com` / [secure password]

### Option B: Via Script

```bash
cd scripts/setup
python create_firebase_users.py
```

> Note: Requires service account key configured.

---

## 4. Environment Variables

### Backend (Cloud Run)

Set these when deploying:

```bash
PROJECT_ID=aifin-project
FIRESTORE_COLLECTION=transactions
TABLE_GOLD=transactions.transactions_gold
```

### Frontend

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=https://finance-backend-930725375338.us-central1.run.app
```

---

## 5. Firestore Indexes

The application requires composite indexes for queries. If you see index errors:

1. Check Cloud Run logs for the index creation URL
2. Click the URL to create the index in Firebase Console
3. Wait 2-5 minutes for index to build

Required indexes:
- `transactions`: `month_ref` (ASC), `__name__` (DESC)

---

## 6. Deploy Services

### Backend

```bash
cd backend
gcloud run deploy finance-backend \
  --source . \
  --region=us-central1 \
  --project=aifin-project \
  --allow-unauthenticated \
  --set-env-vars="PROJECT_ID=aifin-project"
```

### Frontend

```bash
cd frontend
gcloud run deploy finance-frontend \
  --source . \
  --region=us-central1 \
  --project=aifin-project \
  --allow-unauthenticated
```

---

## 7. Verification

After deployment, verify:

1. ✅ Frontend loads at the Cloud Run URL
2. ✅ Login works with created users
3. ✅ Dashboard shows data
4. ✅ Transactions page loads with sorting
5. ✅ Filters work correctly

---

## Troubleshooting

### CORS Errors
Check that backend CORS allows the frontend origin.

### Empty Data
Verify Firestore has documents in `transactions` collection.

### Filter Returns Empty
Check Cloud Run logs - may need additional Firestore indexes.

### Login Fails
Verify Firebase Authentication is enabled and users exist.
