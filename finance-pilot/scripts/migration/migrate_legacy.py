import pandas as pd
import json
import hashlib
import datetime

def generate_id(row):
    # Unique ID based on key fields
    raw_str = f"{row['Data']}-{row['Valor']}-{row['Observações']}-{row['Nome']}"
    return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

def migrate():
    backup_path = '../data/legacy_backup.csv'
    map_path = '../data/category_map.json'
    output_path = '../data/gold_transactions.json'

    # 1. Load Data
    df = pd.read_csv(backup_path)
    
    with open(map_path, 'r', encoding='utf-8') as f:
        category_map = json.load(f)
        # Convert list to dict for faster lookup
        map_dict = {item['original_name']: item for item in category_map}

    print("Migrating data...")
    
    migrated_data = []
    
    for _, row in df.iterrows():
        merchant_key = str(row['Observações'])
        mapping = map_dict.get(merchant_key, {})
        
        # Clean numeric
        try:
            amount = float(str(row['Valor']).replace('.', '').replace(',', '.'))
        except:
            amount = 0.0

        # Construct Gold Record
        record = {
            "id": generate_id(row),
            "date": row['Data'], # We keep original date for now, will parse object later
            "amount": amount,
            "merchant_raw": merchant_key,
            "merchant_clean": mapping.get('suggested_clean_name', merchant_key),
            "category": mapping.get('suggested_category', 'Outros'),
            "subcategory": mapping.get('suggested_subcategory', 'Não Classificado'),
            "owner": row['Nome'],
            "type_legacy": row.get('Tipo', 'Individual'), # Keeping legacy for reference
            "group_legacy": row.get('Grupo', ''),
            "migrated_at": datetime.datetime.now().isoformat()
        }
        
        migrated_data.append(record)
        
    # Deduplicate by ID
    # Convert list of dicts to dataframe to easily remove duplicates by ID
    df_migrated = pd.DataFrame(migrated_data)
    initial_count = len(df_migrated)
    df_migrated.drop_duplicates(subset=['id'], inplace=True)
    final_count = len(df_migrated)
    
    print(f"Total Rows: {initial_count}")
    print(f"Unique Rows (by Hash): {final_count}")
    print(f"Duplicates Removed: {initial_count - final_count}")
    
    # Export
    df_migrated.to_json(output_path, orient='records', indent=4, force_ascii=False)
    print(f"Migration complete. Gold data saved to {output_path}")

if __name__ == "__main__":
    migrate()
