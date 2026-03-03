"""
Script para baixar dados atualizados do Google Sheets (FinData)
e salvar como legacy_backup.csv para uso no Finance Pilot.
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from pathlib import Path
import datetime

# Paths
CREDS_PATH = Path(__file__).parent.parent.parent / "data-transactions" / "acesso.json"
OUTPUT_DIR = Path(__file__).parent.parent / "data"
LEGACY_BACKUP_PATH = OUTPUT_DIR / "legacy_backup.csv"

def download_findata():
    print(f"Authenticating with Google Sheets...")
    
    # 1. Authenticate
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(str(CREDS_PATH), scope)
    client = gspread.authorize(creds)
    
    # 2. Read FinData sheet
    print("Opening FinData spreadsheet...")
    sheet = client.open("FinData").sheet1
    records = sheet.get_all_records(numericise_ignore=['all'])
    df = pd.DataFrame(records)
    
    print(f"Downloaded {len(df)} rows from FinData")
    print(f"Columns: {list(df.columns)}")
    
    # 3. Show date range
    if 'Data' in df.columns:
        # Parse dates to check range
        df['_parsed_date'] = pd.to_datetime(df['Data'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        min_date = df['_parsed_date'].min()
        max_date = df['_parsed_date'].max()
        print(f"Date range: {min_date} to {max_date}")
        df = df.drop(columns=['_parsed_date'])
    
    # 4. Save backup
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(LEGACY_BACKUP_PATH, index=False)
    print(f"\nSaved to: {LEGACY_BACKUP_PATH}")
    
    # Also save timestamped backup
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_path = OUTPUT_DIR / f"findata_backup_{timestamp}.csv"
    df.to_csv(timestamped_path, index=False)
    print(f"Timestamped backup: {timestamped_path}")
    
    return df

if __name__ == "__main__":
    download_findata()
