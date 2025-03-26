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
    Obtém as credenciais para a API do Google, tentando várias abordagens:
    1. Arquivo de token salvo
    2. OAuth 2.0 usando ID do cliente e segredo
    3. Conta de serviço do arquivo google_credentials.json
    4. Segredos do Streamlit
    """
    
    # Tentar obter de token OAuth salvo
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
    
    # Tentar obter via OAuth2 usando ID e segredo do cliente
    try:
        # Criar arquivo de configuração do cliente
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
    
    # 3. Verificar se existe um arquivo de credenciais de conta de serviço
    if os.path.exists('google_credentials.json'):
        try:
            # Verificar se a chave privada não é um placeholder
            with open('google_credentials.json', 'r') as f:
                cred_content = json.load(f)
                pk = cred_content.get("private_key", "")
                if "SUBSTITUA" in pk or "YOUR_PRIVATE_KEY" in pk:
                    logging.error("A chave privada em google_credentials.json é um placeholder. Substitua pela chave real.")
                else:    
                    logging.info("Usando credenciais do arquivo local google_credentials.json")
                    return Credentials.from_service_account_file(
                        'google_credentials.json',
                        scopes=SCOPES
                    )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais do arquivo local: {e}")
    
    # 4. Tentar obter a partir dos segredos do Streamlit
    if 'gcp_service_account' in st.secrets:
        try:
            # Verificar se a chave privada não é um placeholder
            pk = st.secrets["gcp_service_account"].get("private_key", "")
            if "YOUR_PRIVATE_KEY_HERE" in pk:
                logging.error("A chave privada em st.secrets é um placeholder. Substitua pela chave real.")
            else:    
                logging.info("Usando credenciais dos segredos do Streamlit")
                return service_account.Credentials.from_service_account_info(
                    st.secrets["gcp_service_account"],
                    scopes=SCOPES
                )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais do Streamlit: {e}")
    
    logging.error("Não foi possível obter credenciais válidas por nenhum método")
    return None

# Função para criar credenciais temporárias (fallback, não recomendado para produção)
def create_temporary_credentials():
    """
    Cria um arquivo temporário com credenciais para desenvolvimento.
    IMPORTANTE: Use apenas para testes, não para produção!
    """
    try:
        # Aviso: Estas credenciais são apenas para testes e não funcionarão para acessar serviços reais
        credentials_info = {
            "type": "service_account",
            "project_id": "medix-system",
            "private_key_id": "temporary-key-for-development-purposes-only",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC2tVjsVoRxRT1E\nfUL7U/JMn0x2lNEwHcV6utpj5//VmA7HUJGsz6J7QW5NJJl0W3YDUfBZ0r7GU9Ou\nHLHqn9AJn/fbCIfxVhiZFdOL3Pp3E+5PAyHcFx5GLvrx8Dh65IFZkxDP7Tb3zdYT\niV5VhcfF6uVPH3VCcTkLvDTwNv6qmPMGLjwDx79epU3CYNLBZQBGa3jcRd6b2PPM\nXQmvRtJ4bmS0dDSvH4eRYiM41BDKgAuMTKiDYggbHLVUL69BauYGXBU78s2FrGyu\neQ6i9aSbZTt+T0S3R4UPG5t3CKoYKY7EvScSMH29QCUvixUQXCJGZfzX8dQ+7o8z\nF3/GleLxAgMBAAECggEAAqAAYHGPxEp1ALZJb6Ri651hDuVlkOYrTvC89YPWG1ru\nYaRiF9BFXwwLA5jZp8xkNJTkRlykCBoVa3fzSMCyXxtUyjYvAuEA0XnFLzG0QbGD\nD2w0f5Og/2GG8JhcjLLK6j6jF1EXDlWrS5vvvvcTsN7SIHnG+3k82GjoO4mQNBSG\nVi7SXBfHvw+CsGX3Z+GcOxgHopL5VPRfxdv9nPnodJ1MmsQhYc5D4MRNKBgK7JQw\nBD/Xq0SxuBKF+8R4x7P9IFahAiD4M1K/FWdv68BPvCbWwCM+FZsXu1ZHrJS9F+WL\nofLJvJEZ2CwvYxR+7L7i4LoYJmKD1H35Pw0k8CFZAQKBgQDdNnCIbWbpEBm/Qi6s\ndBiJS6CL0NXZqXuJRZg7uUYDuEBtSl3zAkGcCd9R9S+4G7xZwm1+oMlGiB9jIRXL\nfONHvdzxF3I0UQYcauQMv4/w7/YbOc78r3TtPqTTq27UW3npECdQZ1ZhgHGEUo3K\nfP+DKO2eI5RXTp5sJm8jGVbQQQKBgQDTJLbXQrQaKZ/uVNXGz6YDhOkhtb7nACsz\nyzFD2Qgw+BmRncC4xJxho5AR5JYwf0YVKB+LTnZN9NjQmZOm7IMvpGeTg7Qb6hQn\n5XgjK9L0XWev7oPmWd6KVuqUcRwVoQJL8+Ydo5FzHlwW80Lwx41h7o/KlJeXKZF4\ndwtMkxKlcQKBgGKHxLpjI+Hm00rXGTo6ttiK6rpQPx40q/Fyu+zVCEIfSSA+oKNq\ngUgzCw1jQ4U+I/U4qXDGd9Teyj6hR5dYiQ7QmE0I9i+7oyaLLGrSWCVlfnGtKNtB\nTqP3T+o5bNYCdLrP92PVX1EMnXvr0dWZ41YlYtbF9Zmf5n0g16ONzx2BAoGBAJXp\nz4K0wXXGcex9/5E+h1M+0yySXQ0LJRoVYdAS5dXvvCfTvdofoJHeI7KxbwYLghO9\nS1v2fCHfQrG5J13n7Lsv+eaLaoElqsNhT3W8HYOPu6V/ch0xBFR2X2wKQOsMVKnP\neakPhiZDlbIvr+uTFezHIQP5o8YvH4XUBbOqZ2rxAoGAOmYRiP0U2DGE0jxW6TLg\n61lBBvBOx6McYBszQHCcJm4hvrQBj+jqTYvzRqB11aZhQ0JUY8P0KJa0vdE2iAYl\nAVfLMgrhikPB/LHqpvz+zXhIU5a+SCTJTATm5+/lUfTEXpQjSKQxW1ZCBBfzvZTz\ntTyrI7jQJJVeBAvhV/fljx0=\n-----END PRIVATE KEY-----\n",
            "client_email": "medix-service@medix-system.iam.gserviceaccount.com",
            "client_id": CLIENT_ID,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%40medix-system.iam.gserviceaccount.com"
        }
        
        # Criar um arquivo temporário para as credenciais
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        with open(temp_file.name, 'w') as f:
            json.dump(credentials_info, f)
        
        # Obter credenciais do arquivo temporário
        creds = Credentials.from_service_account_file(temp_file.name, scopes=SCOPES)
        
        # Excluir o arquivo temporário após uso
        os.unlink(temp_file.name)
        
        return creds
    except Exception as e:
        logging.error(f"Erro ao criar credenciais temporárias: {e}")
        raise e  # Re-lançar a exceção para que o sistema saiba que falhou

def create_service_account_json():
    """
    Cria um arquivo JSON de conta de serviço que pode ser usado para autenticação.
    Útil para desenvolvedores configurarem seu ambiente local ou Streamlit Cloud.
    """
    credentials = {
        "type": "service_account",
        "project_id": "medix-system",
        "private_key_id": "your-private-key-id-here",
        "private_key": "-----BEGIN PRIVATE KEY-----\nYour_Private_Key_Here\n-----END PRIVATE KEY-----\n",
        "client_email": "medix-service@medix-system.iam.gserviceaccount.com",
        "client_id": CLIENT_ID,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%40medix-system.iam.gserviceaccount.com",
        "universe_domain": "googleapis.com"
    }
    
    with open('google_credentials.json', 'w') as f:
        json.dump(credentials, f, indent=2)
    
    print("Arquivo google_credentials.json criado com sucesso!")
    print("IMPORTANTE: Substitua 'Your_Private_Key_Here' pela sua chave privada real antes de usar!")

def setup_streamlit_secrets_toml():
    """
    Gera um exemplo de arquivo .streamlit/secrets.toml para configuração no Streamlit Cloud
    """
    os.makedirs('.streamlit', exist_ok=True)
    
    secrets_content = """
