import pandas as pd
import os
import glob

def clean_currency(x):
    if isinstance(x, str):
        return float(x.replace(',', ''))
    return x

def analyze_finances():
    input_dir = 'nubank/input'
    all_files = glob.glob(os.path.join(input_dir, "*.csv"))
    
    df_list = []
    for filename in all_files:
        try:
            df = pd.read_csv(filename)
            df_list.append(df)
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            
    if not df_list:
        print("No CSV files found.")
        return

    full_df = pd.concat(df_list, ignore_index=True)
    
    # Ensure correct types
    full_df['date'] = pd.to_datetime(full_df['date'], errors='coerce')
    full_df['amount'] = pd.to_numeric(full_df['amount'], errors='coerce')
    
    # Separate Income and Expenses
    # In many bank exports, expenses are positive and income is negative or vice versa.
    # Looking at nubankdezembro.csv:
    # 20.85 (Expense)
    # -10176.18 (Pagamento recebido - Income/Payment)
    # So: Positive = Expense, Negative = Income/Credit
    
    expenses = full_df[full_df['amount'] > 0].copy()
    income = full_df[full_df['amount'] < 0].copy()
    
    # Analysis per Month
    full_df['month_year'] = full_df['date'].dt.to_period('M')
    
    monthly_summary = full_df.groupby('month_year')['amount'].sum()
    monthly_expenses = full_df[full_df['amount'] > 0].groupby('month_year')['amount'].sum()
    monthly_income = full_df[full_df['amount'] < 0].groupby('month_year')['amount'].sum()
    
    print("--- Financial Analysis Report ---\n")
    
    print("1. Monthly Overview (Net, Expenses, Income):")
    overview = pd.DataFrame({
        'Net': monthly_summary,
        'Expenses': monthly_expenses,
        'Income': monthly_income
    }).fillna(0)
    print(overview.to_string())
    print("\n")
    
    print("2. Total Stats:")
    print(f"Total Expenses Recorded: {expenses['amount'].sum():.2f}")
    print(f"Total Income/Credits Recorded: {income['amount'].sum():.2f}")
    print(f"Net Total: {full_df['amount'].sum():.2f}")
    print("\n")
    
    print("3. Top 10 Expenses (All Time):")
    print(expenses.nlargest(10, 'amount')[['date', 'title', 'amount']])
    print("\n")
    
    print("4. Top 10 Merchants/Titles by Total Spent:")
    top_merchants = expenses.groupby('title')['amount'].sum().nlargest(10)
    print(top_merchants)
    print("\n")

    print("5. Average Monthly Expense:")
    print(f"{monthly_expenses.mean():.2f}")

if __name__ == "__main__":
    analyze_finances()
