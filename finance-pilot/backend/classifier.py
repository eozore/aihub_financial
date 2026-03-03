import sqlite3
import os
from pathlib import Path

# Config
DB_PATH = Path(__file__).parent / "finance.db"

# Mapeamento de palavras-chave -> Categoria
CATEGORY_KEYWORDS = {
    # Alimentação e Restaurantes
    "Bar/Restaurante": [
        "potencia", "restaurante", "bar ", "barbearia", "churras", "grill", 
        "pizza", "sushi", "hamburgu", "lanchonete", "cafe ", "padaria",
        "cerveja", "chopp", "pub", "boteco", "camelo", "esquina", "camarada",
        "pantucci", "papila", "bullguer", "cacilda", "fukuya", "nagairo",
        "ilhabela", "prainha", "arena resenha"
    ],
    "Delivery": [
        "ifood", "rappi", "uber eats", "delivery", "ifd*"
    ],
    "Mercado": [
        "mercado", "supermercado", "atacadao", "carrefour", "extra", "pao de acucar",
        "assai", "hortifruti", "verduras", "bp xpress", "chocolandia", "eskinao"
    ],
    "Uber/Onibus": [
        "uber", "99", "cabify", "taxi", "onibus", "metro", "bilhete unico"
    ],
    "Combustivel": [
        "posto", "shell", "br ", "ipiranga", "gasolina", "combustivel", "piloto auto",
        "petro", "vaca preta"
    ],
    "Pedagio": [
        "pedagio", "nutag", "sem parar", "conectcar", "veloe"
    ],
    "Aluguel": [
        "aluguel", "imobiliaria"
    ],
    "Condominio": [
        "condominio", "taxa condominial"
    ],
    "Luz/Internet": [
        "luz", "energia", "enel", "cpfl", "internet", "net ", "claro", "vivo", "tim"
    ],
    "Streaming": [
        "netflix", "spotify", "amazon prime", "disney", "hbo", "apple.com/bill",
        "apple tv", "youtube premium", "amazonprimebr", "prime canais"
    ],
    "Saúde/Estética": [
        "farmacia", "drogaria", "medico", "hospital", "clinica", "dentista",
        "totalpass", "academia", "gympass", "salao", "cabelo", "barbeiro",
        "gio barbeiro", "vila pompeia", "breakfit"
    ],
    "Vestuário": [
        "roupa", "loja", "shopping", "vestuario", "sapato", "tenis"
    ],
    "Curso": [
        "curso", "escola", "faculdade", "udemy", "coursera", "alura",
        "treinamento", "sete treinamentos", "linkedin"
    ],
    "Projeto Pessoal": [
        "chatgpt", "openai", "aws", "google cloud", "cloud", "github",
        "canva", "figma", "notion", "digital ocean", "sixhq", "colab"
    ],
    "Airbnb/Hotel": [
        "airbnb", "hotel", "pousada", "booking", "expedia", "ibis"
    ],
    "Voos": [
        "azul", "latam", "gol ", "voo", "passagem aerea", "aeroporto"
    ],
    "ItensdeCasa": [
        "shopee", "mercado livre", "amazon", "casa", "decoracao", "moveis"
    ],
    "Faxina": [
        "faxina", "diarista", "limpeza"
    ],
    "Presentes": [
        "presente", "gift", "flor", "joalheria"
    ],
    "Manutenção/Revisão": [
        "mecanico", "oficina", "revisao", "pneu", "lavajato", "rodamalu"
    ],
    "Luana": [
        "luana"
    ],
}

# Palavras-chave que indicam gasto INDIVIDUAL da Larissa no cartão do Victor
# (A Larissa tem um cartão adicional da conta do Victor)
LARISSA_KEYWORDS = [
    "loja feminina", "esmalte", "unha", "salao de beleza", "sephora",
    "renner", "c&a", "riachuelo", "zara", "forever 21",
    # Você pode adicionar mais padrões específicos aqui
]

