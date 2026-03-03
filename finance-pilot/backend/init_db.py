from google.cloud import bigquery
import json
import logging
from pathlib import Path
import datetime
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = "aifin-project"
DATASET_ID = "finance_analytics"
TABLE_ID = "transactions_gold"
DATA_FILE = Path(__file__).parent.parent / "data" / "gold_transactions.json"
DEFAULT_TENANT_ID = os.environ.get("DEFAULT_TENANT_ID", "default")

def init_bigquery():
    client = bigquery.Client(project=PROJECT_ID)
    
    # 1. Create Dataset if not exists
    dataset_ref = f"{PROJECT_ID}.{DATASET_ID}"
    try:
        client.get_dataset(dataset_ref)
        logger.info(f"Dataset {dataset_ref} already exists.")
    except Exception:
        logger.info(f"Creating dataset {dataset_ref}...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset)
        logger.info("Dataset created.")

    # 2. Check Table Schema
    table_ref = f"{dataset_ref}.{TABLE_ID}"
    schema = [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("date", "DATE"),
        bigquery.SchemaField("month_ref", "STRING"),
        bigquery.SchemaField("amount", "FLOAT"),
        bigquery.SchemaField("merchant_clean", "STRING"),
        bigquery.SchemaField("category", "STRING"),
        bigquery.SchemaField("subcategory", "STRING"),
        bigquery.SchemaField("owner", "STRING"),
        bigquery.SchemaField("type", "STRING"), # Shared / Individual
        bigquery.SchemaField("tenant_id", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
    ]

    try:
        client.get_table(table_ref)
        logger.info(f"Table {table_ref} already exists.")
        # Optional: Delete table to reload fresh data
        # client.delete_table(table_ref)
        # client.create_table(bigquery.Table(table_ref, schema=schema))
    except Exception:
        logger.info(f"Creating table {table_ref}...")
        table = bigquery.Table(table_ref, schema=schema)
        client.create_table(table)
        logger.info("Table created.")

    # 3. Load Data
    if not DATA_FILE.exists():
        logger.error(f"Data file not found: {DATA_FILE}")
        return

    logger.info("Loading JSON data...")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    rows_to_insert = []
    for item in raw_data:
        # Transform Logic
        
        # 1. Date
        tx_date = None
        month_ref = None
        if 'date' in item and '/' in item['date']:
             parts = item['date'].split(' ')[0].split('/')
             if len(parts) == 3:
                 tx_date = f"{parts[2]}-{parts[1]}-{parts[0]}" # YYYY-MM-DD
                 month_ref = f"{parts[2]}-{parts[1]}"
        elif 'date' in item and '-' in item['date']:
             tx_date = item['date']
             month_ref = item['date'][:7]

        # 2. Type Mapping
        tx_type = "Individual"
        if item.get("type_legacy") == "Casal":
            tx_type = "Shared"
        elif item.get("type"):
            tx_type = item["type"]

        # 3. Category Mapping
        category = item.get("category")
        if not category and item.get("group_legacy"):
            category = item["group_legacy"]
        
        # 4. Owner Normalization
        owner = item.get("owner", "Unknown")
        if owner == "Lala": owner = "Larissa"

        row = {
            "id": item.get("id"),
            "date": tx_date,
            "month_ref": month_ref,
            "amount": float(item.get("amount") or 0.0),
            "merchant_clean": item.get("merchant_clean") or item.get("merchant_raw"),
            "category": category,
            "subcategory": item.get("subcategory"),
            "owner": owner,
            "type": tx_type,
            "tenant_id": item.get("tenant_id") or DEFAULT_TENANT_ID,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        if row["id"] and row["date"]:
            rows_to_insert.append(row)

    if rows_to_insert:
        errors = client.insert_rows_json(table_ref, rows_to_insert)
        if errors:
            logger.error(f"Encountered errors while inserting rows: {errors}")
        else:
            logger.info(f"Successfully loaded {len(rows_to_insert)} rows into BigQuery.")
    else:
        logger.warning("No valid rows to insert.")

if __name__ == "__main__":
    init_bigquery()
