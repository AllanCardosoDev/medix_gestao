import os
import json
import streamlit as st
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
import tempfile
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Constantes para identificar as credenciais
FOLDER_ID = "1HDN1suMspx1um0xbK34waXZ5VGUmseB6"  # ID da pasta do Google Drive
API_KEY = "AIzaSyBQte4l3T-1wg3ftpAEkbB77qnxbXqQQ1w"  # Chave de API do Google

# Escopos necessários para a API do Google
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]

def get_credentials():
    """
    Obtém as credenciais para a API do Google, verificando diversas fontes:
    1. Segredos do Streamlit (ambiente de produção)
    2. Variáveis de ambiente
    3. Arquivo local de credenciais
    4. Credenciais embutidas (apenas para desenvolvimento)
    """
    
    # 1. Tentar obter a partir dos segredos do Streamlit
    if 'gcp_service_account' in st.secrets:
        try:
            # Verificar se a chave privada não é um placeholder
            pk = st.secrets["gcp_service_account"].get("private_key", "")
            if "YOUR_PRIVATE_KEY_HERE" in pk:
                logging.error("A chave privada em st.secrets é um placeholder. Substitua pela chave real.")
                return None
                
            logging.info("Usando credenciais dos segredos do Streamlit")
            return service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=SCOPES
            )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais do Streamlit: {e}")
    
    # 2. Tentar obter de variáveis de ambiente
    if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        try:
            logging.info("Usando credenciais do arquivo definido em GOOGLE_APPLICATION_CREDENTIALS")
            return Credentials.from_service_account_file(
                os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'),
                scopes=SCOPES
            )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais de variável de ambiente: {e}")
    
    # 3. Verificar se existe um arquivo de credenciais local
    if os.path.exists('google_credentials.json'):
        try:
            # Verificar se a chave privada não é um placeholder
            with open('google_credentials.json', 'r') as f:
                cred_content = json.load(f)
                pk = cred_content.get("private_key", "")
                if "YOUR_PRIVATE_KEY_HERE" in pk:
                    logging.error("A chave privada em google_credentials.json é um placeholder. Substitua pela chave real.")
                    return None
                    
            logging.info("Usando credenciais do arquivo local google_credentials.json")
            return Credentials.from_service_account_file(
                'google_credentials.json',
                scopes=SCOPES
            )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais do arquivo local: {e}")
    
    # 4. Usar credenciais embutidas para desenvolvimento (não recomendado para produção)
    try:
        logging.info("Usando credenciais embutidas com a chave de API fornecida")
        return create_temporary_credentials()
    except Exception as e:
        logging.error(f"Erro ao criar credenciais temporárias: {e}")
        return None

