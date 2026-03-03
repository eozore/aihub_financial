import pandas as pd
import json

def verify():
    legacy_path = '../data/legacy_backup.csv'
    gold_path = '../data/gold_transactions.json'
    
    # Legacy
    df_legacy = pd.read_csv(legacy_path)
    # Clean amount logic used in migration
    df_legacy['Valor_Clean'] = df_legacy['Valor'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)
    legacy_total = df_legacy['Valor_Clean'].sum()
    
    # Gold
    df_gold = pd.read_json(gold_path)
    gold_total = df_gold['amount'].sum()
    
    diff = legacy_total - gold_total
    
    print("--- Verification Report ---")
    print(f"Legacy Total: {legacy_total:,.2f}")
    print(f"Gold Total:   {gold_total:,.2f}")
    print(f"Difference:   {diff:,.2f}")
    
    if abs(diff) > 1:
        print("WARNING: Significant difference detected!")
        # Find missing rows?
    else:
        print("SUCCESS: Totals match (difference likely due to removed duplicates).")
        
    print(f"\nLegacy Row Count: {len(df_legacy)}")
    print(f"Gold Row Count:   {len(df_gold)}")

if __name__ == "__main__":
    verify()
