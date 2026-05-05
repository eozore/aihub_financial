import pandas as pd
import glob
import os

def analyze_legacy_conflicts():
    # Pega o backup mais recente
    list_of_files = glob.glob('data/backup/*.csv') 
    if not list_of_files:
        print("Nenhum backup encontrado.")
        return
        
    latest_file = max(list_of_files, key=os.path.getctime)
    print(f"Analisando arquivo: {latest_file}")
    
    try:
        df = pd.read_csv(latest_file)
    except Exception as e:
        print(f"Erro ao ler CSV: {e}")
        return

    # Normaliza colunas chave
    if 'Observações' not in df.columns or 'Tipo' not in df.columns:
        print("Colunas necessárias (Observações, Tipo) não encontradas.")
        print(df.columns)
        return

    # Limpeza básica
    df['Estabelecimento'] = df['Observações'].astype(str).str.strip().str.lower()
    df['Tipo'] = df['Tipo'].astype(str).str.strip().str.title()
    
    # 1. Volume total
    print(f"\nTotal de Transações: {len(df)}")
    print(f"Estabelecimentos Únicos: {df['Estabelecimento'].nunique()}")
    
    # 2. Análise de Conflito de TIPO (Casal vs Individual)
    # Agrupa por Estabelecimento e conta quantos Tipos ÚNICOS cada um tem
    conflitos = df.groupby('Estabelecimento')['Tipo'].nunique()
    
    # Filtra quem tem mais de 1 tipo (Ex: Lanchonete X apareceu como Casal E como Individual)
    conflitos_reais = conflitos[conflitos > 1]
    
    print(f"\n--- Conflitos de Classificação (Casal vs Individual) ---")
    print(f"Estabelecimentos com classificação mista: {len(conflitos_reais)}")
    
    if len(conflitos_reais) > 0:
        print("\nTop 10 Estabelecimentos com dados mistos (Exemplo de inconsistência):")
        # Mostra o detalhe dos conflitantes
        for estab in conflitos_reais.index[:10]:
            print(f"\nEstabelecimento: {estab}")
            distribuicao = df[df['Estabelecimento'] == estab]['Tipo'].value_counts()
            print(distribuicao.to_string())

if __name__ == "__main__":
    analyze_legacy_conflicts()
