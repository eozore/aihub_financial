# main.py (Corrigido)

# 1. Bibliotecas padrão
import datetime
import os
import pandas as pd

# 2. Bibliotecas de terceiros
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe

# 3. Funções locais
from functions import (create_directories, normalize_valor_column,
                         clean_transaction_title)


def main():
    """
    Função principal para automatizar a atualização da planilha de finanças.
    """
    # --- SETUP INICIAL ---
    create_directories()
    GDRIVE_KEY_FILE = '../acesso.json'
    GSHEET_NAME = 'FinData'
    GSHEET_BACKUP_NAME = 'Backup'
    INPUT_CSV_PATH = 'data/input/nubankagosto.csv'
    
    print("--- INICIANDO PROCESSO DE ATUALIZAÇÃO FINANCEIRA ---")

    # --- 1. AUTENTICAÇÃO E LEITURA DO GOOGLE SHEETS ---
    print("\n[PASSO 1/7] Autenticando com a API do Google Sheets...")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(GDRIVE_KEY_FILE, scope)
        client = gspread.authorize(creds)
        print("Autenticação bem-sucedida!")
    except Exception as e:
        print(f"ERRO: Falha na autenticação. Verifique o arquivo '{GDRIVE_KEY_FILE}'. Detalhes: {e}")
        return

    # --- 2. LEITURA E BACKUP DOS DADOS HISTÓRICOS ---
    print(f"\n[PASSO 2/7] Lendo dados históricos da planilha '{GSHEET_NAME}'...")
    try:
        sheet_findata = client.open(GSHEET_NAME).sheet1
        # Lê os dados como texto para preservar o formato original da data
        finhistorico = pd.DataFrame(sheet_findata.get_all_records(numericise_ignore=['all']))
        print("Leitura concluída. Amostra dos dados históricos:")
        print(finhistorico.head())

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join('data/backup', f'FinData_backup_{timestamp}.csv')
        finhistorico.to_csv(backup_path, index=False)
        print(f"Backup dos dados originais salvo em: '{backup_path}'")

        sheet_backup = client.open(GSHEET_BACKUP_NAME).sheet1
        sheet_backup.clear()
        set_with_dataframe(sheet_backup, finhistorico)
        print(f"Backup também atualizado na planilha online '{GSHEET_BACKUP_NAME}'.")

    except Exception as e:
        print(f"ERRO: Falha ao ler ou fazer backup da planilha '{GSHEET_NAME}'. Detalhes: {e}")
        return

    # --- 3. PRÉ-PROCESSAMENTO DO HISTÓRICO ---
    print("\n[PASSO 3/7] Pré-processando dados históricos...")
    # Converte para datetime para poder fazer comparações
    finhistorico['Data'] = pd.to_datetime(finhistorico['Data'], format='%d/%m/%Y', errors='coerce')
    finhistorico = normalize_valor_column(finhistorico, 'Valor')
    finhistorico['Observações'] = finhistorico['Observações'].apply(clean_transaction_title)
    
    print("Processamento concluído. Amostra dos dados históricos limpos:")
    print(finhistorico[['Data', 'Valor', 'Observações']].head())

    cutoff_date = pd.to_datetime('2025-02-28')
    processed = finhistorico[finhistorico['Data'] > cutoff_date].copy()
    processed = processed.drop(columns=['Data', 'Valor'], errors='ignore').drop_duplicates(subset=['Observações'], keep='first')
    print(f"\nEncontradas {len(processed)} observações únicas após {cutoff_date.date()} para verificação de duplicatas.")

    # --- 4. LEITURA DO CSV DO NUBANK ---
    print(f"\n[PASSO 4/7] Lendo novas transações do arquivo '{INPUT_CSV_PATH}'...")
    try:
        df_new = pd.read_csv(INPUT_CSV_PATH)
        print("Leitura do CSV bem-sucedida. Amostra das novas transações:")
        print(df_new.head())
    except FileNotFoundError:
        print(f"ERRO: Arquivo '{INPUT_CSV_PATH}' não encontrado.")
        return

    # --- 5. PROCESSAMENTO DAS NOVAS TRANSAÇÕES ---
    print("\n[PASSO 5/7] Processando e agrupando novas transações...")
    df_new['date'] = pd.to_datetime(df_new['date'], errors='coerce')
    df_new['title'] = df_new['title'].apply(clean_transaction_title)

    df_grouped = df_new.groupby('title', as_index=False).agg(
        Data=('date', 'min'),
        Valor=('amount', 'sum')
    )
    df_grouped.rename(columns={'title': 'Observações'}, inplace=True)
    df_final = df_grouped[df_grouped['Valor'] > 0].copy()

    print("Novas transações agrupadas. Amostra:")
    print(df_final.head())
    
    # --- 6. MERGE PARA EVITAR DUPLICATAS E CONCATENAÇÃO ---
    print("\n[PASSO 6/7] Removendo duplicatas e combinando dados...")
    df_novas = pd.merge(df_final, processed[['Observações']], on='Observações', how='left', indicator=True)
    df_novas = df_novas[df_novas['_merge'] == 'left_only'].drop(columns=['_merge'])
    
    if df_novas.empty:
        print("Nenhuma nova transação encontrada para adicionar. Processo finalizado.")
        return
        
    print(f"Encontrados {len(df_novas)} novos registros para adicionar. Amostra:")
    print(df_novas.head())

    df_novas['Nome'] = 'Victor'
    
    # Mantém a coluna 'Data' como datetime durante a concatenação # <-- ALTERAÇÃO AQUI
    final_df = pd.concat([finhistorico, df_novas], ignore_index=True)
    
    final_df['Valor'] = pd.to_numeric(final_df['Valor'], errors='coerce').fillna(0).astype(int)
    
    # --- 7. SALVANDO OS DADOS ATUALIZADOS ---
    print("\n[PASSO 7/7] Formatando e salvando dados atualizados...")
    
    # Converte TODA a coluna 'Data' para o formato de texto ANTES de salvar # <-- ALTERAÇÃO AQUI
    final_df['Data'] = final_df['Data'].dt.strftime('%d/%m/%Y')
    
    print("Formatação final concluída. Amostra final (últimas linhas):")
    print(final_df.tail())

    output_path = os.path.join('data/output', f'FinData_atualizado_{timestamp}.csv')
    final_df.to_csv(output_path, index=False) # Não precisa mais de date_format
    print(f"Arquivo final salvo localmente em: '{output_path}'")
    
    try:
        sheet_findata.clear()
        # Envia para o gspread com as datas já como texto formatado
        set_with_dataframe(sheet_findata, final_df.fillna(''))
        print(f"Planilha '{GSHEET_NAME}' atualizada com sucesso no Google Sheets!")
    except Exception as e:
        print(f"ERRO: Falha ao atualizar a planilha '{GSHEET_NAME}'. Detalhes: {e}")

    print("\n--- PROCESSO CONCLUÍDO --- ✅")


if __name__ == '__main__':
    main()