def create_temporary_credentials():
    """
    Cria um arquivo temporário com credenciais para desenvolvimento.
    IMPORTANTE: Use apenas para testes, não para produção!
    """
    try:
        # Gera um UUID único para o private_key_id
        import uuid
        private_key_id = str(uuid.uuid4())
        
        # Credenciais com a chave de API fornecida
        credentials_info = {
            "type": "service_account",
            "project_id": "medix-system",
            "private_key_id": private_key_id,
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC2tVjsVoRxRT1E\nfUL7U/JMn0x2lNEwHcV6utpj5//VmA7HUJGsz6J7QW5NJJl0W3YDUfBZ0r7GU9Ou\nHLHqn9AJn/fbCIfxVhiZFdOL3Pp3E+5PAyHcFx5GLvrx8Dh65IFZkxDP7Tb3zdYT\niV5VhcfF6uVPH3VCcTkLvDTwNv6qmPMGLjwDx79epU3CYNLBZQBGa3jcRd6b2PPM\nXQmvRtJ4bmS0dDSvH4eRYiM41BDKgAuMTKiDYggbHLVUL69BauYGXBU78s2FrGyu\neQ6i9aSbZTt+T0S3R4UPG5t3CKoYKY7EvScSMH29QCUvixUQXCJGZfzX8dQ+7o8z\nF3/GleLxAgMBAAECggEAAqAAYHGPxEp1ALZJb6Ri651hDuVlkOYrTvC89YPWG1ru\nYaRiF9BFXwwLA5jZp8xkNJTkRlykCBoVa3fzSMCyXxtUyjYvAuEA0XnFLzG0QbGD\nD2w0f5Og/2GG8JhcjLLK6j6jF1EXDlWrS5vvvvcTsN7SIHnG+3k82GjoO4mQNBSG\nVi7SXBfHvw+CsGX3Z+GcOxgHopL5VPRfxdv9nPnodJ1MmsQhYc5D4MRNKBgK7JQw\nBD/Xq0SxuBKF+8R4x7P9IFahAiD4M1K/FWdv68BPvCbWwCM+FZsXu1ZHrJS9F+WL\nofLJvJEZ2CwvYxR+7L7i4LoYJmKD1H35Pw0k8CFZAQKBgQDdNnCIbWbpEBm/Qi6s\ndBiJS6CL0NXZqXuJRZg7uUYDuEBtSl3zAkGcCd9R9S+4G7xZwm1+oMlGiB9jIRXL\nfONHvdzxF3I0UQYcauQMv4/w7/YbOc78r3TtPqTTq27UW3npECdQZ1ZhgHGEUo3K\nfP+DKO2eI5RXTp5sJm8jGVbQQQKBgQDTJLbXQrQaKZ/uVNXGz6YDhOkhtb7nACsz\nyzFD2Qgw+BmRncC4xJxho5AR5JYwf0YVKB+LTnZN9NjQmZOm7IMvpGeTg7Qb6hQn\n5XgjK9L0XWev7oPmWd6KVuqUcRwVoQJL8+Ydo5FzHlwW80Lwx41h7o/KlJeXKZF4\ndwtMkxKlcQKBgGKHxLpjI+Hm00rXGTo6ttiK6rpQPx40q/Fyu+zVCEIfSSA+oKNq\ngUgzCw1jQ4U+I/U4qXDGd9Teyj6hR5dYiQ7QmE0I9i+7oyaLLGrSWCVlfnGtKNtB\nTqP3T+o5bNYCdLrP92PVX1EMnXvr0dWZ41YlYtbF9Zmf5n0g16ONzx2BAoGBAJXp\nz4K0wXXGcex9/5E+h1M+0yySXQ0LJRoVYdAS5dXvvCfTvdofoJHeI7KxbwYLghO9\nS1v2fCHfQrG5J13n7Lsv+eaLaoElqsNhT3W8HYOPu6V/ch0xBFR2X2wKQOsMVKnP\neakPhiZDlbIvr+uTFezHIQP5o8YvH4XUBbOqZ2rxAoGAOmYRiP0U2DGE0jxW6TLg\n61lBBvBOx6McYBszQHCcJm4hvrQBj+jqTYvzRqB11aZhQ0JUY8P0KJa0vdE2iAYl\nAVfLMgrhikPB/LHqpvz+zXhIU5a+SCTJTATm5+/lUfTEXpQjSKQxW1ZCBBfzvZTz\ntTyrI7jQJJVeBAvhV/fljx0=\n-----END PRIVATE KEY-----\n",
            "client_email": "medix-service@medix-system.iam.gserviceaccount.com",
            "client_id": "1072458931980-mpf2loc5b26l3j5ke1hf0fhghnrfv6i1.apps.googleusercontent.com",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%40medix-system.iam.gserviceaccount.com",
            "api_key": API_KEY  # Adiciona a chave de API fornecida
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
    Cria um arquivo JSON de conta de serviço com a chave de API fornecida.
    Útil para desenvolvedores configurarem seu ambiente local ou Streamlit Cloud.
    """
    # Gera um UUID único para o private_key_id
    import uuid
    private_key_id = str(uuid.uuid4())
    
    credentials = {
        "type": "service_account",
        "project_id": "medix-system",
        "private_key_id": private_key_id,
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC2tVjsVoRxRT1E\nfUL7U/JMn0x2lNEwHcV6utpj5//VmA7HUJGsz6J7QW5NJJl0W3YDUfBZ0r7GU9Ou\nHLHqn9AJn/fbCIfxVhiZFdOL3Pp3E+5PAyHcFx5GLvrx8Dh65IFZkxDP7Tb3zdYT\niV5VhcfF6uVPH3VCcTkLvDTwNv6qmPMGLjwDx79epU3CYNLBZQBGa3jcRd6b2PPM\nXQmvRtJ4bmS0dDSvH4eRYiM41BDKgAuMTKiDYggbHLVUL69BauYGXBU78s2FrGyu\neQ6i9aSbZTt+T0S3R4UPG5t3CKoYKY7EvScSMH29QCUvixUQXCJGZfzX8dQ+7o8z\nF3/GleLxAgMBAAECggEAAqAAYHGPxEp1ALZJb6Ri651hDuVlkOYrTvC89YPWG1ru\nYaRiF9BFXwwLA5jZp8xkNJTkRlykCBoVa3fzSMCyXxtUyjYvAuEA0XnFLzG0QbGD\nD2w0f5Og/2GG8JhcjLLK6j6jF1EXDlWrS5vvvvcTsN7SIHnG+3k82GjoO4mQNBSG\nVi7SXBfHvw+CsGX3Z+GcOxgHopL5VPRfxdv9nPnodJ1MmsQhYc5D4MRNKBgK7JQw\nBD/Xq0SxuBKF+8R4x7P9IFahAiD4M1K/FWdv68BPvCbWwCM+FZsXu1ZHrJS9F+WL\nofLJvJEZ2CwvYxR+7L7i4LoYJmKD1H35Pw0k8CFZAQKBgQDdNnCIbWbpEBm/Qi6s\ndBiJS6CL0NXZqXuJRZg7uUYDuEBtSl3zAkGcCd9R9S+4G7xZwm1+oMlGiB9jIRXL\nfONHvdzxF3I0UQYcauQMv4/w7/YbOc78r3TtPqTTq27UW3npECdQZ1ZhgHGEUo3K\nfP+DKO2eI5RXTp5sJm8jGVbQQQKBgQDTJLbXQrQaKZ/uVNXGz6YDhOkhtb7nACsz\nyzFD2Qgw+BmRncC4xJxho5AR5JYwf0YVKB+LTnZN9NjQmZOm7IMvpGeTg7Qb6hQn\n5XgjK9L0XWev7oPmWd6KVuqUcRwVoQJL8+Ydo5FzHlwW80Lwx41h7o/KlJeXKZF4\ndwtMkxKlcQKBgGKHxLpjI+Hm00rXGTo6ttiK6rpQPx40q/Fyu+zVCEIfSSA+oKNq\ngUgzCw1jQ4U+I/U4qXDGd9Teyj6hR5dYiQ7QmE0I9i+7oyaLLGrSWCVlfnGtKNtB\nTqP3T+o5bNYCdLrP92PVX1EMnXvr0dWZ41YlYtbF9Zmf5n0g16ONzx2BAoGBAJXp\nz4K0wXXGcex9/5E+h1M+0yySXQ0LJRoVYdAS5dXvvCfTvdofoJHeI7KxbwYLghO9\nS1v2fCHfQrG5J13n7Lsv+eaLaoElqsNhT3W8HYOPu6V/ch0xBFR2X2wKQOsMVKnP\neakPhiZDlbIvr+uTFezHIQP5o8YvH4XUBbOqZ2rxAoGAOmYRiP0U2DGE0jxW6TLg\n61lBBvBOx6McYBszQHCcJm4hvrQBj+jqTYvzRqB11aZhQ0JUY8P0KJa0vdE2iAYl\nAVfLMgrhikPB/LHqpvz+zXhIU5a+SCTJTATm5+/lUfTEXpQjSKQxW1ZCBBfzvZTz\ntTyrI7jQJJVeBAvhV/fljx0=\n-----END PRIVATE KEY-----\n",
        "client_email": "medix-service@medix-system.iam.gserviceaccount.com",
        "client_id": "1072458931980-mpf2loc5b26l3j5ke1hf0fhghnrfv6i1.apps.googleusercontent.com",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%40medix-system.iam.gserviceaccount.com",
        "api_key": API_KEY  # Adiciona a chave de API fornecida
    }
    
    with open('google_credentials.json', 'w') as f:
        json.dump(credentials, f, indent=2)
    
    print("Arquivo google_credentials.json criado com sucesso!")

def setup_streamlit_secrets_toml():
    """
    Gera um exemplo de arquivo .streamlit/secrets.toml para configuração no Streamlit Cloud
    """
    os.makedirs('.streamlit', exist_ok=True)
    
    # Gera um UUID único para o private_key_id
    import uuid
    private_key_id = str(uuid.uuid4())
    
    secrets_content = """
[gcp_service_account]
type = "service_account"
project_id = "medix-system"
private_key_id = "%s"
private_key = "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC2tVjsVoRxRT1E\\nfUL7U/JMn0x2lNEwHcV6utpj5//VmA7HUJGsz6J7QW5NJJl0W3YDUfBZ0r7GU9Ou\\nHLHqn9AJn/fbCIfxVhiZFdOL3Pp3E+5PAyHcFx5GLvrx8Dh65IFZkxDP7Tb3zdYT\\niV5VhcfF6uVPH3VCcTkLvDTwNv6qmPMGLjwDx79epU3CYNLBZQBGa3jcRd6b2PPM\\nXQmvRtJ4bmS0dDSvH4eRYiM41BDKgAuMTKiDYggbHLVUL69BauYGXBU78s2FrGyu\\neQ6i9aSbZTt+T0S3R4UPG5t3CKoYKY7EvScSMH29QCUvixUQXCJGZfzX8dQ+7o8z\\nF3/GleLxAgMBAAECggEAAqAAYHGPxEp1ALZJb6Ri651hDuVlkOYrTvC89YPWG1ru\\nYaRiF9BFXwwLA5jZp8xkNJTkRlykCBoVa3fzSMCyXxtUyjYvAuEA0XnFLzG0QbGD\\nD2w0f5Og/2GG8JhcjLLK6j6jF1EXDlWrS5vvvvcTsN7SIHnG+3k82GjoO4mQNBSG\\nVi7SXBfHvw+CsGX3Z+GcOxgHopL5VPRfxdv9nPnodJ1MmsQhYc5D4MRNKBgK7JQw\\nBD/Xq0SxuBKF+8R4x7P9IFahAiD4M1K/FWdv68BPvCbWwCM+FZsXu1ZHrJS9F+WL\\nofLJvJEZ2CwvYxR+7L7i4LoYJmKD1H35Pw0k8CFZAQKBgQDdNnCIbWbpEBm/Qi6s\\ndBiJS6CL0NXZqXuJRZg7uUYDuEBtSl3zAkGcCd9R9S+4G7xZwm1+oMlGiB9jIRXL\\nfONHvdzxF3I0UQYcauQMv4/w7/YbOc78r3TtPqTTq27UW3npECdQZ1ZhgHGEUo3K\\nfP+DKO2eI5RXTp5sJm8jGVbQQQKBgQDTJLbXQrQaKZ/uVNXGz6YDhOkhtb7nACsz\\nyzFD2Qgw+BmRncC4xJxho5AR5JYwf0YVKB+LTnZN9NjQmZOm7IMvpGeTg7Qb6hQn\\n5XgjK9L0XWev7oPmWd6KVuqUcRwVoQJL8+Ydo5FzHlwW80Lwx41h7o/KlJeXKZF4\\ndwtMkxKlcQKBgGKHxLpjI+Hm00rXGTo6ttiK6rpQPx40q/Fyu+zVCEIfSSA+oKNq\\ngUgzCw1jQ4U+I/U4qXDGd9Teyj6hR5dYiQ7QmE0I9i+7oyaLLGrSWCVlfnGtKNtB\\nTqP3T+o5bNYCdLrP92PVX1EMnXvr0dWZ41YlYtbF9Zmf5n0g16ONzx2BAoGBAJXp\\nz4K0wXXGcex9/5E+h1M+0yySXQ0LJRoVYdAS5dXvvCfTvdofoJHeI7KxbwYLghO9\\nS1v2fCHfQrG5J13n7Lsv+eaLaoElqsNhT3W8HYOPu6V/ch0xBFR2X2wKQOsMVKnP\\neakPhiZDlbIvr+uTFezHIQP5o8YvH4XUBbOqZ2rxAoGAOmYRiP0U2DGE0jxW6TLg\\n61lBBvBOx6McYBszQHCcJm4hvrQBj+jqTYvzRqB11aZhQ0JUY8P0KJa0vdE2iAYl\\nAVfLMgrhikPB/LHqpvz+zXhIU5a+SCTJTATm5+/lUfTEXpQjSKQxW1ZCBBfzvZTz\\ntTyrI7jQJJVeBAvhV/fljx0=\\n-----END PRIVATE KEY-----\\n"
client_email = "medix-service@medix-system.iam.gserviceaccount.com"
client_id = "1072458931980-mpf2loc5b26l3j5ke1hf0fhghnrfv6i1.apps.googleusercontent.com"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%%40medix-system.iam.gserviceaccount.com"
api_key = "%s"
""" % (private_key_id, API_KEY)
    
    with open('.streamlit/secrets.toml', 'w') as f:
        f.write(secrets_content)
    
    print("Arquivo .streamlit/secrets.toml criado com sucesso!")
    print("Este arquivo NÃO deve ser commitado no GitHub. Adicione .streamlit/secrets.toml ao seu .gitignore!")

if __name__ == "__main__":
    # Menu para facilitar a configuração
    print("\n== MEDIX - Gerenciador de Credenciais ==\n")
    print("1. Gerar arquivo de credenciais de conta de serviço")
    print("2. Gerar exemplo de secrets.toml para Streamlit Cloud")
    print("3. Testar conexão com a API do Google")
    print("4. Sair")
    
    choice = input("\nEscolha uma opção (1-4): ")
    
    if choice == "1":
        create_service_account_json()
    elif choice == "2":
        setup_streamlit_secrets_toml()
    elif choice == "3":
        try:
            creds = get_credentials()
            if creds:
                print("✅ Credenciais obtidas com sucesso!")
                print("Testando acesso ao Google Drive...")
                
                from googleapiclient.discovery import build
                drive_service = build('drive', 'v3', credentials=creds)
                
                # Testar listagem de arquivos
                results = drive_service.files().list(
                    pageSize=10, fields="nextPageToken, files(id, name)"
                ).execute()
                
                files = results.get('files', [])
                if not files:
                    print("Nenhum arquivo encontrado.")
                else:
                    print("Arquivos:")
                    for file in files:
                        print(f"{file['name']} ({file['id']})")
                
                print("✅ Conexão com Google Drive estabelecida com sucesso!")
            else:
                print("❌ Falha ao obter credenciais.")
        except Exception as e:
            print(f"❌ Erro ao testar conexão: {e}")
    elif choice == "4":
        print("Saindo...")
    else:
        print("Opção inválida!")
