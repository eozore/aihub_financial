# functions.py

import re
import numpy as np
import pandas as pd

def create_directories():
    """Cria as pastas data/input, data/output e data/backup se não existirem."""
    import os
    os.makedirs('data/input', exist_ok=True)
    os.makedirs('data/output', exist_ok=True)
    os.makedirs('data/backup', exist_ok=True)
    print("Pastas 'data/input', 'data/output' e 'data/backup' verificadas/criadas.")

def normalize_valor_column(df: pd.DataFrame, col_name: str = 'Valor') -> pd.DataFrame:
    """
    Padroniza uma coluna de valor monetário.
    - Substitui strings vazias por NaN.
    - Remove separador de milhares (pontos).
    - Troca vírgula por ponto decimal.
    - Converte para float (erros são transformados em NaN).
    """
    s = df[col_name].astype(str).str.strip()
    s = s.replace('', np.nan)
    # Garante que a substituição de pontos de milhar não afete decimais já com ponto.
    if s.str.contains(r'[,\.]').any():
        s = s.str.replace(r'\.(?=\d{3})', '', regex=True).str.replace(',', '.', regex=False)
    df[col_name] = pd.to_numeric(s, errors='coerce')
    return df

def unquote_iof(obs: str) -> str:
    """
    Se a observação tem o padrão 'IOF de "algo"', retorna apenas 'algo'.
    Caso contrário, retorna a observação sem alteração.
    """
    if pd.isna(obs):
        return obs
    m = re.match(r'IOF de\s*"([^"]+)"', str(obs))
    return m.group(1) if m else str(obs)

def extrair_yelumseg(obs: str) -> str:
    """
    Se 'Yelumseg' estiver na string, retorna apenas 'Yelumseg' para padronização.
    Caso contrário, retorna a string original.
    """
    if pd.isna(obs):
        return obs
    return 'Yelumseg' if 'Yelumseg' in str(obs) else str(obs)

def clean_transaction_title(title: str) -> str:
    """
    Aplica uma série de limpezas a um título de transação:
    - Remove informações de parcelas.
    - Extrai o conteúdo de strings de IOF.
    - Padroniza a descrição 'Yelumseg'.
    """
    if pd.isna(title):
        return title
    title = str(title)
    title = title.split(r' - Parcela')[0].strip()
    title = unquote_iof(title)
    title = extrair_yelumseg(title)
    return title
