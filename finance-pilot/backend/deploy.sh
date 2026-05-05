#!/bin/bash
set -e

# ─── Required environment variables (no hardcoded secrets) ───
# Set these in your CI/CD pipeline or export before running.
: "${PROJECT_ID:?ERROR: PROJECT_ID is required}"
: "${FIREBASE_PROJECT_ID:?ERROR: FIREBASE_PROJECT_ID is required}"
: "${CORS_ORIGINS:?ERROR: CORS_ORIGINS is required}"

# ─── Optional with safe defaults ───
REGION="${REGION:-us-central1}"
REPO="${REPO:-finance-repo}"
IMAGE="${IMAGE:-finance-backend}"
TAG="${TAG:-latest}"
DEFAULT_TENANT_ID="${DEFAULT_TENANT_ID:-default}"
PREMIUM_EMAILS="${PREMIUM_EMAILS:-}"
ADMIN_EMAILS="${ADMIN_EMAILS:-}"

ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"

echo "Active gcloud project: ${ACTIVE_PROJECT:-unset}"
echo "Target deploy project: $PROJECT_ID"
if [ -n "$ACTIVE_PROJECT" ] && [ "$ACTIVE_PROJECT" != "$PROJECT_ID" ]; then
  echo "WARNING: projeto ativo difere do alvo. O deploy seguirá com --project=$PROJECT_ID."
fi

echo "1. Building Container..."
gcloud builds submit \
  --project "$PROJECT_ID" \
  --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:$TAG" \
  .

echo "2. Deploying to Cloud Run..."
gcloud run deploy "$IMAGE" \
  --project "$PROJECT_ID" \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:$TAG" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "finance-backend-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --memory 1Gi \
  --set-env-vars="^|^PROJECT_ID=$PROJECT_ID|FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID|TENANT_HEADER_NAME=X-Tenant-ID|DEFAULT_TENANT_ID=$DEFAULT_TENANT_ID|TENANT_REQUIRED=true|REQUIRE_AUTH_FOR_DATA=true|PREMIUM_EMAILS=$PREMIUM_EMAILS|ADMIN_EMAILS=$ADMIN_EMAILS|CORS_ORIGINS=$CORS_ORIGINS"

echo "Done!"
