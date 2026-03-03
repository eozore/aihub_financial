import sqlite3
import os
from google.cloud import bigquery
from pathlib import Path

# Config
# Ensure you have 'GOOGLE_APPLICATION_CREDENTIALS' set or run 'gcloud auth application-default login'
PROJECT_ID = os.environ.get("PROJECT_ID", "aifin-project")
DATASET_ID = "finance_analytics"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.transactions_gold"
DB_PATH = Path(__file__).parent.parent / "backend" / "finance.db"

def migrate():
    print(f"Migrating from {DB_PATH} to BigQuery {TABLE_ID}...")
    
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}!")
        return

    # SQLite
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM transactions_gold")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    
    print(f"Read {len(rows)} rows from SQLite.")
    
    if not rows:
        print("No data to migrate.")
        return

    # BigQuery
    try:
        client = bigquery.Client(project=PROJECT_ID)
        
        # TRUNCATE TABLE first to ensure exact sync with local
        print(f"Truncating table {TABLE_ID}...")
        truncate_query = f"TRUNCATE TABLE `{TABLE_ID}`"
        client.query(truncate_query).result()
        print("Table truncated.")
        
        # Batch insert
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            
            # BigQuery requires specific formatting sometimes, but JSON insert is robust
            # Ensure float amount
            for r in batch:
                 if r['amount'] is None: r['amount'] = 0.0
                 else: r['amount'] = float(r['amount'])

            errors = client.insert_rows_json(TABLE_ID, batch)
            if errors:
                print(f"Errors in batch {i}: {errors}")
            else:
                print(f"Inserted batch {i} to {i+len(batch)}")
                
        print("Migration completed successfully.")
        
    except Exception as e:
        print(f"Failed to connect to BigQuery: {e}")
        print("Make sure you are authenticated with 'gcloud auth application-default login'")

if __name__ == "__main__":
    migrate()
