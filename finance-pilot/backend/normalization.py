import re
import json
import os
from pathlib import Path

# Carregar mapa do JSON
MAP_FILE = Path(__file__).parent / "merchant_map.json"

def load_maps():
    if not MAP_FILE.exists():
        return {}, {}
    
    with open(MAP_FILE, 'r') as f:
        data = json.load(f)
        
    return data.get("mappings", {}), data.get("replacements", {})

MAPPINGS, REPLACEMENTS = load_maps()

# Regex padrão para limpeza técnica (parcelas, datas, etc)
CLEANUP_PATTERNS = [
    (r'\s*-\s*Parcela\s*\d+/\d+', ''),  # Remove " - Parcela 1/12"
    (r'\s*\d+/\d+', ''),               # Remove " 01/12" solto
    (r'\*', ' '),                      # Troca * por espaço
    (r'\s+', ' '),                     # Remove espaços duplos
]

def _compile_pattern(raw: str) -> re.Pattern:
    """
    Converte chaves com wildcard '*' em regex.
    Ex: 'Ifd*' -> 'Ifd.*'
    """
    pattern = re.escape(raw).replace(r'\*', '.*')
    return re.compile(pattern, flags=re.IGNORECASE)

def normalize_merchant(raw_name: str) -> str:
    """
    Normaliza o nome do estabelecimento usando JSON de configuração.
    """
    if not raw_name or str(raw_name).lower() == 'nan':
        return "Desconhecido"
        
    normalized = str(raw_name).strip()
    
    # 1. Limpeza Técnica (Regex Hardcoded)
    for pattern, replacement in CLEANUP_PATTERNS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
    # 2. Substituições Simples (do JSON) - suporta wildcard '*'
    for target, replacement in REPLACEMENTS.items():
        pattern = _compile_pattern(target)
        normalized = pattern.sub(replacement, normalized)

    normalized = normalized.strip().title()
    
    # 3. Mapeamento Inteligente (do JSON)
    # Verifica se chaves existem dentro do nome normalizado
    
    # Ordenar por tamanho para dar prioridade a matches mais longos
    sorted_keys = sorted(MAPPINGS.keys(), key=len, reverse=True)
    
    for key in sorted_keys:
        target_val = MAPPINGS[key]
        pattern = _compile_pattern(key)
        if pattern.search(normalized):
            return target_val
            
    return normalized.strip()

# Teste rápido
if __name__ == "__main__":
    tests = [
        "Uber *Trip Help",
        "Uber Do Brasil",
        "IOF de 'Uber'",
        "Amazon Prime Canais",
        "Mp *Padaria Do Zé",
        "Ec *Posto Gasolina",
        "Magazine Luiza - Parcela 2/10",
        "Netflix.Com",
        "Apple.Com/Bill"
    ]
    
    print(f"{'Original':<30} -> {'Normalizado'}")
    print("-" * 50)
    for t in tests:
        print(f"{t:<30} -> {normalize_merchant(t)}")
