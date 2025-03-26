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
    """
    
    # 1. Tentar obter a partir dos segredos do Streamlit
    if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
        try:
            logging.info("Tentando usar credenciais dos segredos do Streamlit")
            # Cria um arquivo temporário com as credenciais do st.secrets para usar com from_service_account_info
            service_account_info = st.secrets["gcp_service_account"]
            
            # Verificar se a private_key está formatada corretamente
            if isinstance(service_account_info, dict) and "private_key" in service_account_info:
                # Certificar-se de que a chave privada tem o formato correto com quebras de linha
                if "\\n" in service_account_info["private_key"] and not service_account_info["private_key"].startswith("-----BEGIN PRIVATE KEY-----\n"):
                    service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
            
            return service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais do Streamlit: {e}")
            logging.info("Tentando outras fontes de credenciais...")
    
    # 2. Tentar obter de variáveis de ambiente
    if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        try:
            logging.info("Tentando usar credenciais do arquivo definido em GOOGLE_APPLICATION_CREDENTIALS")
            return Credentials.from_service_account_file(
                os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'),
                scopes=SCOPES
            )
        except Exception as e:
            logging.error(f"Erro ao usar credenciais de variável de ambiente: {e}")
            logging.info("Tentando outras fontes de credenciais...")
    
    # 3. Verificar se existe um arquivo de credenciais local
    for filename in ['google_credentials.json', 'credentials.json', 'service_account.json']:
        if os.path.exists(filename):
            try:
                logging.info(f"Tentando usar credenciais do arquivo local {filename}")
                return Credentials.from_service_account_file(
                    filename,
                    scopes=SCOPES
                )
            except Exception as e:
                logging.error(f"Erro ao usar credenciais do arquivo {filename}: {e}")
    
    # 4. Criar um arquivo temporário com credenciais embutidas como último recurso
    if hasattr(st, 'secrets') and 'fallback_credentials' in st.secrets:
        try:
            logging.info("Tentando usar credenciais de fallback dos secrets")
            fallback_info = st.secrets["fallback_credentials"]
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
            with open(temp_file.name, 'w') as f:
                json.dump(fallback_info, f)
            
            creds = Credentials.from_service_account_file(temp_file.name, scopes=SCOPES)
            os.unlink(temp_file.name)  # Remover o arquivo temporário
            return creds
        except Exception as e:
            logging.error(f"Erro ao usar credenciais de fallback: {e}")
    
    logging.error("Nenhuma fonte de credenciais válida encontrada")
    return None

def create_service_account_json(output_file='new_google_credentials.json'):
    """
    Cria um template para o arquivo JSON de credenciais.
    Este arquivo deve ser preenchido com credenciais reais.
    """
    credentials_template = {
        "type": "service_account",
        "project_id": "SEU_PROJECT_ID",
        "private_key_id": "SEU_PRIVATE_KEY_ID",
        "private_key": "-----BEGIN PRIVATE KEY-----\nSUA_CHAVE_PRIVADA_AQUI\n-----END PRIVATE KEY-----\n",
        "client_email": "SEU_CLIENT_EMAIL",
        "client_id": "SEU_CLIENT_ID",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/SEU_CLIENT_EMAIL"
    }
    
    with open(output_file, 'w') as f:
        json.dump(credentials_template, f, indent=2)
    
    print(f"Arquivo template {output_file} criado com sucesso!")
    print("IMPORTANTE: Substitua os valores do template por suas credenciais reais.")

def diagnosticar_problemas():
    """
    Função para diagnosticar problemas comuns de autenticação
    """
    problemas = []
    
    # Verificar existência de arquivos de credenciais
    arquivos_credenciais = ['google_credentials.json', 'credentials.json', 'service_account.json']
    arquivo_encontrado = False
    
    for arquivo in arquivos_credenciais:
        if os.path.exists(arquivo):
            arquivo_encontrado = True
            print(f"✅ Arquivo de credenciais encontrado: {arquivo}")
            
            # Verificar conteúdo do arquivo
            try:
                with open(arquivo, 'r') as f:
                    data = json.load(f)
                    
                campos_obrigatorios = ["type", "project_id", "private_key_id", "private_key", 
                                      "client_email", "client_id", "auth_uri", "token_uri"]
                                      
                for campo in campos_obrigatorios:
                    if campo not in data:
                        problemas.append(f"Campo obrigatório '{campo}' faltando no arquivo {arquivo}")
                    elif campo == "private_key" and "PRIVATE_KEY" not in data[campo]:
                        problemas.append(f"O campo 'private_key' no arquivo {arquivo} parece estar incompleto ou inválido")
                    elif campo == "client_email" and "@" not in data[campo]:
                        problemas.append(f"O campo 'client_email' no arquivo {arquivo} parece estar inválido")
            except json.JSONDecodeError:
                problemas.append(f"O arquivo {arquivo} não é um JSON válido")
            except Exception as e:
                problemas.append(f"Erro ao analisar o arquivo {arquivo}: {str(e)}")
    
    if not arquivo_encontrado:
        problemas.append("Nenhum arquivo de credenciais encontrado")
    
    # Verificar variável de ambiente
    if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        problemas.append("Variável de ambiente GOOGLE_APPLICATION_CREDENTIALS não definida")
    
    # Verificar secrets do Streamlit
    if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
        print("✅ Credenciais encontradas em st.secrets['gcp_service_account']")
        
        # Verificar campos obrigatórios
        service_account_info = st.secrets["gcp_service_account"]
        campos_obrigatorios = ["type", "project_id", "private_key", "client_email"]
        
        for campo in campos_obrigatorios:
            if campo not in service_account_info:
                problemas.append(f"Campo obrigatório '{campo}' faltando em st.secrets['gcp_service_account']")
    else:
        problemas.append("Credenciais não encontradas em st.secrets['gcp_service_account']")
    
    return problemas

if __name__ == "__main__":
    # Menu para facilitar a configuração
    print("\n== MEDIX - Gerenciador de Credenciais ==\n")
    print("1. Diagnosticar problemas de autenticação")
    print("2. Gerar template de arquivo de credenciais")
    print("3. Testar conexão com a API do Google")
    print("4. Sair")
    
    choice = input("\nEscolha uma opção (1-4): ")
    
    if choice == "1":
        problemas = diagnosticar_problemas()
        if problemas:
            print("\n❌ Problemas encontrados:")
            for problema in problemas:
                print(f"  - {problema}")
            print("\nSugestões de correção:")
            print("  - Certifique-se de que suas credenciais são válidas e estão corretamente formatadas")
            print("  - Verifique se a conta de serviço tem as permissões necessárias no Google Drive")
            print("  - Certifique-se de que os escopos solicitados são compatíveis com as permissões da conta")
        else:
            print("\n✅ Nenhum problema óbvio encontrado com as credenciais")
    
    elif choice == "2":
        create_service_account_json()
    
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
                    pageSize=5, fields="nextPageToken, files(id, name)"
                ).execute()
                
                files = results.get('files', [])
                if not files:
                    print("Nenhum arquivo encontrado, mas a conexão foi estabelecida.")
                else:
                    print("Arquivos encontrados (primeiros 5):")
                    for file in files:
                        print(f"  - {file['name']} ({file['id']})")
                
                print("✅ Conexão com Google Drive estabelecida com sucesso!")
            else:
                print("❌ Falha ao obter credenciais.")
        except Exception as e:
            print(f"❌ Erro ao testar conexão: {e}")
    
    elif choice == "4":
        print("Saindo...")
    else:
        print("Opção inválida!")
