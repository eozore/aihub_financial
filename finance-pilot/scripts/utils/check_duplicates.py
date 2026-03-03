import pandas as pd
import hashlib

def generate_id(row):
    raw_str = f"{row['Data']}-{row['Valor']}-{row['Observações']}-{row['Nome']}"
    return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

def find_duplicates():
    backup_path = '../data/legacy_backup.csv'
    df = pd.read_csv(backup_path)
    
    # Generate IDs
    df['hash_id'] = df.apply(generate_id, axis=1)
    
    # Find duplicates
    duplicates = df[df.duplicated(subset=['hash_id'], keep=False)]
    
    if duplicates.empty:
        print("No duplicates found in source based on hash logic.")
    else:
        print(f"Found {len(duplicates)} rows involved in duplication (originals + copies):")
        print(duplicates[['Data', 'Nome', 'Valor', 'Observações']].sort_values(by='Data').to_string())

if __name__ == "__main__":
    find_duplicates()