[gcp_service_account]
type = "service_account"
project_id = "medix-system"
private_key_id = "your-private-key-id-here"
private_key = "-----BEGIN PRIVATE KEY-----\\nYOUR_PRIVATE_KEY_HERE\\n-----END PRIVATE KEY-----\\n"
client_email = "medix-service@medix-system.iam.gserviceaccount.com"
client_id = "%s"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%%40medix-system.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
""" % CLIENT_ID
    
    with open('.streamlit/secrets.toml', 'w') as f:
        f.write(secrets_content)
    
    print("Arquivo .streamlit/secrets.toml criado com sucesso!")
    print("IMPORTANTE: Substitua 'YOUR_PRIVATE_KEY_HERE' pela sua chave privada real antes de usar!")
    print("Este arquivo NÃO deve ser commitado no GitHub. Adicione .streamlit/secrets.toml ao seu .gitignore!")

def get_oauth_credentials():
    """
    Utiliza as credenciais OAuth 2.0 do cliente para autenticação
    (alternativa à conta de serviço)
    """
    from google_auth_oauthlib.flow import Flow
    
    # Configuração para OAuth 2.0
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
    
    # Criar arquivo de configuração temporário
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
    with open(temp_file.name, 'w') as f:
        json.dump(client_config, f)
    
    # Iniciar fluxo de autorização
    flow = Flow.from_client_secrets_file(
        temp_file.name,
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob")
    
    # Gerar URL de autorização
    auth_url, _ = flow.authorization_url(prompt='consent')
    
    # Excluir arquivo temporário
    os.unlink(temp_file.name)
    
    # Exibir instruções para o usuário
    print(f"Acesse este URL para autorizar o aplicativo: {auth_url}")
    auth_code = input("Digite o código de autorização: ")
    
    # Trocar o código de autorização por tokens de acesso e atualização
    flow.fetch_token(code=auth_code)
    
    return flow.credentials

if __name__ == "__main__":
    # Menu para facilitar a configuração
    print("\n== MEDIX - Gerenciador de Credenciais ==\n")
    print("1. Gerar arquivo de credenciais de conta de serviço")
    print("2. Gerar exemplo de secrets.toml para Streamlit Cloud")
    print("3. Obter credenciais usando OAuth 2.0")
    print("4. Sair")
    
    choice = input("\nEscolha uma opção (1-4): ")
    
    if choice == "1":
        create_service_account_json()
    elif choice == "2":
        setup_streamlit_secrets_toml()
    elif choice == "3":
        try:
            creds = get_oauth_credentials()
            print(f"Credenciais obtidas com sucesso!")
            print(f"Token de acesso: {creds.token}")
            print(f"Expira em: {creds.expiry}")
        except Exception as e:
            print(f"Erro ao obter credenciais: {e}")
    elif choice == "4":
        print("Saindo...")
    else:
        print("Opção inválida!")
