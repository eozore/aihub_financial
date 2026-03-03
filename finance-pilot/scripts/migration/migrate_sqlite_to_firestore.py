"""
Migration Script: SQLite → Firestore + BigQuery

This script:
1. Reads all transactions from local SQLite
2. Re-classifies them using the updated classifier rules
3. Inserts them into Firestore
4. Syncs to BigQuery for analytics

Usage:
    python migrate_sqlite_to_firestore.py
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from google.cloud import firestore, bigquery
from classifier import classify_transaction
from normalization import normalize_merchant

# Config
PROJECT_ID = os.environ.get("PROJECT_ID", "aifin-project")
DB_PATH = Path(__file__).parent.parent / "backend" / "finance.db"
FIRESTORE_COLLECTION = "transactions"
TABLE_GOLD = f"{PROJECT_ID}.finance_analytics.transactions_gold"


def get_sqlite_transactions():
    """Read all transactions from SQLite."""
    if not DB_PATH.exists():
        print(f"SQLite database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT * FROM transactions_gold ORDER BY date DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    
    print(f"✓ Found {len(rows)} transactions in SQLite")
    return rows


def reclassify_transaction(tx: dict) -> dict:
    """Apply new classifier rules to a transaction."""
    description = tx.get('merchant_clean', '') or ''
    amount = float(tx.get('amount') or 0)
    owner = tx.get('owner', 'Victor') or 'Victor'
    category = tx.get('category')
    
    # Normalize merchant name
    normalized = normalize_merchant(description)
    
    # Re-classify with new rules
    classification = classify_transaction(normalized, amount, owner, category)
    
    # Update transaction
    tx['merchant_clean'] = normalized
    tx['category'] = classification['category']
    tx['type'] = classification['type']
    tx['_classification_rule'] = classification['debug_info']
    
    return tx


def migrate_to_firestore(transactions: list, dry_run: bool = False):
    """Insert transactions into Firestore."""
    if dry_run:
        print("DRY RUN: Would insert to Firestore")
        return
    
    db = firestore.Client(project=PROJECT_ID)
    collection = db.collection(FIRESTORE_COLLECTION)
    
    # Delete existing documents
    print("Deleting existing Firestore documents...")
    docs = collection.stream()
    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    print(f"✓ Deleted {deleted} existing documents")
    
    # Insert new transactions
    print(f"Inserting {len(transactions)} transactions into Firestore...")
    batch = db.batch()
    batch_count = 0
    
    for i, tx in enumerate(transactions):
        doc_id = tx.get('id') or f"{tx['date']}-{i}"
        doc_ref = collection.document(doc_id)
        
        # Clean up internal fields
        tx_clean = {k: v for k, v in tx.items() if not k.startswith('_')}
        tx_clean['migrated_at'] = datetime.now().isoformat()
        
        batch.set(doc_ref, tx_clean)
        batch_count += 1
        
        # Firestore batch limit is 500
        if batch_count >= 450:
            batch.commit()
            print(f"  Committed batch ({i+1}/{len(transactions)})")
            batch = db.batch()
            batch_count = 0
    
    # Commit remaining
    if batch_count > 0:
        batch.commit()
    
    print(f"✓ Inserted {len(transactions)} transactions into Firestore")


def sync_to_bigquery(transactions: list, dry_run: bool = False):
    """Sync transactions to BigQuery for analytics."""
    if dry_run:
        print("DRY RUN: Would sync to BigQuery")
        return
    
    client = bigquery.Client(project=PROJECT_ID)
    
    # Truncate existing table
    print("Truncating BigQuery table...")
    query = f"DELETE FROM `{TABLE_GOLD}` WHERE 1=1"
    try:
        client.query(query).result()
        print("✓ Truncated BigQuery table")
    except Exception as e:
        print(f"Warning: Could not truncate table: {e}")
    
    # Prepare rows for insertion
    rows_to_insert = []
    for tx in transactions:
        row = {
            'id': tx.get('id'),
            'date': tx.get('date'),
            'month_ref': tx.get('month_ref'),
            'amount': float(tx.get('amount') or 0),
            'merchant_clean': tx.get('merchant_clean') or '',
            'category': tx.get('category') or 'Outro',
            'subcategory': tx.get('subcategory') or '',
            'owner': tx.get('owner') or 'Victor',
            'type': tx.get('type') or 'Individual',
            'created_at': tx.get('created_at'),
        }
        rows_to_insert.append(row)
    
    # Insert in batches
    print(f"Inserting {len(rows_to_insert)} rows into BigQuery...")
    table_ref = client.dataset("finance_analytics").table("transactions_gold")
    
    errors = client.insert_rows_json(table_ref, rows_to_insert)
    if errors:
        print(f"Errors inserting to BigQuery: {errors[:5]}...")
    else:
        print(f"✓ Inserted {len(rows_to_insert)} rows into BigQuery")


def print_classification_summary(transactions: list):
    """Print summary of classification changes."""
    rules = {}
    type_counts = {'Shared': 0, 'Individual': 0}
    
    for tx in transactions:
        rule = tx.get('_classification_rule', 'unknown')
        rules[rule] = rules.get(rule, 0) + 1
        type_counts[tx.get('type', 'Individual')] += 1
    
    print("\n" + "="*50)
    print("CLASSIFICATION SUMMARY")
    print("="*50)
    print(f"\nType Distribution:")
    print(f"  Shared: {type_counts['Shared']}")
    print(f"  Individual: {type_counts['Individual']}")
    
    print(f"\nRules Applied:")
    for rule, count in sorted(rules.items(), key=lambda x: -x[1]):
        print(f"  {rule}: {count}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate SQLite to Firestore + BigQuery")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually migrate")
    parser.add_argument("--skip-firestore", action="store_true", help="Skip Firestore migration")
    parser.add_argument("--skip-bigquery", action="store_true", help="Skip BigQuery sync")
    args = parser.parse_args()
    
    print("="*50)
    print("FINANCE DATA MIGRATION")
    print("="*50)
    print(f"Project: {PROJECT_ID}")
    print(f"SQLite: {DB_PATH}")
    print(f"Dry Run: {args.dry_run}")
    print()
    
    # Step 1: Read from SQLite
    transactions = get_sqlite_transactions()
    if not transactions:
        print("No transactions to migrate")
        return
    
    # Step 2: Re-classify with new rules
    print("\nRe-classifying transactions with new rules...")
    for tx in transactions:
        reclassify_transaction(tx)
    print("✓ Re-classification complete")
    
    # Print summary
    print_classification_summary(transactions)
    
    # Step 3: Migrate to Firestore
    if not args.skip_firestore:
        print("\n" + "-"*50)
        migrate_to_firestore(transactions, dry_run=args.dry_run)
    
    # Step 4: Sync to BigQuery
    if not args.skip_bigquery:
        print("\n" + "-"*50)
        sync_to_bigquery(transactions, dry_run=args.dry_run)
    
    print("\n" + "="*50)
    print("MIGRATION COMPLETE")
    print("="*50)


if __name__ == "__main__":
    main()
