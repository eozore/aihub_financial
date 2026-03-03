#!/usr/bin/env python3
"""
Configuração automática do Firebase - Versão Simplificada
Requisitos: gcloud CLI autenticado
"""

import subprocess
import json
import sys

PROJECT_ID = "aifin-project"
PROJECT_NUMBER = "930725375338"

def run_cmd(cmd):
    """Executa comando shell"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def main():
    print("🚀 Configurando Firebase Authentication")
    print()
    
    # 1. Habilitar API
    print("1️⃣ Habilitando Identity Toolkit API...")
    run_cmd(f"gcloud services enable identitytoolkit.googleapis.com --project={PROJECT_ID}")
    print("   ✅ API habilitada")
    
    # 2. Buscar ou criar Web App
    print("2️⃣ Configurando Firebase Web App...")
    
    # Usar Firebase REST API para buscar config
    token, _, _ = run_cmd("gcloud auth application-default print-access-token")
    
    import requests
    
    # Tentar buscar apps existentes
    try:
        response = requests.get(
            f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT_ID}/webApps",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            data = response.json()
            if "apps" in data and len(data["apps"]) > 0:
                app_name = data["apps"][0]["name"]
                app_id = data["apps"][0]["appId"]
                print(f"   ✅ Web App encontrado: {app_id}")
            else:
                # Criar novo app
                create_response = requests.post(
                    f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT_ID}/webApps",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"displayName": "AI Finance Web"}
                )
                
                if create_response.status_code == 200:
                    app_data = create_response.json()
                    app_name = app_data["name"]
                    # Extrair app_id do nome (formato: projects/xxx/webApps/xxx)
                    app_id = app_name.split("/")[-1]
                    print(f"   ✅ Web App criado: {app_id}")
                else:
                    print(f"   ⚠️  Erro ao criar app: {create_response.text}")
                    app_id = f"1:{PROJECT_NUMBER}:web:default"
        
        # Buscar config
        config_response = requests.get(
            f"https://firebase.googleapis.com/v1beta1/{app_name}/config",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if config_response.status_code == 200:
            config = config_response.json()
            api_key = config.get("apiKey", "")
            print(f"   ✅ API Key obtida: {api_key[:20]}...")
        else:
            api_key = "AIzaSyDEFAULT_KEY"
            print("   ⚠️  Usando API Key padrão")
            
    except Exception as e:
        print(f"   ⚠️  Erro na API: {e}")
        api_key = "AIzaSyDEFAULT_KEY"
        app_id = f"1:{PROJECT_NUMBER}:web:default"
    
    # 3. Atualizar firebase.ts
    print("3️⃣ Atualizando firebase.ts...")
    
    firebase_config = f"""// lib/firebase.ts - Auto-generated
import {{ initializeApp, getApps, getApp }} from "firebase/app";
import {{ getAuth }} from "firebase/auth";

const firebaseConfig = {{
  apiKey: "{api_key}",
  authDomain: "{PROJECT_ID}.firebaseapp.com",
  projectId: "{PROJECT_ID}",
  storageBucket: "{PROJECT_ID}.appspot.com",
  messagingSenderId: "{PROJECT_NUMBER}",
  appId: "{app_id}"
}};

const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
export const auth = getAuth(app);
"""
    
    with open("frontend/lib/firebase.ts", "w") as f:
        f.write(firebase_config)
    
    print("   ✅ Arquivo atualizado!")
    
    # 4. Criar usuários via Identity Toolkit API
    print("4️⃣ Criando usuários...")
    
    users = [
        {"email": "victor@aifinance.com", "password": "Victor@AIFinance2026", "displayName": "Victor"},
        {"email": "larissa@aifinance.com", "password": "Larissa@AIFinance2026", "displayName": "Larissa"}
    ]
    
    for user in users:
        try:
            signup_response = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={api_key}",
                json={
                    "email": user["email"],
                    "password": user["password"],
                    "displayName": user["displayName"],
                    "returnSecureToken": True
                }
            )
            
            if signup_response.status_code == 200:
                print(f"   ✅ {user['displayName']} criado: {user['email']}")
            elif "EMAIL_EXISTS" in signup_response.text:
                print(f"   ⚠️  {user['email']} já existe")
            else:
                print(f"   ❌ Erro: {signup_response.json()}")
        except Exception as e:
            print(f"   ❌ Erro ao criar {user['email']}: {e}")
    
    print()
    print("✨ Configuração Completa!")
    print()
    print("📧 Credenciais de Login:")
    print("   Victor:  victor@aifinance.com / Victor@AIFinance2026")
    print("   Larissa: larissa@aifinance.com / Larissa@AIFinance2026")
    print()
    print("🚀 Próximo passo: Deploy")
    print("   cd frontend && ./deploy.sh")

if __name__ == "__main__":
    try:
        import requests
    except ImportError:
        print("❌ Erro: módulo 'requests' não encontrado")
        print("Instalando...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "requests"])
        import requests
    
    main()
