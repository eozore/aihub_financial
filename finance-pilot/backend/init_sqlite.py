"""
Script para carregar dados do CSV (FinData) para o SQLite local.
Aplica transformações de normalização e carrega no banco.
"""
import pandas as pd
import sqlite3
from pathlib import Path
import datetime
import uuid
import os

DATA_FILE = Path(__file__).parent.parent / "data" / "findata_backup_20260202_164435.csv"
DB_PATH = Path(__file__).parent / "finance.db"
DEFAULT_TENANT_ID = os.environ.get("DEFAULT_TENANT_ID", "default")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Drop and recreate table for fresh load
    c.execute('DROP TABLE IF EXISTS transactions_gold')
    
    c.execute('''
        CREATE TABLE transactions_gold (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            date DATE,
            month_ref TEXT,
            amount REAL,
            merchant_clean TEXT,
            category TEXT,
            subcategory TEXT,
            owner TEXT,
            type TEXT,
            created_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

def load_legacy_data():
    if not DATA_FILE.exists():
        print(f"Data file not found: {DATA_FILE}")
        return

    # Initialize DB
    init_db()
    conn = get_db_connection()
    c = conn.cursor()

    print(f"Loading CSV data from {DATA_FILE}...")
    df = pd.read_csv(DATA_FILE)
    print(f"Read {len(df)} rows")
    print(f"Columns: {list(df.columns)}")

    count = 0
    for _, row in df.iterrows():
        # 1. Date Transformation (DD/MM/YYYY HH:MM:SS -> YYYY-MM-DD)
        raw_date = str(row.get('Data', ''))
        tx_date = None
        month_ref = None
        
        if raw_date and '/' in raw_date:
            try:
                parts = raw_date.split(' ')[0].split('/')
                if len(parts) == 3:
                    tx_date = f"{parts[2]}-{parts[1]}-{parts[0]}"  # YYYY-MM-DD
                    month_ref = f"{parts[2]}-{parts[1]}"
            except:
                pass
        
        if not tx_date:
            continue  # Skip rows without valid date

        # 2. Type Mapping (Casal -> Shared, otherwise Individual)
        tipo = str(row.get("Tipo", ""))
        tx_type = "Shared" if tipo == "Casal" else "Individual"

        # 3. Category (Grupo column)
        category = str(row.get("Grupo", "")) or "Outros"
        
        # 4. Owner Normalization (Lala -> Larissa)
        owner = str(row.get("Nome", "Unknown"))
        if owner == "Lala":
            owner = "Larissa"
        
        # 5. Amount - Handle Brazilian format (comma as decimal, or plain number)
        amount_str = str(row.get("Valor", "0"))
        amount_str = amount_str.replace('.', '').replace(',', '.')  # "1.234,56" -> "1234.56"
        try:
            amount = float(amount_str) if amount_str else 0.0
        except:
            amount = 0.0

        # 6. Merchant/Description
        merchant = str(row.get("Observações", "")) or category

        # Generate unique ID
        tx_id = str(uuid.uuid4())[:8] + "-" + tx_date.replace("-", "")

        # Insert into SQLite
        try:
            c.execute('''
                INSERT INTO transactions_gold 
                (id, tenant_id, date, month_ref, amount, merchant_clean, category, subcategory, owner, type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                tx_id,
                DEFAULT_TENANT_ID,
                tx_date,
                month_ref,
                amount,
                merchant,
                category,
                None,  # subcategory
                owner,
                tx_type,
                datetime.datetime.now().isoformat()
            ))
            count += 1
        except Exception as e:
            print(f"Error inserting row: {e}")

    conn.commit()
    conn.close()
    print(f"Successfully loaded {count} rows into SQLite.")
    
    # Show date range
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM transactions_gold")
    min_date, max_date, total = c.fetchone()
    conn.close()
    print(f"Date range: {min_date} to {max_date} ({total} transactions)")

if __name__ == "__main__":
    load_legacy_data()
