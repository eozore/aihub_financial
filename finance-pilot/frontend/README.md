# 🎨 Frontend - Next.js Application

Personal finance dashboard built with Next.js and React.

## Tech Stack

- **Next.js 15** - React framework with App Router
- **React 19** - UI library
- **TailwindCSS** - Utility-first CSS framework
- **Recharts** - Chart library
- **Firebase** - Authentication
- **TypeScript** - Type safety

## Folder Structure

```
frontend/
├── app/                    # Next.js App Router
│   ├── page.tsx           # Dashboard (main page)
│   ├── transactions/      # Transactions list page
│   ├── upload/            # File upload page
│   └── login/             # Login page
├── components/            # React components
│   ├── AppShell.tsx       # Layout with sidebar
│   ├── DashboardCharts.tsx # Chart components
│   └── UploadForm.tsx     # File upload form
├── context/               # React contexts
│   └── AuthContext.tsx    # Firebase auth context
├── services/              # API client
│   └── api.ts             # Backend API calls
└── lib/                   # Utilities
    └── firebase.ts        # Firebase config
```

## Pages

| Route | Description |
|-------|-------------|
| `/` | Dashboard with summary cards and charts |
| `/transactions` | Transaction list with filters and sorting |
| `/upload` | CSV file upload form |
| `/login` | Firebase authentication |

## Environment Variables

Create `.env.local`:

```env
NEXT_PUBLIC_API_URL=https://finance-backend-930725375338.us-central1.run.app
NEXT_PUBLIC_TENANT_HEADER_NAME=X-Tenant-ID
NEXT_PUBLIC_DEFAULT_TENANT_ID=default
```

## Local Development

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Features

- **Responsive Design** - Works on desktop and mobile
- **Dark Mode** - Automatic color scheme support
- **Sortable Tables** - Click column headers to sort
- **Real-time Filters** - Filter by owner, type, date range
- **Interactive Charts** - Hover for details
- **Settlement Calculator** - Shows who owes whom
- **Workspace Switcher** - Seleção de painel ativo por usuário

## Firebase Configuration

Update `lib/firebase.ts` with your Firebase config:

```typescript
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "aifin-project.firebaseapp.com",
  projectId: "aifin-project",
  // ... other config
};
```

## Deployment

```bash
gcloud run deploy finance-frontend \
  --source . \
  --region=us-central1 \
  --project=aifin-project \
  --allow-unauthenticated
```

Or use the deploy script:

```bash
./deploy.sh
```

## Component Documentation

### AppShell

Main layout component with sidebar navigation.

```tsx
<AppShell>
  {/* Page content */}
</AppShell>
```

### DashboardCharts

Contains the spend evolution chart using Recharts.

```tsx
<SpendTrendChart data={trendData} />
```
