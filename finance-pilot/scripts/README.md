# 🛠️ Scripts

Utility scripts for migration, setup, and maintenance.

## Folder Structure

```
scripts/
├── migration/          # Data migration scripts
├── setup/              # Firebase/GCP setup scripts
└── utils/              # Utility helpers
```

---

## Migration Scripts

Located in `migration/`:

| Script | Description |
|--------|-------------|
| `migrate_sqlite_to_firestore.py` | Migrate data from SQLite to Firestore + BigQuery |
| `migrate_legacy.py` | Migrate legacy CSV data format |
| `migrate_to_cloud.py` | Upload local data to cloud storage |

### Usage: SQLite to Firestore Migration

```bash
cd scripts/migration
python migrate_sqlite_to_firestore.py

# Dry run (no actual changes)
python migrate_sqlite_to_firestore.py --dry-run
```

---

## Setup Scripts

Located in `setup/`:

| Script | Description |
|--------|-------------|
| `configure_firebase.py` | Configure Firebase project settings |
| `create_firebase_users.py` | Create Victor and Larissa users |
| `setup_firebase_complete.py` | Full Firebase setup automation |

### Usage: Create Users

```bash
cd scripts/setup
python create_firebase_users.py
```

> Note: Requires service account key

---

## Utility Scripts

Located in `utils/`:

| Script | Description |
|--------|-------------|
| `build_dictionary.py` | Build category dictionary from transactions |
| `check_duplicates.py` | Find duplicate transactions |
| `extract_merchants.py` | Extract unique merchant names |
| `run_processor.py` | Run processor on local files |
| `verify_migration.py` | Verify migration completeness |

### Usage: Check Duplicates

```bash
cd scripts/utils
python check_duplicates.py
```

---

## Environment

All scripts expect these environment variables:

```bash
export PROJECT_ID=aifin-project
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```
