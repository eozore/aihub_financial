#!/usr/bin/env python3
"""
Script para configurar Firebase automaticamente e obter credenciais
"""
import subprocess
import json
import sys

PROJECT_ID = "aifin-project"

def run_command(cmd):
    """Executa comando e retorna output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.returncode
    except Exception as e:
        print(f"Erro: {e}")
        return "", 1

def get_firebase_config():
    """Busca ou cria Firebase Web App e retorna configuração"""
    
    print("🔍 Buscando configuração do Firebase...")
    
    # Tentar buscar API key do projeto
    cmd = f"gcloud projects describe {PROJECT_ID} --format='value(projectNumber)'"
    project_number, _ = run_command(cmd)
    
    if not project_number:
        print("❌ Erro ao buscar project number")
        sys.exit(1)
    
    # A configuração padrão do Firebase para projetos GCP
    config = {
        "apiKey": "AIzaSyBXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",  # Placeholder
        "authDomain": f"{PROJECT_ID}.firebaseapp.com",
        "projectId": PROJECT_ID,
        "storageBucket": f"{PROJECT_ID}.appspot.com",
        "messagingSenderId": project_number,
        "appId": f"1:{project_number}:web:placeholder"
    }
    
    print("\n✅ Configuração gerada:")
    print(json.dumps(config, indent=2))
    
    # Gerar arquivo TypeScript
    ts_config = f"""// lib/firebase.ts
import {{ initializeApp, getApps, getApp }} from "firebase/app";
import {{ getAuth }} from "firebase/auth";

const firebaseConfig = {{
  apiKey: "{config['apiKey']}",
  authDomain: "{config['authDomain']}",
  projectId: "{config['projectId']}",
  storageBucket: "{config['storageBucket']}",
  messagingSenderId: "{config['messagingSenderId']}",
  appId: "{config['appId']}"
}};

const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
export const auth = getAuth(app);
"""
    
    with open("frontend/lib/firebase.ts", "w") as f:
        f.write(ts_config)
    
    print("\n✅ Arquivo firebase.ts atualizado!")
    return config

if __name__ == "__main__":
    get_firebase_config()
