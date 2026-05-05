#!/bin/bash
set -e

PROJECT_ID="${PROJECT_ID:-aifin-project}"
REGION="${REGION:-us-central1}"
ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"

echo "GCP account: ${ACTIVE_ACCOUNT:-unknown}"
echo "GCP active project: ${ACTIVE_PROJECT:-unset}"
echo "Deploy target project: $PROJECT_ID"
if [ -n "$ACTIVE_PROJECT" ] && [ "$ACTIVE_PROJECT" != "$PROJECT_ID" ]; then
  echo "WARNING: projeto ativo no gcloud difere do alvo. O deploy seguirá usando --project=$PROJECT_ID."
fi

echo "==> Deploy backend"
(
  cd finance-pilot/backend
  PROJECT_ID="$PROJECT_ID" REGION="$REGION" ./deploy.sh
)

BACKEND_URL="$(gcloud run services describe finance-backend --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
echo "Backend URL: $BACKEND_URL"

echo "==> Deploy frontend"
(
  cd finance-pilot/frontend
  PROJECT_ID="$PROJECT_ID" REGION="$REGION" BACKEND_URL="$BACKEND_URL" ./deploy.sh
)

echo "Done."
echo "Frontend app: $(gcloud run services describe finance-frontend --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
