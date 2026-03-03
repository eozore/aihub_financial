#!/usr/bin/env python3
"""
Script para criar usuários no Firebase Authentication
Requer: pip install firebase-admin
"""

import firebase_admin
from firebase_admin import credentials, auth
import os

# IMPORTANTE: Você precisa baixar a Service Account Key do Firebase
# Console Firebase > Project Settings > Service Accounts > Generate New Private Key
# Salve como 'firebase-service-account.json' nesta pasta

def create_users():
    # Inicializa Firebase Admin
    cred_path = os.path.join(os.path.dirname(__file__), 'firebase-service-account.json')
    
    if not os.path.exists(cred_path):
        print("❌ Erro: Arquivo 'firebase-service-account.json' não encontrado!")
        print("\n📝 Como obter:")
        print("1. Acesse: https://console.firebase.google.com/")
        print("2. Projeto 'aifin-project' > ⚙️ Settings > Service Accounts")
        print("3. Clique em 'Generate New Private Key'")
        print("4. Salve o arquivo como 'firebase-service-account.json' nesta pasta")
        return
    
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    
    users_to_create = [
        {
            'email': 'victor@aifinance.com',
            'password': 'Victor@2026',  # Mude para uma senha segura!
            'display_name': 'Victor'
        },
        {
            'email': 'larissa@aifinance.com',
            'password': 'Larissa@2026',  # Mude para uma senha segura!
            'display_name': 'Larissa'
        }
    ]
    
    print("🚀 Criando usuários no Firebase Authentication...\n")
    
    for user_data in users_to_create:
        try:
            user = auth.create_user(
                email=user_data['email'],
                password=user_data['password'],
                display_name=user_data['display_name']
            )
            print(f"✅ Usuário criado: {user_data['email']}")
            print(f"   UID: {user.uid}")
            print(f"   Senha: {user_data['password']}")
            print()
        except auth.EmailAlreadyExistsError:
            print(f"⚠️  Usuário já existe: {user_data['email']}")
        except Exception as e:
            print(f"❌ Erro ao criar {user_data['email']}: {e}")
    
    print("\n✨ Concluído! Agora você pode fazer login com esses usuários.")

if __name__ == '__main__':
    create_users()
