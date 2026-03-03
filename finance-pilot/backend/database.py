import sqlite3
from pathlib import Path

DB_PATH = Path('finance.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create transactions_gold table mimicking BigQuery schema
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions_gold (
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

    # Monthly snapshots used by the Patrimônio dashboard (manual or derived).
    # One row per tenant + owner + month_ref (YYYY-MM).
    c.execute('''
        CREATE TABLE IF NOT EXISTS net_worth_monthly (
            tenant_id TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT 'Victor',
            month_ref TEXT NOT NULL,
            salary REAL,
            other_income REAL,
            income_total REAL,
            expense_fixed REAL,
            expense_variable REAL,
            expense_total REAL,
            cash_end_balance REAL,
            net_worth_total REAL,
            debt_ratio REAL,
            notes TEXT,
            updated_at TIMESTAMP,
            PRIMARY KEY (tenant_id, owner, month_ref)
        )
    ''')

    # Raw current-account movements (signed values). Used for month validation and
    # for generating spending transactions from outgoing cash movements.
    c.execute('''
        CREATE TABLE IF NOT EXISTS current_account_movements (
            tenant_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            movement_id TEXT NOT NULL,
            date DATE,
            month_ref TEXT,
            amount_signed REAL,
            description TEXT,
            source_file TEXT,
            is_card_invoice_payment INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP,
            PRIMARY KEY (tenant_id, owner, movement_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
