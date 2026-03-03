import pandas as pd
import json
import os

def analyze():
    input_path = '../data/legacy_backup.csv'
    output_path = '../data/distinct_merchants.json'
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found")
        return

    try:
        df = pd.read_csv(input_path)
        
        # Adjust column names based on previous knowledge ("Observações" seems to be merchant)
        if 'Observações' in df.columns:
            merchant_col = 'Observações'
        elif 'title' in df.columns:
            merchant_col = 'title'
        else:
            print(f"Columns found: {df.columns}")
            print("Could not identify merchant column.")
            return

        # Normalize
        df['clean_merchant'] = df[merchant_col].astype(str).str.strip()
        
        # Count frequency
        merchant_counts = df['clean_merchant'].value_counts()
        
        # Export to list of dicts for easy inspection
        result = []
        for merchant, count in merchant_counts.items():
            result.append({
                "original_name": merchant,
                "count": int(count),
                # Pre-fill structure for the mapping
                "suggested_clean_name": merchant.title(),
                "suggested_category": "",
                "suggested_subcategory": ""
            })
            
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
            
        print(f"Exported {len(result)} unique merchants to {output_path}")
        print("Top 10 most frequent:")
        print(merchant_counts.head(10))

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    analyze()
