import json

def build_dictionary():
    input_path = '../data/distinct_merchants.json'
    output_path = '../data/category_map.json'

    with open(input_path, 'r') as f:
        merchants = json.load(f)

    # Keywords for auto-classification
    keywords = {
        "Alimentação": {
            "Mercado": ["carrefour", "pao de acucar", "dia%", "supermercado", "assai", "atacadista", "market", "mercadinho", "hortifruti"],
            "Restaurante": ["restaurante", "bar", "lanchonete", "padaria", "cafe", "bistro", "churrascaria", "pizzaria", "hamburgueria", "sushi", "temaki", "outback", "madero", "potencia", "grillarica"],
            "Delivery": ["ifood", "rappi", "uber eats", "delivery", "ze delivery", "aiqfome", "ifd*"]
        },
        "Transporte": {
            "App": ["uber", "99app", "99 pop", "indriver"],
            "Combustível": ["posto", "shell", "ipiranga", "petrobras", "abastecimento", "auto posto", "combustivel"],
            "Pedágio/Estacionamento": ["sem parar", "veloe", "conectcar", "estapar", "estacionamento", "zona azul", "nutag"],
            "Manutenção": ["mecanica", "oficina", "pneu", "autocenter", "revisao", "lavajato"]
        },
        "Lazer": {
            "Streaming/Assinaturas": ["netflix", "spotify", "amazonprime", "disney", "hbo", "globoplay", "youtube", "apple.com", "google", "chatgpt", "openai"],
            "Viagem": ["airbnb", "booking", "azul", "gol", "latam", "hoteis", "hotel", "pousada", "trip"],
            "Entretenimento": ["cinema", "ingresso", "sympla", "eventim", "bilheteria", "show", "teatro"]
        },
        "Saúde": {
            "Farmácia": ["drogasil", "droga raia", "pague menos", "farma", "drogaria"],
            "Academia/Esporte": ["smartfit", "bluefit", "totalpass", "gympass", "natacao", "crossfit"],
            "Estética/Beleza": ["barber", "barbearia", "cabeleireiro", "salao", "estetica", "laser"]
        },
         "Habitação": {
            "Manutenção/Reforma": ["leroy", "telhanorte", "c&c", "sodimac", "material de construcao"],
            "Serviços": ["faxina", "diarista"],
        },
        "Pessoal": {
             "Vestuário": ["zara", "renner", "riachuelo", "c&a", "nike", "adidas", "roupa", "loja"],
             "Educação/Cursos": ["udemy", "alura", "coursera", "curso", "escola", "faculdade"]
        },
        "Receita": {
            "Salário": ["salario", "pagamento recibo", "ted recebida"],
            "Investimento": ["nu invest", "rico", "modal", "xp"],
             "Outros": ["reembolso", "cashback"]
        }
    }

    mapped_count = 0
    
    for item in merchants:
        original = item['original_name'].lower().replace("*", " ")
        found = False
        
        # Priority scan
        for category, subcategories in keywords.items():
            if found: break
            for subcategory, terms in subcategories.items():
                if found: break
                for term in terms:
                    if term in original:
                        item['suggested_category'] = category
                        item['suggested_subcategory'] = subcategory
                        found = True
                        mapped_count += 1
                        
        if not found:
            # Default fallback for known unlabeled recurring items
            if "pagamento" in original:
                 item['suggested_category'] = "Financeiro"
                 item['suggested_subcategory'] = "Pagamento Cartão"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merchants, f, indent=4, ensure_ascii=False)

    print(f"Auto-classified {mapped_count} out of {len(merchants)} merchants.")

if __name__ == "__main__":
    build_dictionary()
