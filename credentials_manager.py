import os
import json
import streamlit as st
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
import tempfile
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

# Configuração de logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Constantes para identificar as credenciais
FOLDER_ID = "1HDN1suMspx1um0xbK34waXZ5VGUmseB6"  # ID da pasta do Google Drive
CLIENT_ID = "1072458931980-mpf2loc5b26l3j5ke1hf0fhghnrfv6i1.apps.googleusercontent.com"
CLIENT_SECRET = "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"

# Escopos necessários para a API do Google
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]

def get_credentials():
    """
    Obtém as credenciais para a API do Google.
    Tenta primeiro usar o arquivo google_credentials.json (com suas credenciais),
    depois tenta outros métodos se necessário.
    """
    # 1. Tentar usar o arquivo google_credentials.json
    if os.path.exists('google_credentials.json'):
        try:
            logging.info("Usando credenciais do arquivo local google_credentials.json")
            return Credentials.from_service_account_file(
                'google_credentials.json',
                scopes=SCOPES
            )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais do arquivo local: {e}")
    
    # 2. Tentar usar token OAuth salvo
    if os.path.exists('token.pickle'):
        try:
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                if creds and creds.valid:
                    logging.info("Usando credenciais OAuth2 do arquivo token.pickle")
                    return creds
                elif creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Salvar as credenciais atualizadas
                    with open('token.pickle', 'wb') as token:
                        pickle.dump(creds, token)
                    logging.info("Credenciais OAuth2 atualizadas e salvas")
                    return creds
        except Exception as e:
            logging.warning(f"Erro ao carregar token OAuth: {e}")
    
    # 3. Tentar obter a partir dos segredos do Streamlit
    if 'gcp_service_account' in st.secrets:
        try:
            logging.info("Usando credenciais dos segredos do Streamlit")
            return service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=SCOPES
            )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais do Streamlit: {e}")
    
    # 4. Tentar criar credenciais OAuth2 interativamente
    try:
        # Criar arquivo de configuração do cliente com suas credenciais
        client_config = {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
            }
        }
        
        # Salvar temporariamente para uso com InstalledAppFlow
        with open('client_config.json', 'w') as f:
            json.dump(client_config, f)
            
        logging.info("Iniciando fluxo de autenticação OAuth2...")
        # Criar e iniciar o fluxo de autenticação
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_config.json', SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Remover arquivo temporário
        os.remove('client_config.json')
        
        # Salvar as credenciais para uso futuro
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
        
        logging.info("Novas credenciais OAuth2 obtidas e salvas")
        return creds
    except Exception as e:
        logging.error(f"Erro ao obter credenciais via OAuth2: {e}")
    
    logging.error("Não foi possível obter credenciais por nenhum método")
    return None

if __name__ == "__main__":
    # Menu simples para testar
    print("\n== MEDIX - Gerenciador de Credenciais ==\n")
    print("Testando credenciais...")
    
    creds = get_credentials()
    if creds:
        print("✅ Credenciais obtidas com sucesso!")
        if hasattr(creds, 'token'):
            print(f"Token de acesso: {creds.token[:20]}... (expira em: {creds.expiry})")
        else:
            print("Usando credenciais de conta de serviço")
    else:
        print("❌ Não foi possível obter credenciais válidas.")
