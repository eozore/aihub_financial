import pandas as pd
import hashlib
import datetime
import os
import io
import sqlite3
import logging
from pathlib import Path

from classification_service import ClassificationService

logger = logging.getLogger("finance-pilot")

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

        self.classification_svc = ClassificationService()

    def _day_name_pt(self, date_value) -> str:
        try:
            return pd.to_datetime(date_value).day_name(locale="pt_BR")
        except Exception:
            weekday = pd.to_datetime(date_value).weekday()
            names = [
                "Segunda feira", "Terça feira", "Quarta feira",
                "Quinta feira", "Sexta feira", "Sábado", "Domingo",
            ]
            return names[weekday]

    def generate_id(self, row, index=0):
        raw_str = f"{row['tenant_id']}-{row['date']}-{row['amount']}-{row['merchant_raw']}-{row['owner']}-{index}"
        return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16]

    def _process_chunk(self, df, date_col, amt_col, merch_col, owner, month_ref, tenant_id, filename, offset):
        """Process a DataFrame chunk and return a list of processed row dicts."""
        import calendar

        rows = []
        ref_year, ref_month = map(int, month_ref.split('-'))

        for index, row in df.iterrows():
            real_index = offset + len(rows)

            # Ignore invoice payments
            if "Pagamento recebido" in str(row[merch_col]):
                continue

            # Clean amount
            val_str = str(row[amt_col]).strip()
            if ',' in val_str:
                val_str = val_str.replace('.', '').replace(',', '.')
            try:
                amount = float(val_str)
            except Exception:
                amount = 0.0

            # Ignore negative values (refunds/chargebacks)
            if amount < 0:
                continue

            # Date parsing
            original_date_str = str(row[date_col])
            try:
                if '-' in original_date_str:
                    day = int(pd.to_datetime(original_date_str).day)
                else:
                    day = int(original_date_str.split('/')[0])
            except Exception:
                day = 1

            rec_id = self.generate_id({
                'tenant_id': tenant_id,
                'date': original_date_str,
                'amount': val_str,
                'merchant_raw': str(row[merch_col]),
                'owner': owner
            }, real_index)

            # Create date object
            try:
                new_date = datetime.date(ref_year, ref_month, day)
            except ValueError:
                last_day = calendar.monthrange(ref_year, ref_month)[1]
                new_date = datetime.date(ref_year, ref_month, last_day)

            rec_id_full = f"{rec_id}-{new_date.isoformat().replace('-', '')}"

            merchant_raw = str(row[merch_col])

            # Use unified classification service for normalization
            classification = self.classification_svc.classify(
                merchant_raw, amount=amount, owner=owner
            )

            merchant_clean = classification["merchant_norm"]

            rows.append({
                "id": rec_id_full,
                "date": new_date.isoformat(),
                "month_ref": month_ref,
                "amount": amount,
                "merchant_raw": merchant_raw,
                "merchant_clean": merchant_clean,
                "merchant_norm": classification["merchant_norm"],
                "category": classification["category"],
                "subcategory": None,
                "type": None,  # Will be filled by model or rule below
                "owner": owner,
                "tenant_id": tenant_id,
                "source_file": filename,
                "created_at": datetime.datetime.now().isoformat()
            })

        return rows

    def process_file(self, file_content: bytes, filename: str, owner: str, month_ref: str, tenant_id: str):
        """
        Reads CSV bytes, processes to Silver (deduplicated) and Gold (enriched).
        Supports both SQLite (local) and BigQuery (cloud) modes.
        Uses chunked reading for large files to limit memory usage.
        """
        try:
            # 1. Read CSV in chunks
            CHUNK_SIZE = 5000
            chunks = pd.read_csv(io.BytesIO(file_content), chunksize=CHUNK_SIZE)

            first_chunk = True
            date_col = amt_col = merch_col = None
            processed_rows = []

            for df in chunks:
                # Detect columns on first chunk
                if first_chunk:
                    if 'date' in df.columns:
                        date_col = 'date'
                    elif 'Data' in df.columns:
                        date_col = 'Data'
                    else:
                        raise ValueError("Column 'date' or 'Data' not found")

                    if 'amount' in df.columns:
                        amt_col = 'amount'
                    elif 'Valor' in df.columns:
                        amt_col = 'Valor'
                    else:
                        raise ValueError("Column 'amount' or 'Valor' not found")

                    if 'title' in df.columns:
                        merch_col = 'title'
                    elif 'Observações' in df.columns:
                        merch_col = 'Observações'
                    else:
                        raise ValueError("Column 'title' or 'Observações' not found")
                    first_chunk = False

                processed_rows.extend(
                    self._process_chunk(df, date_col, amt_col, merch_col, owner, month_ref, tenant_id, filename, len(processed_rows))
                )

            if not processed_rows:
                logger.warning("No valid rows found in file: %s", filename)
                return {"count": 0, "gold_rows": []}

            # 2. Enrich with type inference
            df_proc = pd.DataFrame(processed_rows)
            df_proc["day_of_week"] = df_proc["date"].apply(self._day_name_pt)
            df_proc["month"] = pd.to_datetime(df_proc["date"]).dt.month

            # Type: use classification service rules for each row
            for idx, row in df_proc.iterrows():
                classification = self.classification_svc.classify(
                    row["merchant_clean"],
                    amount=row["amount"],
                    owner=owner,
                    existing_category=row["category"],
                )
                df_proc.at[idx, "type"] = classification["type"]

            # 3. Build gold rows directly from individual transactions (no aggregation)
            gold_rows = []
            for _, row_ind in df_proc.iterrows():
                gold_rows.append({
                    "id": row_ind["id"],
                    "date": row_ind["date"],
                    "month_ref": month_ref,
                    "amount": row_ind["amount"],
                    "merchant_clean": row_ind["merchant_clean"],
                    "category": row_ind["category"],
                    "subcategory": row_ind.get("subcategory"),
                    "type": row_ind["type"],
                    "owner": row_ind["owner"],
                    "tenant_id": row_ind["tenant_id"],
                    "created_at": datetime.datetime.now().isoformat(),
                })

            # 4. Insert to database
            if self.use_sqlite:
                inserted_count = self._insert_sqlite(gold_rows)
            else:
                inserted_count = self._insert_bigquery(processed_rows, gold_rows)

            return {"count": inserted_count, "gold_rows": gold_rows}

        except Exception as e:
            logger.error("Error processing file %s: %s", filename, e)
            raise

    def _insert_sqlite(self, rows):
        """Insert rows into local SQLite database."""
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
                    row['id'], row['tenant_id'], row['date'], row['month_ref'],
                    row['amount'], row['merchant_clean'], row['category'],
                    row['subcategory'], row['owner'], row['type'], row['created_at']
                ))
                inserted += 1
            except Exception as e:
                logger.error("Error inserting row: %s", e)

        conn.commit()
        conn.close()
        logger.info("Inserted %d rows into SQLite", inserted)
        return inserted

    def _sanitize_bq_value(self, value):
        if value is None:
            return None

        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.isoformat()

        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass

        if isinstance(value, str) and value.strip().lower() == "nan":
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        return value

    def _sanitize_bq_row(self, row: dict) -> dict:
        return {key: self._sanitize_bq_value(value) for key, value in row.items()}

    def _append_bigquery_rows(self, table_id: str, rows: list[dict], label: str):
        from google.cloud import bigquery

        if not rows:
            return

        try:
            errors = self.bq_client.insert_rows_json(table_id, rows)
            if errors:
                raise RuntimeError(f"BQ {label} Errors: {errors}")
        except Exception as exc:
            message = str(exc).lower()
            if "table is truncated" not in message:
                raise

            logger.warning(
                "BQ streaming insert blocked for %s (%s). Falling back to load job.",
                label,
                table_id,
            )
            load_job = self.bq_client.load_table_from_json(
                rows,
                table_id,
                job_config=bigquery.LoadJobConfig(
                    write_disposition=bigquery.WriteDisposition.WRITE_APPEND
                ),
            )
            load_job.result()
            logger.info("BQ fallback load job completed for %s", label)

    def _insert_bigquery(self, silver_rows, gold_rows):
        """Insert rows into BigQuery (cloud mode)."""
        silver_data = [
            self._sanitize_bq_row({
                "id": r['id'], "date": r['date'], "month_ref": r['month_ref'],
                "amount": r['amount'], "merchant_raw": r['merchant_raw'],
                "merchant_clean": r['merchant_clean'], "owner": r['owner'],
                "tenant_id": r['tenant_id'], "source_file": r['source_file'],
                "created_at": r['created_at']
            })
            for r in silver_rows
        ]

        self._append_bigquery_rows(TABLE_SILVER, silver_data, "silver")

        gold_data = [
            self._sanitize_bq_row({
                "id": r['id'], "date": r['date'], "month_ref": r['month_ref'],
                "amount": r['amount'], "merchant_clean": r['merchant_clean'],
                "category": r['category'], "subcategory": r['subcategory'],
                "type": r['type'], "owner": r['owner'],
                "tenant_id": r['tenant_id'], "created_at": r['created_at']
            })
            for r in gold_rows
        ]

        self._append_bigquery_rows(TABLE_GOLD, gold_data, "gold")

        return len(gold_data)
