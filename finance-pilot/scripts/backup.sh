#!/bin/bash
# ─── Finance Pilot - Backup Script ───
# Cria backup local do SQLite e exporta dados em CSV/JSON.
# Uso: ./scripts/backup.sh [destino]
# Custo: $0 (tudo local + git)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="$PROJECT_ROOT/backend/finance.db"
BACKUP_DIR="${1:-$PROJECT_ROOT/data/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Finance Pilot Backup ===${NC}"
echo "Timestamp: $TIMESTAMP"
echo "Source DB: $DB_PATH"
echo "Backup dir: $BACKUP_DIR"
echo ""

# Criar diretório de backup
mkdir -p "$BACKUP_DIR"

# 1. Backup binário do SQLite (cópia atômica)
if [ -f "$DB_PATH" ]; then
    BACKUP_DB="$BACKUP_DIR/finance_backup_${TIMESTAMP}.db"
    sqlite3 "$DB_PATH" ".backup '$BACKUP_DB'"
    echo -e "${GREEN}✓${NC} SQLite backup: $BACKUP_DB ($(du -h "$BACKUP_DB" | cut -f1))"
else
    echo -e "${YELLOW}⚠ Database not found at $DB_PATH${NC}"
    exit 1
fi

# 2. Export transactions_gold como CSV
CSV_FILE="$BACKUP_DIR/transactions_gold_${TIMESTAMP}.csv"
sqlite3 -header -csv "$DB_PATH" "SELECT * FROM transactions_gold ORDER BY date DESC;" > "$CSV_FILE"
ROWS=$(wc -l < "$CSV_FILE")
echo -e "${GREEN}✓${NC} Transactions CSV: $CSV_FILE ($((ROWS - 1)) rows)"

# 3. Export net_worth_monthly como CSV
NW_FILE="$BACKUP_DIR/net_worth_monthly_${TIMESTAMP}.csv"
sqlite3 -header -csv "$DB_PATH" "SELECT * FROM net_worth_monthly ORDER BY month_ref DESC;" > "$NW_FILE"
NW_ROWS=$(wc -l < "$NW_FILE")
echo -e "${GREEN}✓${NC} Net Worth CSV: $NW_FILE ($((NW_ROWS - 1)) rows)"

# 4. Export current_account_movements como CSV
CA_FILE="$BACKUP_DIR/current_account_${TIMESTAMP}.csv"
sqlite3 -header -csv "$DB_PATH" "SELECT * FROM current_account_movements ORDER BY date DESC;" > "$CA_FILE"
CA_ROWS=$(wc -l < "$CA_FILE")
echo -e "${GREEN}✓${NC} Current Account CSV: $CA_FILE ($((CA_ROWS - 1)) rows)"

# 5. Limpar backups antigos (manter últimos 10)
echo ""
echo "Limpando backups antigos (mantendo últimos 10)..."
ls -t "$BACKUP_DIR"/finance_backup_*.db 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
ls -t "$BACKUP_DIR"/transactions_gold_*.csv 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
ls -t "$BACKUP_DIR"/net_worth_monthly_*.csv 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
ls -t "$BACKUP_DIR"/current_account_*.csv 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true

echo ""
echo -e "${GREEN}=== Backup completo ===${NC}"
echo "Para restaurar: sqlite3 backend/finance.db '.restore $BACKUP_DB'"