# Palavras-chave que indicam gasto INDIVIDUAL do Victor
VICTOR_INDIVIDUAL_KEYWORDS = [
    "barbeiro", "barbearia", "cerveja artesanal", "futebol", "joga10",
    "arena resenha", "gio barbeiro", "vila pompeia", "totalpass",
    "linkedin", "chatgpt", "openai", "github", "digital ocean"
]

# Palavras-chave que indicam gasto de CASAL (Shared)
SHARED_KEYWORDS = [
    "aluguel", "condominio", "luz", "internet", "mercado", "supermercado",
    "ifood", "delivery", "netflix", "amazon prime", "spotify",
    "combustivel", "posto", "pedagio", "nutag", "uber",
    "restaurante", "airbnb", "hotel", "voo", "passagem"
]

# ============================================================
# NOVAS REGRAS BASEADAS EM ANÁLISE DE DADOS (Feb 2026)
# ============================================================

# Categorias que SEMPRE são Shared (baseado em análise: >90% shared no histórico)
ALWAYS_SHARED_CATEGORIES = [
    "Aluguel",        # 91 shared / 8 individual
    "Condominio",     # 11 shared / 0 individual
    "Luz/Internet",   # 21 shared / 0 individual
    "Faxina",         # 10 shared / 0 individual
    "Streaming",      # 49 shared / 4 individual
    "Mercado",        # 33 shared / 4 individual
    "ItensdeCasa",    # 25 shared / 4 individual
    "Manutenção/Revisão",  # 16 shared / 0 individual
]

# Categorias que SEMPRE são Individual (baseado em análise: >80% individual no histórico)
ALWAYS_INDIVIDUAL_CATEGORIES = [
    "Projeto Pessoal",  # 9 shared / 104 individual
    "Vestuário",        # 1 shared / 26 individual
    "Curso",            # 1 shared / 7 individual
    "Luana",            # 4 shared / 9 individual
    "Saúde/Estética",   # 19 shared / 109 individual (includes personal gym, salon)
]

# Merchants que FORÇAM tipo Shared (override sobre qualquer regra)
# Baseado em erro de classificação detectado: Pedagio (NuTag) = 21 Individual quando deveria ser Shared
FORCE_SHARED_MERCHANTS = [
    "nutag", "pedagio", "sem parar", "veloe", "conectcar",  # Pedágio = sempre compartilhado
    "canva",  # Uso do casal (11 shared / 2 individual)
    "apple.com/bill",  # Streaming família (8 shared / 3 individual)
]

