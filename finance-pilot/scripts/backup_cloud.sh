#!/bin/bash
# ─── Finance Pilot - Cloud Backup Script ───
# Exporta dados do Firestore e BigQuery para Cloud Storage.
# Uso: ./scripts/backup_cloud.sh
# Custo: ~$0.01 por execução (Storage + BQ export)
set -e

: "${PROJECT_ID:?ERROR: PROJECT_ID is required}"
REGION="${REGION:-us-central1}"
BUCKET="${PROJECT_ID}-raw-uploads"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_PREFIX="backups/${TIMESTAMP}"

GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== Finance Pilot Cloud Backup ===${NC}"
echo "Project: $PROJECT_ID"
echo "Bucket: gs://$BUCKET/$BACKUP_PREFIX"
echo ""

# 1. Export Firestore (toda a database)
echo "1. Exporting Firestore..."
gcloud firestore export "gs://$BUCKET/$BACKUP_PREFIX/firestore" \
    --project="$PROJECT_ID" \
    --collection-ids="transactions,users,workspaces,workspace_members,net_worth_monthly,current_account_movements"
echo -e "${GREEN}✓${NC} Firestore exported"

# 2. Export BigQuery tables to GCS (formato CSV comprimido)
echo "2. Exporting BigQuery tables..."
for TABLE in transactions_silver transactions_gold; do
    bq extract \
        --project_id="$PROJECT_ID" \
        --destination_format=CSV \
        --compression=GZIP \
        "${PROJECT_ID}:finance_analytics.${TABLE}" \
        "gs://$BUCKET/$BACKUP_PREFIX/bigquery/${TABLE}_*.csv.gz"
    echo -e "${GREEN}✓${NC} BigQuery table $TABLE exported"
done

# 3. Limpar backups antigos (manter últimos 30 dias)
echo ""
echo "3. Limpando backups com mais de 30 dias..."
CUTOFF_DATE=$(date -v-30d +%Y%m%d 2>/dev/null || date -d "30 days ago" +%Y%m%d 2>/dev/null || echo "skip")
if [ "$CUTOFF_DATE" != "skip" ]; then
    gsutil ls "gs://$BUCKET/backups/" 2>/dev/null | while read -r dir; do
        DIR_DATE=$(echo "$dir" | grep -oE '[0-9]{8}' | head -1)
        if [ -n "$DIR_DATE" ] && [ "$DIR_DATE" -lt "$CUTOFF_DATE" ]; then
            gsutil -m rm -r "$dir" 2>/dev/null || true
            echo "  Removed: $dir"
        fi
    done
fi

echo ""
echo -e "${GREEN}=== Cloud backup completo ===${NC}"
echo "Restore Firestore: gcloud firestore import gs://$BUCKET/$BACKUP_PREFIX/firestore"
echo "Restore BigQuery: bq load --source_format=CSV finance_analytics.TABLE gs://$BUCKET/$BACKUP_PREFIX/bigquery/TABLE_*.csv.gz"
