import pandas as pd
import hashlib
import datetime
import os
import io
import sqlite3
from pathlib import Path

from normalization import normalize_merchant
from category_mapping import load_category_map, get_category
from type_model import load_model, predict_types

# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID", "aifin-project")
BUCKET_RAW = f"{PROJECT_ID}-raw-uploads"
DATASET_ID = "finance_analytics"
TABLE_SILVER = f"{PROJECT_ID}.{DATASET_ID}.transactions_silver"
TABLE_GOLD = f"{PROJECT_ID}.{DATASET_ID}.transactions_gold"

# Local SQLite Config
USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() == "true"
DB_PATH = Path(__file__).parent / "finance.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

class TransactionProcessor:
    def __init__(self):
        self.use_sqlite = USE_SQLITE
        
        if not self.use_sqlite:
            from google.cloud import storage, bigquery, firestore
            self.storage_client = storage.Client(project=PROJECT_ID)
            self.bq_client = bigquery.Client(project=PROJECT_ID)
            self.db = firestore.Client(project=PROJECT_ID)
        
        self.category_map = load_category_map()
        self.type_model = load_model()

    def _day_name_pt(self, date_value) -> str:
        try:
            return pd.to_datetime(date_value).day_name(locale="pt_BR")
        except Exception:
            weekday = pd.to_datetime(date_value).weekday()
            names = [
                "Segunda feira",
                "Terça feira",
                "Quarta feira",
                "Quinta feira",
                "Sexta feira",
                "Sábado",
                "Domingo",
            ]
            return names[weekday]

    def generate_id(self, row, index=0):
        # Unique ID hash - include index to distinguish identical transactions on same day
        raw_str = f"{row['tenant_id']}-{row['date']}-{row['amount']}-{row['merchant_raw']}-{row['owner']}-{index}"
        return hashlib.md5(raw_str.encode('utf-8')).hexdigest()[:8]

    def process_file(self, file_content: bytes, filename: str, owner: str, month_ref: str, tenant_id: str):
        """
        Reads CSV bytes, processes to Silver ( deduplicated ) and Gold ( enriched ).
        Supports both SQLite (local) and BigQuery (cloud) modes.
        """
        try:
            # 1. Read CSV
            df = pd.read_csv(io.BytesIO(file_content))
            
            # Normalize columns
            if 'date' in df.columns: date_col = 'date'
            elif 'Data' in df.columns: date_col = 'Data'
            else: raise ValueError("Column 'date' or 'Data' not found")
            
            if 'amount' in df.columns: amt_col = 'amount' 
            elif 'Valor' in df.columns: amt_col = 'Valor'
            else: raise ValueError("Column 'amount' or 'Valor' not found")
            
            if 'title' in df.columns: merch_col = 'title'
            elif 'Observações' in df.columns: merch_col = 'Observações'
            else: raise ValueError("Column 'title' or 'Observações' not found")

            processed_rows = []
            
            for index, row in df.iterrows():
                # Ignore Invoice Payments
                if "Pagamento recebido" in str(row[merch_col]):
                    continue

                # Clean Amount
                val_str = str(row[amt_col]).strip()
                if ',' in val_str:
                    val_str = val_str.replace('.', '').replace(',', '.')
                try:
                    amount = float(val_str)
                except:
                    amount = 0.0
                # Ignore negative values (refunds/chargebacks) before any other processing
                if amount < 0:
                    continue

                # Date parsing
                original_date_str = str(row[date_col])
                try:
                    if '-' in original_date_str:
                         day = int(pd.to_datetime(original_date_str).day)
                    else:
                        day = int(original_date_str.split('/')[0])
                except:
                    day = 1
                
                ref_year, ref_month = map(int, month_ref.split('-'))
                
                rec_id = self.generate_id({
                    'tenant_id': tenant_id,
                    'date': original_date_str, 
                    'amount': val_str, 
                    'merchant_raw': str(row[merch_col]),
                    'owner': owner
                }, index)

                # Create Date Object
                try:
                    new_date = datetime.date(ref_year, ref_month, day)
                except ValueError:
                    import calendar
                    last_day = calendar.monthrange(ref_year, ref_month)[1]
                    new_date = datetime.date(ref_year, ref_month, last_day)

                # Add suffix to make unique
                rec_id_full = f"{rec_id}-{new_date.isoformat().replace('-', '')}"
                
                # Mantem descricao original (sem normalizar) e normaliza apenas para categoria
                merchant_raw = str(row[merch_col])
                merchant_clean = merchant_raw.strip()
                merchant_norm = normalize_merchant(merchant_raw)

                processed_rows.append({
                    "id": rec_id_full,
                    "date": new_date.isoformat(),
                    "month_ref": month_ref,
                    "amount": amount,
                    "merchant_raw": merchant_raw,
                    "merchant_clean": merchant_clean,
                    "merchant_norm": merchant_norm,
                    "category": None,  # Will be filled by mapping
                    "subcategory": None,
                    "type": None,  # Will be filled by model (Victor) or fixed (Larissa)
                    "owner": owner,
                    "tenant_id": tenant_id,
                    "source_file": filename,
                    "created_at": datetime.datetime.now().isoformat()
                })

            # 2.5. Enrich with category mapping + aggregate
            df_proc = pd.DataFrame(processed_rows)
            df_proc["category"] = df_proc["merchant_norm"].apply(
                lambda x: get_category(x, self.category_map)
            )
            df_proc["day_of_week"] = df_proc["date"].apply(self._day_name_pt)
            df_proc["month"] = pd.to_datetime(df_proc["date"]).dt.month

            # Define tipo: Victor = modelo, Larissa = Individual
            if owner.strip().lower() == "larissa":
                df_proc["type"] = "Individual"
            else:
                preds = predict_types(df_proc, model=self.type_model)
                if preds is None:
                    df_proc["type"] = None
                else:
                    df_proc["type"] = preds

            # Agrupa APOS estimar tipo (soma final)
            final_group_cols = ["tenant_id", "merchant_clean", "category", "owner", "type"]
            df_final = (
                df_proc
                .groupby(final_group_cols, as_index=False, dropna=False)
                .agg({
                    "amount": "sum",
                    "date": "min",
                })
            )

            # Reconstrói linhas gold agregadas
            gold_rows = []
            for _, row_agg in df_final.iterrows():
                rec_id = self.generate_id({
                    "tenant_id": row_agg["tenant_id"],
                    "date": row_agg["date"],
                    "amount": row_agg["amount"],
                    "merchant_raw": row_agg["merchant_clean"],
                    "owner": row_agg["owner"],
                }, 0)
                rec_id_full = f"{rec_id}-{str(row_agg['date']).replace('-', '')}"
                gold_rows.append({
                    "id": rec_id_full,
                    "date": row_agg["date"],
                    "month_ref": month_ref,
                    "amount": row_agg["amount"],
                    "merchant_clean": row_agg["merchant_clean"],
                    "category": row_agg["category"],
                    "subcategory": None,
                    "type": row_agg["type"],
                    "owner": row_agg["owner"],
                    "tenant_id": row_agg["tenant_id"],
                    "created_at": datetime.datetime.now().isoformat(),
                })

            # 3. Insert to Database
            if self.use_sqlite:
                return self._insert_sqlite(gold_rows)
            else:
                return self._insert_bigquery(processed_rows, gold_rows)

        except Exception as e:
            print(f"Error processing file: {e}")
            raise e

    def _insert_sqlite(self, rows):
        """Insert rows into local SQLite database"""
        conn = get_db_connection()
        c = conn.cursor()
        
        inserted = 0
        for row in rows:
            try:
                c.execute('''
                    INSERT OR REPLACE INTO transactions_gold 
                    (id, tenant_id, date, month_ref, amount, merchant_clean, category, subcategory, owner, type, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['id'],
                    row['tenant_id'],
                    row['date'],
                    row['month_ref'],
                    row['amount'],
                    row['merchant_clean'],
                    row['category'],
                    row['subcategory'],
                    row['owner'],
                    row['type'],
                    row['created_at']
                ))
                inserted += 1
            except Exception as e:
                print(f"Error inserting row: {e}")
        
        conn.commit()
        conn.close()
        print(f"Inserted {inserted} rows into SQLite")
        return inserted

    def _insert_bigquery(self, silver_rows, gold_rows):
        """Insert rows into BigQuery (cloud mode)"""
        from google.cloud import bigquery
        
        # Silver records
        silver_rows = [{
            "id": r['id'],
            "date": r['date'],
            "month_ref": r['month_ref'],
            "amount": r['amount'],
            "merchant_raw": r['merchant_raw'],
            "merchant_clean": r['merchant_clean'],
            "owner": r['owner'],
            "tenant_id": r['tenant_id'],
            "source_file": r['source_file'],
            "created_at": r['created_at']
        } for r in silver_rows]
        
        errors = self.bq_client.insert_rows_json(TABLE_SILVER, silver_rows)
        if errors:
            print(f"BQ Silver Errors: {errors}")
        
        # Gold records
        gold_rows = [{
            "id": r['id'],
            "date": r['date'],
            "month_ref": r['month_ref'],
            "amount": r['amount'],
            "merchant_clean": r['merchant_clean'],
            "category": r['category'],
            "subcategory": r['subcategory'],
            "type": r['type'],
            "owner": r['owner'],
            "tenant_id": r['tenant_id'],
            "created_at": r['created_at']
        } for r in gold_rows]

        errors_gold = self.bq_client.insert_rows_json(TABLE_GOLD, gold_rows)
        if errors_gold:
            print(f"BQ Gold Errors: {errors_gold}")

        return len(gold_rows)