def get_history_stats(merchant_clean: str):
    """
    Consulta o histórico no SQLite para calcular a % de vezes que este merchant foi Shared.
    """
    try:
        if not os.path.exists(DB_PATH):
           return 0.0, 0
           
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Busca exata ou parcial? Vamos começar com exata para ser conservador
        c.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN type = 'Shared' THEN 1 ELSE 0 END) as shared_count
            FROM transactions_gold
            WHERE merchant_clean = ? COLLATE NOCASE
        """, (merchant_clean.strip(),))
        
        row = c.fetchone()
        conn.close()
        
        if not row or row[0] == 0:
            return 0.0, 0
            
        total = row[0]
        shared = row[1] or 0
        return (shared / total), total
        
    except Exception as e:
        print(f"Error fetching stats for {merchant_clean}: {e}")
        return 0.0, 0

def classify_transaction(description: str, amount: float, owner: str = "Victor", category: str = None) -> dict:
    """
    Classifica uma transação baseada em regras hierárquicas:
    
    Prioridade:
    1. FORCE_SHARED_MERCHANTS (override absoluto para pedágio, etc)
    2. ALWAYS_SHARED_CATEGORIES / ALWAYS_INDIVIDUAL_CATEGORIES
    3. Histórico do estabelecimento (se > 60% shared → Shared)
    4. Fallback para palavras-chave
    """
    desc_clean = description.strip()
    desc_lower = desc_clean.lower()
    
    # 1. Detectar Categoria via palavras-chave
    detected_category = category or "Outro"
    if detected_category == "Outro" or not category:
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in desc_lower:
                    detected_category = cat
                    break
            if detected_category != "Outro":
                break
    
    # ============================================================
    # NOVA LÓGICA: Regras Hierárquicas para Tipo
    # ============================================================
    
    detected_type = None  # Será definido por prioridade
    rule_used = "default"
    
    # REGRA 1: Force Shared Merchants (override absoluto)
    for merchant_kw in FORCE_SHARED_MERCHANTS:
        if merchant_kw.lower() in desc_lower:
            detected_type = "Shared"
            rule_used = f"force_merchant:{merchant_kw}"
            break
    
    # REGRA 2: Categorias que sempre são Shared
    if detected_type is None and detected_category in ALWAYS_SHARED_CATEGORIES:
        detected_type = "Shared"
        rule_used = f"category:{detected_category}"
    
    # REGRA 3: Categorias que sempre são Individual
    if detected_type is None and detected_category in ALWAYS_INDIVIDUAL_CATEGORIES:
        detected_type = "Individual"
        rule_used = f"category:{detected_category}"
    
    # REGRA 4: Histórico do estabelecimento (se não foi definido pelas regras acima)
    if detected_type is None:
        shared_ratio, total_history = get_history_stats(desc_clean)
        
        if total_history > 0:
            if shared_ratio > 0.6:
                detected_type = "Shared"
                rule_used = f"history:{shared_ratio:.0%}"
            elif amount > 80 and shared_ratio > 0.3:
                detected_type = "Shared"
                rule_used = f"history+amount:{shared_ratio:.0%}"
            else:
                detected_type = "Individual"
                rule_used = f"history:{shared_ratio:.0%}"
        else:
            # REGRA 5: Fallback para palavras-chave (sem histórico)
            if owner == "Larissa":
                is_shared = any(kw.lower() in desc_lower for kw in SHARED_KEYWORDS)
                detected_type = "Shared" if is_shared else "Individual"
                rule_used = "keyword_larissa"
            else:
                is_victor_individual = any(kw.lower() in desc_lower for kw in VICTOR_INDIVIDUAL_KEYWORDS)
                if is_victor_individual:
                    detected_type = "Individual"
                    rule_used = "keyword_victor"
                else:
                    is_shared = any(kw.lower() in desc_lower for kw in SHARED_KEYWORDS)
                    if is_shared and amount > 50:
                        detected_type = "Shared"
                        rule_used = "keyword_shared"
                    else:
                        detected_type = "Individual"
                        rule_used = "default"
    
    return {
        "category": detected_category,
        "type": detected_type,
        "debug_info": f"rule:{rule_used}"
    }


def enrich_transactions(rows: list, owner: str = "Victor") -> list:
    """
    Enriquece lista de transações com categoria e tipo.
    """
    for row in rows:
        amount = float(row.get("amount", 0))
        description = row.get("merchant_clean", "")
        
        classification = classify_transaction(description, amount, owner)
        
        # Só atualizar se não tiver categoria definida ou for "Outros"
        if not row.get("category") or row.get("category") == "Outros":
            row["category"] = classification["category"]
        
        # Atualizar tipo (aqui queremos forçar nossa recém calculada inferência)
        # Mas mantemos respeito se já veio algo muito específico (raro no fluxo atual)
        row["type"] = classification["type"]
    
    return rows


# Para teste
if __name__ == "__main__":
    test_cases = [
        ("Potencia Gaucha", "Victor"),
        ("iFood - NuPay", "Victor"),
        ("NuTag*GGJ0C95", "Victor"),
        ("Totalpass", "Victor"),
        ("Mercado Carrefour", "Victor"),
        ("Airbnb * Hm2qz5t4cx", "Victor"),
        ("Apple.Com/Bill", "Victor"),
        ("Uber Uber *Trip", "Victor"),
        ("LinkedIn", "Victor"),
    ]
    
    for desc, owner in test_cases:
        result = classify_transaction(desc, owner)
        print(f"{desc:30} -> {result['category']:20} | {result['type']}")
