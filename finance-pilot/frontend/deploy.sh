#!/bin/bash
set -e

# ─── Required environment variables (no hardcoded secrets) ───
# Set these in your CI/CD pipeline or export before running.
: "${PROJECT_ID:?ERROR: PROJECT_ID is required}"
: "${BACKEND_URL:?ERROR: BACKEND_URL is required}"
: "${FIREBASE_API_KEY:?ERROR: FIREBASE_API_KEY is required}"
: "${FIREBASE_AUTH_DOMAIN:?ERROR: FIREBASE_AUTH_DOMAIN is required}"
: "${FIREBASE_PROJECT_ID:?ERROR: FIREBASE_PROJECT_ID is required}"
: "${FIREBASE_STORAGE_BUCKET:?ERROR: FIREBASE_STORAGE_BUCKET is required}"
: "${FIREBASE_MESSAGING_SENDER_ID:?ERROR: FIREBASE_MESSAGING_SENDER_ID is required}"
: "${FIREBASE_APP_ID:?ERROR: FIREBASE_APP_ID is required}"

# ─── Optional with safe defaults ───
REGION="${REGION:-us-central1}"
REPO="${REPO:-finance-repo}"
IMAGE="${IMAGE:-finance-frontend}"
TAG="${TAG:-latest}"
TENANT_HEADER_NAME="${TENANT_HEADER_NAME:-X-Tenant-ID}"
DEFAULT_TENANT_ID="${DEFAULT_TENANT_ID:-default}"

IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:$TAG"
ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"

echo "Active gcloud project: ${ACTIVE_PROJECT:-unset}"
echo "Target deploy project: $PROJECT_ID"
if [ -n "$ACTIVE_PROJECT" ] && [ "$ACTIVE_PROJECT" != "$PROJECT_ID" ]; then
  echo "WARNING: projeto ativo difere do alvo. O deploy seguirá com --project=$PROJECT_ID."
fi

echo "1. Building Container..."
gcloud builds submit \
  --project "$PROJECT_ID" \
  --config cloudbuild.yaml \
  --substitutions="_IMAGE_NAME=$IMAGE_URI,_API_URL=$BACKEND_URL,_TENANT_HEADER_NAME=$TENANT_HEADER_NAME,_DEFAULT_TENANT_ID=$DEFAULT_TENANT_ID,_FIREBASE_API_KEY=$FIREBASE_API_KEY,_FIREBASE_AUTH_DOMAIN=$FIREBASE_AUTH_DOMAIN,_FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID,_FIREBASE_STORAGE_BUCKET=$FIREBASE_STORAGE_BUCKET,_FIREBASE_MESSAGING_SENDER_ID=$FIREBASE_MESSAGING_SENDER_ID,_FIREBASE_APP_ID=$FIREBASE_APP_ID" \
  .

echo "2. Deploying to Cloud Run..."
gcloud run deploy "$IMAGE" \
  --project "$PROJECT_ID" \
  --image "$IMAGE_URI" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "finance-backend-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --memory 1Gi \
  --set-env-vars="NEXT_PUBLIC_API_URL=$BACKEND_URL,NEXT_PUBLIC_TENANT_HEADER_NAME=$TENANT_HEADER_NAME,NEXT_PUBLIC_DEFAULT_TENANT_ID=$DEFAULT_TENANT_ID,NEXT_PUBLIC_FIREBASE_API_KEY=$FIREBASE_API_KEY,NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$FIREBASE_AUTH_DOMAIN,NEXT_PUBLIC_FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID,NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=$FIREBASE_STORAGE_BUCKET,NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=$FIREBASE_MESSAGING_SENDER_ID,NEXT_PUBLIC_FIREBASE_APP_ID=$FIREBASE_APP_ID"

echo "Done!"
