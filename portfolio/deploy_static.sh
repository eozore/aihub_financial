#!/bin/bash
set -e

PROJECT_ID="${PROJECT_ID:-aifin-project}"
BUCKET_NAME="${BUCKET_NAME:-zore-financial-home}"
LOCATION="${LOCATION:-us-central1}"
MAKE_PUBLIC="${MAKE_PUBLIC:-true}"
ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"

echo "Active gcloud project: ${ACTIVE_PROJECT:-unset}"
echo "Target deploy project: $PROJECT_ID"
if [ -n "$ACTIVE_PROJECT" ] && [ "$ACTIVE_PROJECT" != "$PROJECT_ID" ]; then
  echo "WARNING: projeto ativo difere do alvo. O deploy seguirá com --project=$PROJECT_ID."
fi

echo "1. Ensuring bucket exists..."
if ! gcloud storage buckets describe "gs://$BUCKET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET_NAME" \
    --project "$PROJECT_ID" \
    --location "$LOCATION"
fi

echo "2. Uploading static files..."
gcloud storage cp "index.html" "gs://$BUCKET_NAME/index.html"
gcloud storage cp "404.html" "gs://$BUCKET_NAME/404.html"
gcloud storage cp "style.css" "gs://$BUCKET_NAME/style.css"
gcloud storage rsync -r "blogs" "gs://$BUCKET_NAME/blogs"
gcloud storage rsync -r "image" "gs://$BUCKET_NAME/image"

echo "3. Configuring website entrypoints..."
gcloud storage buckets update "gs://$BUCKET_NAME" \
  --project "$PROJECT_ID" \
  --web-main-page-suffix="index.html" \
  --web-error-page="404.html"

if [ "$MAKE_PUBLIC" = "true" ]; then
  echo "4. Making bucket public (read-only)..."
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
    --project "$PROJECT_ID" \
    --member="allUsers" \
    --role="roles/storage.objectViewer"
fi

echo "Done!"
echo "Website URL: http://storage.googleapis.com/$BUCKET_NAME/index.html"
