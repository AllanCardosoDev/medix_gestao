import streamlit as st
import pandas as pd
from datetime import datetime
import re
import io
import os
import logging
import time
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import json
import uuid
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu

# Configuração de logging
logging.basicConfig(filename='app.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Configurações do Google API
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]

# ID da pasta no Google Drive onde os dados serão armazenados
FOLDER_ID = "1HDN1suMspx1um0xbK34waXZ5VGUmseB6"

# Funções auxiliares
def validar_cpf(cpf):
    if not cpf:
        return True  # CPF vazio é considerado válido, pois não é obrigatório
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digito = 11 - (soma % 11)
    if digito > 9:
        digito = 0
    if int(cpf[9]) != digito:
        return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digito = 11 - (soma % 11)
    if digito > 9:
        digito = 0
    return int(cpf[10]) == digito

def formatar_cpf(cpf):
    if not cpf:
        return ""
    cpf = re.sub(r'\D', '', cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

def criar_arquivo_credenciais():
    """Cria um arquivo de credenciais temporário para a autenticação Google."""
    credentials_info = {
        "type": "service_account",
        "project_id": "medix-system",
        "private_key_id": str(uuid.uuid4()),
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEA0T/5Q/+lhrZ3p0SV\n1QHE+vXdw8PIWXDA1SNfBQVrAU5QzMX/6aBD4PsI+S5wVpGwQg5y7YLNkzAgjOBB\nkTiR4wIDAQABAkA9u9ks+rLWRlg9nCQ9cj5x1dLkf1R1sJj+wI0JNLKL1Hb1NZLC\n2pX2QWpIU5i9MfZ5+BB1CPXKu5SnPzOjBYphAiEA97HJt1YfBUzFWEcpweDLu7fJ\nVNzcpUm1FNM8mCt8LnkCIQDYfPGRW7QVuN1KsGySVJnMGD8k1Wir2pcUJ34JRoqZ\nixkZ2wIgTQtTQUKCPXwcIcZR3RZG/l4j+QRBGXx0lM5LbQl+c6kCIQDSFNtGBkxX\n4+GvLpwWX5/jCCeR/+GCw9nMlvzILXeTZwIhAJJfGwKUhECMACPyGfSBDHF5e1CX\nGOQVY2Qxijy9jTxL\n-----END PRIVATE KEY-----\n",
        "client_email": "medix-service@medix-system.iam.gserviceaccount.com",
        "client_id": "1072458931980-mpf2loc5b26l3j5ke1hf0fhghnrfv6i1.apps.googleusercontent.com",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%40medix-system.iam.gserviceaccount.com"
    }
    
    with open('credentials.json', 'w') as f:
        json.dump(credentials_info, f)
    
    return 'credentials.json'

def autenticar_google():
    """Autentica com a API do Google usando OAuth2."""
    try:
        # Se você já tiver o arquivo JSON de credenciais (preferível):
        if os.path.exists('google_credentials.json'):
            creds = Credentials.from_service_account_file('google_credentials.json', scopes=SCOPES)
        else:
            # Usamos credenciais alternativas com método de autenticação OAuth2
            # Nota: Em produção, é melhor usar um arquivo de credenciais real
            st.warning("Usando autenticação alternativa. Para melhor segurança, use um arquivo de credenciais.")
            credentials_file = criar_arquivo_credenciais()
            creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        
        return creds
    except Exception as e:
        logging.error(f"Erro na autenticação: {e}")
        st.error(f"Erro na autenticação com Google API: {e}")
        return None

class GestaoVendasGoogleSheets:
    def __init__(self):
        self.creds = autenticar_google()
        if not self.creds:
            st.error("Falha na autenticação com Google API.")
            return
        
        self.drive_service = build('drive', 'v3', credentials=self.creds)
        self.sheets_service = build('sheets', 'v4', credentials=self.creds)
        self.gc = gspread.authorize(self.creds)
        
        # Inicializa as planilhas se não existirem
        self.sheets = self.inicializar_planilhas()
        if not self.sheets:
            st.error("Falha ao inicializar planilhas.")
            return
        
        self.produtos_sheet = self.sheets.worksheet("Produtos")
        self.vendas_sheet = self.sheets.worksheet("Vendas")
        
        # Verifica e corrige headers das planilhas se necessário
        self.verificar_headers()
    
    def inicializar_planilhas(self):
        """Inicializa as planilhas no Google Sheets, criando-as se não existirem."""
        try:
            # Verifica se já existe uma planilha MEDIX na pasta especificada
            results = self.drive_service.files().list(
                q=f"name='MEDIX_Sistema' and '{FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.spreadsheet'",
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                # Usa a planilha existente
                spreadsheet_id = files[0]['id']
                spreadsheet = self.gc.open_by_key(spreadsheet_id)
            else:
                # Cria uma nova planilha
                spreadsheet = self.gc.create('MEDIX_Sistema')
                
                # Move a planilha para a pasta especificada
                file_id = spreadsheet.id
                file = self.drive_service.files().get(fileId=file_id, fields='parents').execute()
                previous_parents = ",".join(file.get('parents', []))
                
                self.drive_service.files().update(
                    fileId=file_id,
                    addParents=FOLDER_ID,
                    removeParents=previous_parents,
                    fields='id, parents'
                ).execute()
                
                # Inicializa as worksheets
                try:
                    spreadsheet.add_worksheet(title="Produtos", rows=1000, cols=20)
                    spreadsheet.add_worksheet(title="Vendas", rows=1000, cols=20)
                    
                    # Remove a planilha padrão (Sheet1)
                    default_sheet = spreadsheet.worksheet("Sheet1")
                    spreadsheet.del_worksheet(default_sheet)
                except Exception as e:
                    logging.warning(f"Erro ao configurar worksheets: {e}")
                    # As worksheets provavelmente já existem
            
            return spreadsheet
            
        except Exception as e:
            logging.error(f"Erro ao inicializar planilhas: {e}")
            st.error(f"Erro ao inicializar planilhas: {e}")
            return None
    
    def verificar_headers(self):
        """Verifica e configura os cabeçalhos das planilhas."""
        try:
            # Verifica os headers da planilha de produtos
            try:
                produtos_headers = self.produtos_sheet.row_values(1)
                if not produtos_headers:
                    self.produtos_sheet.insert_row([
                        "id", "nome", "tipo", "valor", "quantidade", 
                        "link_download", "descricao", "data_cadastro"
                    ], 1)
            except Exception:
                self.produtos_sheet.insert_row([
                    "id", "nome", "tipo", "valor", "quantidade", 
                    "link_download", "descricao", "data_cadastro"
                ], 1)
            
            # Verifica os headers da planilha de vendas
            try:
                vendas_headers = self.vendas_sheet.row_values(1)
                if not vendas_headers:
                    self.vendas_sheet.insert_row([
                        "id", "produto_id", "produto_nome", "cliente", "cpf_cliente",
                        "email_cliente", "quantidade", "valor_total", "forma_pagamento",
                        "data_registro", "data_compra", "status"
                    ], 1)
            except Exception:
                self.vendas_sheet.insert_row([
                    "id", "produto_id", "produto_nome", "cliente", "cpf_cliente",
                    "email_cliente", "quantidade", "valor_total", "forma_pagamento",
                    "data_registro", "data_compra", "status"
                ], 1)
                
        except Exception as e:
            logging.error(f"Erro ao verificar headers: {e}")
            st.error(f"Erro ao verificar headers das planilhas: {e}")
    
    def validar_produto(self, nome, id=None):
        """Verifica se já existe um produto com o mesmo nome."""
        try:
            produtos = self.listar_produtos()
            if id:
                # Verifica se existe outro produto com o mesmo nome, exceto o produto sendo editado
                return not produtos[(produtos['nome'] == nome) & (produtos['id'] != id)].shape[0]
            else:
                # Verifica se já existe um produto com este nome
                return not produtos[produtos['nome'] == nome].shape[0]
        except Exception as e:
            logging.error(f"Erro ao validar produto: {e}")
            return False
    
    def gerar_id(self, tipo):
        """Gera um novo ID único para produtos ou vendas."""
        try:
            if tipo == "produto":
                produtos = self.listar_produtos()
                if produtos.empty:
                    return 1
                return int(produtos['id'].max()) + 1
            else:  # tipo == "venda"
                vendas = self.listar_vendas()
                if vendas.empty:
                    return 1
                return int(vendas['id'].max()) + 1
        except Exception as e:
            logging.error(f"Erro ao gerar ID: {e}")
            return str(uuid.uuid4())[:8]  # Fallback para UUID em caso de erro
    
    def cadastrar_produto(self, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        """Cadastra um novo produto na planilha de produtos."""
        try:
            if not self.validar_produto(nome):
                raise ValueError("Já existe um produto com este nome")
            
            # Gera um novo ID
            id = self.gerar_id("produto")
            
            # Formata os dados para inserção
            data_cadastro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            produto = [
                id, nome, tipo, valor, quantidade or "", 
                link_download or "", descricao or "", data_cadastro
            ]
            
            # Insere o produto na planilha
            self.produtos_sheet.append_row(produto)
            return True
        except Exception as e:
            logging.error(f"Erro ao cadastrar produto: {e}")
            st.error(f"Erro ao cadastrar produto: {e}")
            return False
    
    def editar_produto(self, id, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        """Edita um produto existente na planilha."""
        try:
            if not self.validar_produto(nome, id):
                raise ValueError("Já existe outro produto com este nome")
            
            # Encontra o produto pelo ID
            produtos = self.listar_produtos()
            produto = produtos[produtos['id'] == id]
            
            if produto.empty:
                raise ValueError(f"Produto com ID {id} não encontrado")
            
            # Encontra a linha do produto na planilha
            cells = self.produtos_sheet.findall(str(id))
            for cell in cells:
                if cell.col == 1:  # A coluna ID é a primeira
                    row = cell.row
                    break
            else:
                raise ValueError(f"Produto com ID {id} não encontrado na planilha")
            
            # Atualiza os dados do produto
            self.produtos_sheet.update(f'A{row}:H{row}', [[
                id, nome, tipo, valor, quantidade or "", 
                link_download or "", descricao or "", produto['data_cadastro'].values[0]
            ]])
            
            return True
        except Exception as e:
            logging.error(f"Erro ao editar produto: {e}")
            st.error(f"Erro ao editar produto: {e}")
            return False
    
    def remover_produto(self, id):
        """Remove um produto da planilha."""
        try:
            # Verifica se há vendas associadas a este produto
            vendas = self.listar_vendas()
            if not vendas.empty and (vendas['produto_id'] == id).any():
                raise ValueError("Não é possível remover um produto que possui vendas associadas")
            
            # Encontra a linha do produto na planilha
            cell = self.produtos_sheet.find(str(id), in_column=1)
            if cell:
                self.produtos_sheet.delete_row(cell.row)
                return True
            else:
                raise ValueError(f"Produto com ID {id} não encontrado")
        except Exception as e:
            logging.error(f"Erro ao remover produto: {e}")
            st.error(f"Erro ao remover produto: {str(e)}")
            return False
    
    def registrar_venda(self, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra=None):
        """Registra uma nova venda na planilha de vendas."""
        try:
            if cpf and not validar_cpf(cpf):
                raise ValueError("CPF inválido")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else ""
            
            # Obtém informações do produto
            produtos = self.listar_produtos()
            produto = produtos[produtos['id'] == produto_id]
            
            if produto.empty:
                raise ValueError("Produto não encontrado")
            
            nome_produto = produto['nome'].values[0]
            valor_unitario = float(produto['valor'].values[0])
            tipo_produto = produto['tipo'].values[0]
            
            # Verifica estoque para produtos físicos
            if tipo_produto in ['Card', 'Material Físico']:
                estoque_atual = produto['quantidade'].values[0]
                if pd.isna(estoque_atual) or estoque_atual == "":
                    raise ValueError("Estoque não definido para este produto")
                
                estoque_atual = int(estoque_atual)
                if quantidade > estoque_atual:
                    raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual}")
                
                # Atualiza o estoque do produto
                self.atualizar_estoque(produto_id, estoque_atual - quantidade)
            
            # Gera um novo ID para a venda
            id = self.gerar_id("venda")
            
            # Formata os dados para inserção
            data_registro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not data_compra:
                data_compra = datetime.now().strftime("%Y-%m-%d")
            else:
                data_compra = data_compra.strftime("%Y-%m-%d")
            
            valor_total = valor_unitario * quantidade
            
            venda = [
                id, produto_id, nome_produto, cliente, cpf_formatado,
                email, quantidade, valor_total, forma_pagamento,
                data_registro, data_compra, "Processando"
            ]
            
            # Insere a venda na planilha
            self.vendas_sheet.append_row(venda)
            return True
        except Exception as e:
            logging.error(f"Erro ao registrar venda: {e}")
            st.error(f"Erro ao registrar venda: {str(e)}")
            return False
    
    def atualizar_estoque(self, produto_id, nova_quantidade):
        """Atualiza o estoque de um produto."""
        try:
            # Encontra a linha do produto na planilha
            cell = self.produtos_sheet.find(str(produto_id), in_column=1)
            if cell:
                # Atualiza apenas a coluna de quantidade (coluna E ou índice 5)
                self.produtos_sheet.update_cell(cell.row, 5, nova_quantidade)
                return True
            else:
                raise ValueError(f"Produto com ID {produto_id} não encontrado")
        except Exception as e:
            logging.error(f"Erro ao atualizar estoque: {e}")
            return False
    
    def editar_venda(self, id, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra):
        """Edita uma venda existente na planilha."""
        try:
            if cpf and not validar_cpf(cpf):
                raise ValueError("CPF inválido")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else ""
            
            # Obter informações da venda atual
            vendas = self.listar_vendas()
            venda_atual = vendas[vendas['id'] == id]
            
            if venda_atual.empty:
                raise ValueError(f"Venda com ID {id} não encontrada")
            
            quantidade_atual = int(venda_atual['quantidade'].values[0])
            produto_id_atual = venda_atual['produto_id'].values[0]
            
            # Obter informações do produto
            produtos = self.listar_produtos()
            produto = produtos[produtos['id'] == produto_id]
            
            if produto.empty:
                raise ValueError("Produto não encontrado")
            
            nome_produto = produto['nome'].values[0]
            valor_unitario = float(produto['valor'].values[0])
            tipo_produto = produto['tipo'].values[0]
            
            # Ajustar estoque se necessário
            if tipo_produto in ['Card', 'Material Físico']:
                # Se for o mesmo produto
                if produto_id == produto_id_atual:
                    # Ajusta o estoque considerando a diferença de quantidade
                    estoque_atual = int(produto['quantidade'].values[0]) if produto['quantidade'].values[0] != "" else 0
                    estoque_ajustado = estoque_atual + quantidade_atual - quantidade
                    
                    if estoque_ajustado < 0:
                        raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual}")
                    
                    self.atualizar_estoque(produto_id, estoque_ajustado)
                else:
                    # Se for um produto diferente, devolve o estoque do produto anterior
                    produto_anterior = produtos[produtos['id'] == produto_id_atual]
                    if not produto_anterior.empty and produto_anterior['tipo'].values[0] in ['Card', 'Material Físico']:
                        estoque_anterior = int(produto_anterior['quantidade'].values[0]) if produto_anterior['quantidade'].values[0] != "" else 0
                        self.atualizar_estoque(produto_id_atual, estoque_anterior + quantidade_atual)
                    
                    # E reduz o estoque do novo produto
                    estoque_atual = int(produto['quantidade'].values[0]) if produto['quantidade'].values[0] != "" else 0
                    if quantidade > estoque_atual:
                        raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual}")
                    
                    self.atualizar_estoque(produto_id, estoque_atual - quantidade)
            
            # Encontra a linha da venda na planilha
            cell = self.vendas_sheet.find(str(id), in_column=1)
            if not cell:
                raise ValueError(f"Venda com ID {id} não encontrada na planilha")
            
            # Calcula o valor total
            valor_total = valor_unitario * quantidade
            
            # Formata a data de compra
            if isinstance(data_compra, datetime):
                data_compra = data_compra.strftime("%Y-%m-%d")
            
            # Atualiza os dados da venda
            self.vendas_sheet.update(f'A{cell.row}:L{cell.row}', [[
                id, produto_id, nome_produto, cliente, cpf_formatado,
                email, quantidade, valor_total, forma_pagamento,
                venda_atual['data_registro'].values[0], data_compra, venda_atual['status'].values[0]
            ]])
            
            return True
        except Exception as e:
            logging.error(f"Erro ao editar venda: {e}")
            st.error(f"Erro ao editar venda: {str(e)}")
            return False
    
    def remover_venda(self, id):
        """Remove uma venda da planilha e ajusta o estoque."""
        try:
            # Obter informações da venda
            vendas = self.listar_vendas()
            venda = vendas[vendas['id'] == id]
            
            if venda.empty:
                raise ValueError(f"Venda com ID {id} não encontrada")
            
            produto_id = venda['produto_id'].values[0]
            quantidade = int(venda['quantidade'].values[0])
            
            # Obter informações do produto para verificar se precisa ajustar estoque
            produtos = self.listar_produtos()
            produto = produtos[produtos['id'] == produto_id]
            
            if not produto.empty:
                tipo_produto = produto['tipo'].values[0]
                
                # Devolver ao estoque se for produto físico
                if tipo_produto in ['Card', 'Material Físico']:
                    estoque_atual = int(produto['quantidade'].values[0]) if produto['quantidade'].values[0] != "" else 0
                    self.atualizar_estoque(produto_id, estoque_atual + quantidade)
            
            # Encontra a linha da venda na planilha
            cell = self.vendas_sheet.find(str(id), in_column=1)
            if cell:
                self.vendas_sheet.delete_row(cell.row)
                return True
            else:
                raise ValueError(f"Venda com ID {id} não encontrada na planilha")
        except Exception as e:
            logging.error(f"Erro ao remover venda: {e}")
            st.error(f"Erro ao remover venda: {str(e)}")
            return False
    
    def listar_produtos(self):
        """Obtém a lista de produtos da planilha."""
        try:
            produtos_data = self.produtos_sheet.get_all_records()
            if not produtos_data:
                return pd.DataFrame(columns=[
                    'id', 'nome', 'tipo', 'valor', 'quantidade', 
                    'link_download', 'descricao', 'data_cadastro'
                ])
            
            df = pd.DataFrame(produtos_data)
            
            # Convertendo tipos de dados
            if not df.empty:
                df['id'] = df['id'].astype(int)
                df['valor'] = df['valor'].astype(float)
                
                # Trata valores vazios na coluna quantidade
                df['quantidade'] = df['quantidade'].replace('', 0)
                df['quantidade'] = pd.to_numeric(df['quantidade'], errors='coerce').fillna(0).astype(int)
            
            return df
        except Exception as e:
            logging.error(f"Erro ao listar produtos: {e}")
            st.error(f"Erro ao listar produtos: {e}")
            return pd.DataFrame()
    
    def listar_vendas(self):
        """Obtém a lista de vendas da planilha."""
        try:
            vendas_data = self.vendas_sheet.get_all_records()
            if not vendas_data:
                return pd.DataFrame(columns=[
                    'id', 'produto_id', 'produto_nome', 'cliente', 'cpf_cliente',
                    'email_cliente', 'quantidade', 'valor_total', 'forma_pagamento',
                    'data_registro', 'data_compra', 'status'
                ])
            
            df = pd.DataFrame(vendas_data)
            
            # Convertendo tipos de dados
            if not df.empty:
                df['id'] = df['id'].astype(int)
                df['produto_id'] = df['produto_id'].astype(int)
                df['quantidade'] = df['quantidade'].astype(int)
                df['valor_total'] = df['valor_total'].astype(float)
            
            return df
        except Exception as e:
            logging.error(f"Erro ao listar vendas: {e}")
            st.error(f"Erro ao listar vendas: {e}")
            return pd.DataFrame()
    
    def realizar_backup(self):
        """Exporta os dados para arquivos Excel e cria um backup no Google Drive."""
        try:
            # Obter os dados
            produtos_df = self.listar_produtos()
            vendas_df = self.listar_vendas()
            
            # Timestamp para o nome do arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"MEDIX_backup_{timestamp}.xlsx"
            
            # Criar arquivo Excel
            with pd.ExcelWriter(backup_filename) as writer:
                produtos_df.to_excel(writer, sheet_name='Produtos', index=False)
                vendas_df.to_excel(writer, sheet_name='Vendas', index=False)
            
            # Fazer upload do arquivo para o Google Drive
            file_metadata = {
                'name': backup_filename,
                'parents': [FOLDER_ID]
            }
            
            media = MediaFileUpload(backup_filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            
            # Remover o arquivo local
            os.remove(backup_filename)
            
            return backup_filename
        except Exception as e:
            logging.error(f"Erro ao realizar backup: {e}")
            st.error(f"Erro ao realizar backup: {e}")
            return None


# Funções da interface do usuário
def cadastrar_produto_ui(gestao):
    st.markdown("## 📦 Cadastro de Novo Produto")
    
    with st.form("cadastro_produto", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome do Produto", placeholder="Ex: Curso de Primeiros Socorros")
            valor = st.number_input("Valor (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        
        with col2:
            tipo = st.selectbox("Tipo de Produto", ["PDF", "Card", "Material Físico", "Aula"])
            if tipo in ['Card', 'Material Físico']:
                quantidade = st.number_input("Quantidade em Estoque", min_value=0, value=0, step=1)
            else:
                quantidade = None
        
        if tipo in ['PDF', 'Aula']:
            link_download = st.text_input("Link de Download", placeholder="Ex: https://drive.google.com/file/...")
        else:
            link_download = None
        
        descricao = st.text_area("Descrição do Produto", placeholder="Descreva o produto em detalhes...")
        
        col_button1, col_button2 = st.columns([1, 5])
        with col_button1:
            submit = st.form_submit_button("💾 Cadastrar", use_container_width=True)
        
        if submit:
            if not nome:
                st.error("🚫 Nome do produto é obrigatório!")
            elif valor <= 0:
                st.error("🚫 O valor do produto deve ser maior que zero!")
            else:
                sucesso = gestao.cadastrar_produto(nome, tipo, valor, quantidade, link_download, descricao)
                if sucesso:
                    st.success("✅ Produto cadastrado com sucesso!")
                    st.balloons()
                else:
                    st.error("❌ Erro ao cadastrar produto. Verifique os logs para mais detalhes.")

def registrar_venda_ui(gestao):
    st.markdown("## 💳 Registro de Nova Venda")
    
    produtos = gestao.listar_produtos()
    if produtos.empty:
        st.warning("⚠️ Não há produtos cadastrados. Cadastre um produto primeiro.")
        if st.button("➕ Ir para cadastro de produtos"):
            st.session_state.page = "cadastrar_produto"
            st.rerun()
    else:
        with st.form("registro_venda", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                # Dropdown para selecionar o produto com informações extras
                produtos['info'] = produtos.apply(lambda x: f"{x['nome']} - R$ {x['valor']:.2f}", axis=1)
                produto_opcoes = dict(zip(produtos['info'], produtos['id']))
                produto_selecionado = st.selectbox("Produto", list(produto_opcoes.keys()))
                produto_id = produto_opcoes[produto_selecionado]
                
                cliente = st.text_input("Nome do Cliente", placeholder="Nome completo")
                cpf = st.text_input("CPF do Cliente (opcional)", help="Digite apenas números", placeholder="Ex: 12345678900")
            
            with col2:
                email = st.text_input("Email do Cliente", placeholder="Ex: cliente@email.com")
                
                # Obter informações do produto selecionado
                produto_info = produtos[produtos['id'] == produto_id].iloc[0]
                tipo_produto = produto_info['tipo']
                
                # Mostrar estoque disponível para produtos físicos
                if tipo_produto in ['Card', 'Material Físico']:
                    estoque_max = int(produto_info['quantidade'])
                    st.info(f"📦 Estoque disponível: {estoque_max} unidades")
                    quantidade = st.number_input("Quantidade", min_value=1, max_value=estoque_max, value=min(1, estoque_max), step=1)
                else:
                    quantidade = st.number_input("Quantidade", min_value=1, value=1, step=1)
                
                forma_pagamento = st.selectbox("Forma de Pagamento", ["Pix", "Cartão de Crédito", "Cartão de Débito", "Transferência Bancária", "Dinheiro"])
                data_compra = st.date_input("Data da Compra", datetime.now())
            
            # Mostrar valor total calculado
            valor_unitario = float(produto_info['valor'])
            valor_total = valor_unitario * quantidade
            st.info(f"💰 Valor Total: R$ {valor_total:.2f}")
            
            col_button1, col_button2 = st.columns([1, 5])
            with col_button1:
                submit_venda = st.form_submit_button("💾 Registrar", use_container_width=True)
            
            if submit_venda:
                try:
                    if not cliente:
                        st.error("🚫 Nome do cliente é obrigatório!")
                    else:
                        if gestao.registrar_venda(produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra):
                            st.success("✅ Venda registrada com sucesso!")
                            st.balloons()
                        else:
                            st.error("❌ Falha ao registrar a venda")
                except ValueError as e:
                    st.error(f"🚫 {str(e)}")
                except Exception as e:
                    st.error(f"❌ Erro inesperado: {str(e)}")
                    logging.error(f"Erro inesperado ao registrar venda: {str(e)}")

def listar_produtos_ui(gestao):
    st.markdown("## 📋 Lista de Produtos")
    
    # Adicionar filtros
    col1, col2 = st.columns([2, 3])
    with col1:
        filtro_tipo = st.multiselect("Filtrar por tipo", ["PDF", "Card", "Material Físico", "Aula"], default=None)
    
    with col2:
        busca = st.text_input("Buscar produto", placeholder="Digite para buscar...")
    
    produtos = gestao.listar_produtos()
    
    if produtos.empty:
        st.warning("⚠️ Nenhum produto cadastrado")
        if st.button("➕ Cadastrar Produto"):
            st.session_state.page = "cadastrar_produto"
            st.rerun()
    else:
        # Aplicar filtros
        if filtro_tipo:
            produtos = produtos[produtos['tipo'].isin(filtro_tipo)]
        
        if busca:
            produtos = produtos[produtos['nome'].str.contains(busca, case=False) | 
                              produtos['descricao'].str.contains(busca, case=False)]
        
        # Exibir produtos
        for index, row in produtos.iterrows():
            with st.expander(f"{row['nome']} - {row['tipo']}"):
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.markdown(f"**Tipo:** {row['tipo']}")
                    st.markdown(f"**Valor:** R$ {float(row['valor']):.2f}")
                    
                    if row['tipo'] in ['Card', 'Material Físico']:
                        if row['quantidade'] and int(row['quantidade']) > 0:
                            st.markdown(f"**Estoque:** {int(row['quantidade'])} unidades")
                        else:
                            st.markdown("**Estoque:** Esgotado", unsafe_allow_html=True)
                    
                    if row['link_download']:
                        st.markdown(f"**Link:** [{row['link_download']}]({row['link_download']})")
                    
                    if row['descricao']:
                        st.markdown(f"**Descrição:** {row['descricao']}")
                
                with col2:
                    if st.button(f"✏️ Editar", key=f"edit_{row['id']}", use_container_width=True):
                        st.session_state.editing_product = row['id']
                
                with col3:
                    if st.button(f"🗑️ Remover", key=f"remove_{row['id']}", use_container_width=True):
                        try:
                            if gestao.remover_produto(row['id']):
                                st.success(f"✅ Produto {row['nome']} removido com sucesso!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ Erro ao remover o produto {row['nome']}")
                        except ValueError as e:
                            st.error(f"🚫 {str(e)}")
        
        # Modal para edição
        if 'editing_product' in st.session_state:
            produto = produtos[produtos['id'] == st.session_state.editing_product].iloc[0]
            
            st.markdown(f"### ✏️ Editando: {produto['nome']}")
            
            with st.form("editar_produto"):
                col1, col2 = st.columns(2)
                
                with col1:
                    nome = st.text_input("Nome do Produto", value=produto['nome'])
                    valor = st.number_input("Valor", min_value=0.0, value=float(produto['valor']), step=0.01, format="%.2f")
                
                with col2:
                    tipo = st.selectbox("Tipo de Produto", ["PDF", "Card", "Material Físico", "Aula"], index=["PDF", "Card", "Material Físico", "Aula"].index(produto['tipo']))
                    
                    if tipo in ['Card', 'Material Físico']:
                        quantidade = st.number_input("Quantidade", min_value=0, value=int(produto['quantidade']), step=1)
                    else:
                        quantidade = 0
                
                if tipo in ['PDF', 'Aula']:
                    link_download = st.text_input("Link de Download", value=produto['link_download'] if produto['link_download'] else "")
                else:
                    link_download = ""
                
                descricao = st.text_area("Descrição", value=produto['descricao'] if produto['descricao'] else "")
                
                col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 3])
                with col_btn1:
                    submit_edit = st.form_submit_button("💾 Atualizar", use_container_width=True)
                
                with col_btn2:
                    cancel_edit = st.form_submit_button("❌ Cancelar", use_container_width=True)
                
                if submit_edit:
                    if gestao.editar_produto(st.session_state.editing_product, nome, tipo, valor, quantidade, link_download, descricao):
                        st.success("✅ Produto atualizado com sucesso!")
                        del st.session_state.editing_product
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Erro ao atualizar o produto")
                
                if cancel_edit:
                    del st.session_state.editing_product
                    st.rerun()

def listar_vendas_ui(gestao):
    st.markdown("## 📊 Lista de Vendas")
    
    # Adicionar filtros
    col1, col2, col3 = st.columns([2, 2, 3])
    
    with col1:
        data_inicio = st.date_input("Data inicial", value=datetime.now().replace(day=1))
    
    with col2:
        data_fim = st.date_input("Data final", value=datetime.now())
    
    with col3:
        busca = st.text_input("Buscar por cliente ou produto", placeholder="Digite para buscar...")
    
    vendas = gestao.listar_vendas()
    
    if vendas.empty:
        st.warning("⚠️ Nenhuma venda registrada")
        if st.button("➕ Registrar Venda"):
            st.session_state.page = "registrar_venda"
            st.rerun()
    else:
        # Converter as colunas de data para datetime
        vendas['data_compra'] = pd.to_datetime(vendas['data_compra'])
        
        # Aplicar filtros
        vendas_filtradas = vendas[
            (vendas['data_compra'] >= pd.Timestamp(data_inicio)) & 
            (vendas['data_compra'] <= pd.Timestamp(data_fim))
        ]
        
        if busca:
            vendas_filtradas = vendas_filtradas[
                vendas_filtradas['cliente'].str.contains(busca, case=False) | 
                vendas_filtradas['produto_nome'].str.contains(busca, case=False)
            ]
        
        # Calcular totais
        if not vendas_filtradas.empty:
            total_valor = vendas_filtradas['valor_total'].sum()
            total_vendas = len(vendas_filtradas)
            
            # Mostrar estatísticas
            st.subheader("📈 Resumo do Período")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total de Vendas", f"{total_vendas}")
            
            with col2:
                st.metric("Valor Total", f"R$ {total_valor:.2f}")
            
            with col3:
                st.metric("Ticket Médio", f"R$ {(total_valor / total_vendas):.2f}" if total_vendas > 0 else "R$ 0.00")
            
            # Gráfico de vendas por dia
            vendas_por_dia = vendas_filtradas.groupby(vendas_filtradas['data_compra'].dt.date)['valor_total'].sum().reset_index()
            vendas_por_dia.columns = ['Data', 'Valor Total']
            
            # Plotar gráfico de barras
            fig = px.bar(
                vendas_por_dia, 
                x='Data', 
                y='Valor Total',
                labels={'valor_total': 'Valor Total (R$)'},
                title='Vendas Diárias no Período'
            )
            fig.update_layout(xaxis_title="Data", yaxis_title="Valor Total (R$)")
            st.plotly_chart(fig, use_container_width=True)
        
        # Tabela de vendas
        st.subheader("📝 Detalhes das Vendas")
        
        if vendas_filtradas.empty:
            st.info("Nenhuma venda encontrada para os filtros selecionados.")
        else:
            # Formatar dados para exibição
            vendas_display = vendas_filtradas.copy()
            vendas_display['data_compra'] = vendas_display['data_compra'].dt.strftime('%d/%m/%Y')
            vendas_display['valor_total'] = vendas_display['valor_total'].apply(lambda x: f"R$ {x:.2f}")
            
            # Exibir vendas
            for index, row in vendas_filtradas.iterrows():
                with st.expander(f"Venda #{row['id']} - {row['cliente']} - {pd.to_datetime(row['data_compra']).strftime('%d/%m/%Y')}"):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.markdown(f"**Cliente:** {row['cliente']}")
                        st.markdown(f"**Produto:** {row['produto_nome']}")
                        st.markdown(f"**Quantidade:** {row['quantidade']}")
                        st.markdown(f"**Valor Total:** R$ {float(row['valor_total']):.2f}")
                        st.markdown(f"**Forma de Pagamento:** {row['forma_pagamento']}")
                        
                        if row['cpf_cliente']:
                            st.markdown(f"**CPF:** {row['cpf_cliente']}")
                        
                        if row['email_cliente']:
                            st.markdown(f"**Email:** {row['email_cliente']}")
                    
                    with col2:
                        if st.button(f"✏️ Editar", key=f"edit_v_{row['id']}", use_container_width=True):
                            st.session_state.editing_sale = row['id']
                    
                    with col3:
                        if st.button(f"🗑️ Remover", key=f"remove_v_{row['id']}", use_container_width=True):
                            if gestao.remover_venda(row['id']):
                                st.success(f"✅ Venda #{row['id']} removida com sucesso!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ Erro ao remover a venda #{row['id']}")
            
            # Modal para edição de venda
            if 'editing_sale' in st.session_state:
                venda = vendas_filtradas[vendas_filtradas['id'] == st.session_state.editing_sale].iloc[0]
                
                st.markdown(f"### ✏️ Editando Venda #{venda['id']}")
                
                with st.form("editar_venda"):
                    produtos = gestao.listar_produtos()
                    
                    # Preparar dados para o dropdown de produtos
                    produtos['info'] = produtos.apply(lambda x: f"{x['nome']} - R$ {x['valor']:.2f}", axis=1)
                    opcoes_produtos = dict(zip(produtos['info'], produtos['id']))
                    
                    # Encontrar o índice do produto atual
                    produto_atual = produtos[produtos['id'] == venda['produto_id']]
                    if not produto_atual.empty:
                        produto_info_atual = produto_atual['info'].values[0]
                        idx = list(opcoes_produtos.keys()).index(produto_info_atual)
                    else:
                        idx = 0
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        produto_selecionado = st.selectbox("Produto", list(opcoes_produtos.keys()), index=idx)
                        cliente = st.text_input("Nome do Cliente", value=venda['cliente'])
                        cpf = st.text_input("CPF do Cliente", value=venda['cpf_cliente'] if venda['cpf_cliente'] else "")
                    
                    with col2:
                        email = st.text_input("Email do Cliente", value=venda['email_cliente'] if venda['email_cliente'] else "")
                        quantidade = st.number_input("Quantidade", min_value=1, value=int(venda['quantidade']))
                        forma_pagamento = st.selectbox(
                            "Forma de Pagamento", 
                            ["Pix", "Cartão de Crédito", "Cartão de Débito", "Transferência Bancária", "Dinheiro"],
                            index=["Pix", "Cartão de Crédito", "Cartão de Débito", "Transferência Bancária", "Dinheiro"].index(venda['forma_pagamento'])
                            if venda['forma_pagamento'] in ["Pix", "Cartão de Crédito", "Cartão de Débito", "Transferência Bancária", "Dinheiro"] else 0
                        )
                    
                    # Data da compra
                    data_compra = st.date_input(
                        "Data da Compra", 
                        value=pd.to_datetime(venda['data_compra']).date() if pd.notnull(venda['data_compra']) else datetime.now()
                    )
                    
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 3])
                    
                    with col_btn1:
                        submit_edit = st.form_submit_button("💾 Atualizar", use_container_width=True)
                    
                    with col_btn2:
                        cancel_edit = st.form_submit_button("❌ Cancelar", use_container_width=True)
                    
                    if submit_edit:
                        produto_id = opcoes_produtos[produto_selecionado]
                        if gestao.editar_venda(
                            st.session_state.editing_sale, produto_id, cliente, 
                            cpf, email, quantidade, forma_pagamento, data_compra
                        ):
                            st.success("✅ Venda atualizada com sucesso!")
                            del st.session_state.editing_sale
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ Erro ao atualizar a venda")
                    
                    if cancel_edit:
                        del st.session_state.editing_sale
                        st.rerun()

def backup_ui(gestao):
    st.markdown("## 💾 Backup e Restauração")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Realizar Backup")
        st.markdown("Crie um backup dos seus dados e salve-o no Google Drive.")
        
        if st.button("🔄 Iniciar Backup", use_container_width=True):
            with st.spinner("Realizando backup..."):
                try:
                    backup_file = gestao.realizar_backup()
                    if backup_file:
                        st.success(f"✅ Backup realizado com sucesso! Arquivo '{backup_file}' salvo no Google Drive.")
                        st.balloons()
                    else:
                        st.error("❌ Erro ao realizar backup.")
                except Exception as e:
                    logging.error(f"Erro ao realizar backup: {e}")
                    st.error(f"❌ Erro ao realizar backup: {e}")

def visualizar_planilha_ui(gestao):
    st.markdown("## 👀 Visualizar Dados")
    
    # Tabs para diferentes visualizações
    tab1, tab2, tab3 = st.tabs(["📊 Tabelas", "📈 Gráficos", "💰 Financeiro"])
    
    with tab1:
        tipo = st.radio("Selecione o tipo de dados", ["Produtos", "Vendas"], horizontal=True)
        
        if tipo == "Produtos":
            df = gestao.listar_produtos()
            
            if not df.empty:
                # Ajustar colunas para exibição
                df_display = df.copy()
                df_display['valor'] = df_display['valor'].apply(lambda x: f"R$ {float(x):.2f}")
                
                # Ocultar colunas menos importantes
                colunas_exibir = ['id', 'nome', 'tipo', 'valor', 'quantidade']
                if 'data_cadastro' in df_display.columns:
                    colunas_exibir.append('data_cadastro')
                
                st.dataframe(
                    df_display[colunas_exibir],
                    column_config={
                        "id": "ID",
                        "nome": "Nome do Produto",
                        "tipo": "Tipo",
                        "valor": "Valor",
                        "quantidade": "Estoque",
                        "data_cadastro": "Data de Cadastro"
                    },
                    use_container_width=True
                )
                
                # Opção para exportar
                if st.button("📥 Exportar para Excel"):
                    with st.spinner("Gerando arquivo..."):
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df.to_excel(writer, sheet_name='Produtos', index=False)
                        
                        st.download_button(
                            label="📥 Baixar Excel",
                            data=buffer.getvalue(),
                            file_name=f"MEDIX_Produtos_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
            else:
                st.warning("⚠️ Nenhum produto cadastrado")
        
        else:  # Vendas
            df = gestao.listar_vendas()
            
            if not df.empty:
                # Ajustar colunas para exibição
                df_display = df.copy()
                df_display['valor_total'] = df_display['valor_total'].apply(lambda x: f"R$ {float(x):.2f}")
                df_display['data_compra'] = pd.to_datetime(df_display['data_compra']).dt.strftime('%d/%m/%Y')
                if 'data_registro' in df_display.columns:
                    df_display['data_registro'] = pd.to_datetime(df_display['data_registro']).dt.strftime('%d/%m/%Y %H:%M')
                
                # Ocultar colunas menos importantes
                colunas_exibir = ['id', 'produto_nome', 'cliente', 'quantidade', 'valor_total', 'forma_pagamento', 'data_compra']
                
                st.dataframe(
                    df_display[colunas_exibir],
                    column_config={
                        "id": "ID",
                        "produto_nome": "Produto",
                        "cliente": "Cliente",
                        "quantidade": "Qtd",
                        "valor_total": "Valor Total",
                        "forma_pagamento": "Pagamento",
                        "data_compra": "Data da Compra"
                    },
                    use_container_width=True
                )
                
                # Opção para exportar
                if st.button("📥 Exportar para Excel"):
                    with st.spinner("Gerando arquivo..."):
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df.to_excel(writer, sheet_name='Vendas', index=False)
                        
                        st.download_button(
                            label="📥 Baixar Excel",
                            data=buffer.getvalue(),
                            file_name=f"MEDIX_Vendas_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
            else:
                st.warning("⚠️ Nenhuma venda registrada")
    
    with tab2:
        if gestao.listar_vendas().empty:
            st.warning("⚠️ Nenhuma venda registrada para gerar gráficos.")
        else:
            chart_type = st.selectbox(
                "Selecione o tipo de gráfico",
                ["Vendas por Período", "Produtos Mais Vendidos", "Formas de Pagamento", "Valor vs Quantidade"]
            )
            
            vendas = gestao.listar_vendas()
            vendas['data_compra'] = pd.to_datetime(vendas['data_compra'])
            
            if chart_type == "Vendas por Período":
                periodo = st.radio("Agrupar por:", ["Dia", "Mês", "Ano"], horizontal=True)
                
                if periodo == "Dia":
                    vendas_agrupadas = vendas.groupby(vendas['data_compra'].dt.date)['valor_total'].sum().reset_index()
                    vendas_agrupadas.columns = ['Data', 'Valor Total']
                    
                    fig = px.bar(
                        vendas_agrupadas, 
                        x='Data', 
                        y='Valor Total',
                        title='Vendas Diárias',
                        labels={'Valor Total': 'Valor Total (R$)'}
                    )
                
                elif periodo == "Mês":
                    vendas['mes_ano'] = vendas['data_compra'].dt.strftime('%Y-%m')
                    vendas_agrupadas = vendas.groupby('mes_ano')['valor_total'].sum().reset_index()
                    vendas_agrupadas.columns = ['Mês/Ano', 'Valor Total']
                    
                    fig = px.bar(
                        vendas_agrupadas, 
                        x='Mês/Ano', 
                        y='Valor Total',
                        title='Vendas Mensais',
                        labels={'Valor Total': 'Valor Total (R$)'}
                    )
                
                else:  # Ano
                    vendas_agrupadas = vendas.groupby(vendas['data_compra'].dt.year)['valor_total'].sum().reset_index()
                    vendas_agrupadas.columns = ['Ano', 'Valor Total']
                    
                    fig = px.bar(
                        vendas_agrupadas, 
                        x='Ano', 
                        y='Valor Total',
                        title='Vendas Anuais',
                        labels={'Valor Total': 'Valor Total (R$)'}
                    )
                
                st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "Produtos Mais Vendidos":
                top_n = st.slider("Número de produtos", 3, 10, 5)
                
                # Agrupar por produto e somar quantidades
                produtos_vendidos = vendas.groupby('produto_nome')['quantidade'].sum().reset_index()
                produtos_vendidos = produtos_vendidos.sort_values('quantidade', ascending=False).head(top_n)
                
                fig = px.bar(
                    produtos_vendidos,
                    x='produto_nome',
                    y='quantidade',
                    title=f'Top {top_n} Produtos Mais Vendidos',
                    labels={'produto_nome': 'Produto', 'quantidade': 'Quantidade Vendida'}
                )
                fig.update_layout(xaxis_title="Produto", yaxis_title="Quantidade Vendida")
                
                st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "Formas de Pagamento":
                # Agrupar por forma de pagamento
                pagamentos = vendas.groupby('forma_pagamento')['valor_total'].sum().reset_index()
                
                fig = px.pie(
                    pagamentos,
                    values='valor_total',
                    names='forma_pagamento',
                    title='Distribuição de Formas de Pagamento',
                    hole=0.4
                )
                
                fig.update_traces(textposition='inside', textinfo='percent+label')
                
                st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "Valor vs Quantidade":
                # Scatter plot de valor vs quantidade
                fig = px.scatter(
                    vendas,
                    x='quantidade',
                    y='valor_total',
                    color='produto_nome',
                    size='quantidade',
                    hover_name='cliente',
                    title='Relação entre Quantidade e Valor Total por Produto',
                    labels={'quantidade': 'Quantidade', 'valor_total': 'Valor Total (R$)', 'produto_nome': 'Produto'}
                )
                
                st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        if gestao.listar_vendas().empty:
            st.warning("⚠️ Nenhuma venda registrada para análise financeira.")
        else:
            st.subheader("💰 Análise Financeira")
            
            # Filtros de período
            col1, col2 = st.columns(2)
            with col1:
                data_inicio = st.date_input("Data inicial", value=datetime.now().replace(day=1))
            with col2:
                data_fim = st.date_input("Data final", value=datetime.now())
            
            vendas = gestao.listar_vendas()
            vendas['data_compra'] = pd.to_datetime(vendas['data_compra'])
            
            # Filtrar por período
            vendas_periodo = vendas[
                (vendas['data_compra'] >= pd.Timestamp(data_inicio)) & 
                (vendas['data_compra'] <= pd.Timestamp(data_fim))
            ]
            
            if vendas_periodo.empty:
                st.info("Não há vendas no período selecionado.")
            else:
                # Calcular métricas financeiras
                receita_total = vendas_periodo['valor_total'].sum()
                total_vendas = len(vendas_periodo)
                ticket_medio = receita_total / total_vendas if total_vendas > 0 else 0
                
                # Valor médio por produto
                valor_por_produto = vendas_periodo.groupby('produto_nome')['valor_total'].sum().reset_index()
                top_produto = valor_por_produto.sort_values('valor_total', ascending=False).iloc[0]['produto_nome']
                valor_top_produto = valor_por_produto.sort_values('valor_total', ascending=False).iloc[0]['valor_total']
                
                # Exibir métricas
                st.subheader("📊 Resumo Financeiro")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Receita Total", f"R$ {receita_total:.2f}")
                with col2:
                    st.metric("Número de Vendas", f"{total_vendas}")
                with col3:
                    st.metric("Ticket Médio", f"R$ {ticket_medio:.2f}")
                
                # Mais insights
                st.subheader("🔍 Insights")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Produto Mais Rentável", top_produto, f"R$ {valor_top_produto:.2f}")
                
                with col2:
                    # Forma de pagamento mais utilizada
                    pagamento_mais_usado = vendas_periodo['forma_pagamento'].value_counts().index[0]
                    porcentagem_pagamento = (vendas_periodo['forma_pagamento'].value_counts().iloc[0] / total_vendas) * 100
                    st.metric("Forma de Pagamento Mais Usada", pagamento_mais_usado, f"{porcentagem_pagamento:.1f}%")
                
                # Gráfico de evolução de receita
                st.subheader("📈 Evolução da Receita")
                
                # Agrupar por dia
                receita_diaria = vendas_periodo.groupby(vendas_periodo['data_compra'].dt.date)['valor_total'].sum().reset_index()
                
                # Calcular média móvel de 7 dias
                if len(receita_diaria) > 7:
                    receita_diaria['media_movel'] = receita_diaria['valor_total'].rolling(window=7, min_periods=1).mean()
                    
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=receita_diaria['data_compra'],
                        y=receita_diaria['valor_total'],
                        name='Receita Diária',
                        marker_color='lightblue'
                    ))
                    fig.add_trace(go.Scatter(
                        x=receita_diaria['data_compra'],
                        y=receita_diaria['media_movel'],
                        name='Média Móvel (7 dias)',
                        line=dict(color='red', width=2)
                    ))
                    fig.update_layout(
                        title='Evolução da Receita Diária',
                        xaxis_title='Data',
                        yaxis_title='Receita (R$)',
                        legend=dict(x=0, y=1.1, orientation='h')
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    fig = px.bar(
                        receita_diaria,
                        x='data_compra',
                        y='valor_total',
                        title='Evolução da Receita Diária',
                        labels={'data_compra': 'Data', 'valor_total': 'Receita (R$)'}
                    )
                    st.plotly_chart(fig, use_container_width=True)

def configuracoes_ui(gestao):
    st.markdown("## ⚙️ Configurações")
    
    st.subheader("🔐 Acesso ao Google Drive")
    st.markdown("""
    O sistema está configurado para salvar os dados na seguinte pasta do Google Drive:
    
    **Pasta:** [Gestão Produtos](https://drive.google.com/drive/folders/1HDN1suMspx1um0xbK34waXZ5VGUmseB6)
    
    Todos os dados de produtos e vendas são armazenados em tempo real em planilhas do Google Sheets 
    dentro desta pasta, garantindo acesso fácil e segurança de backup automático.
    """)
    
    st.subheader("🎨 Personalização")
    
    # Tema da aplicação
    tema = st.selectbox(
        "Tema da aplicação",
        ["Padrão", "Claro", "Escuro", "Azul Médico"],
        index=0
    )
    
    if tema != "Padrão":
        st.info("A mudança de tema será implementada na próxima atualização.")
    
    # Informações do Sistema
    st.subheader("ℹ️ Informações do Sistema")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Versão:** 1.0.0")
        st.markdown("**Última atualização:** 25/03/2025")
        st.markdown("**Desenvolvido por:** MEDIX Team")
    
    with col2:
        st.markdown("**Status:** Conectado ao Google Drive")
        st.markdown("**Armazenamento:** Google Sheets")
        st.markdown("**Suporte:** suporte@medix.com")
    
    # Botão para testar conexão
    if st.button("🔄 Testar Conexão com Google Drive"):
        with st.spinner("Testando conexão..."):
            try:
                # Tentar obter as planilhas para testar a conexão
                gestao.inicializar_planilhas()
                st.success("✅ Conexão bem sucedida! O sistema está conectado ao Google Drive.")
            except Exception as e:
                st.error(f"❌ Falha na conexão: {e}")

def main():
    # Configuração da página
    st.set_page_config(
        page_title="MEDIX - Gestão de Produtos e Vendas",
        page_icon="🩺",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # CSS personalizado
    st.markdown("""
    <style>
    /* Estilo geral */
    .main {
        background-color: #f8f9fa;
    }
    
    /* Cabeçalhos */
    h1, h2, h3, h4 {
        color: #2c3e50;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Botões */
    .stButton > button {
        background-color: #3498db;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    
    .stButton > button:hover {
        background-color: #2980b9;
    }
    
    /* Containers */
    .css-1r6slb0 {
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background-color: #f1f8fe;
        border-radius: 5px;
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #2c3e50 !important;
    }
    
    [data-testid="stMetricDelta"] {
        font-size: 1rem !important;
        font-weight: 500 !important;
    }
    
    /* Menu lateral */
    .css-1d391kg {
        background-color: #2c3e50;
    }
    
    /* Footer */
    footer {
        visibility: hidden;
    }
    
    /* Formulários */
    .stForm {
        background-color: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
    }
    
    /* Alertas e mensagens */
    .stAlert {
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Inicializar sessão
    if 'page' not in st.session_state:
        st.session_state.page = "home"
    
    if 'gestao' not in st.session_state:
        st.session_state.gestao = GestaoVendasGoogleSheets()
    
    gestao = st.session_state.gestao
    
    # Sidebar com menu
    with st.sidebar:
        # Logo
        st.image("https://i.imgur.com/gKyBL7S.png", width=100)
        st.title("🩺 MEDIX")
        st.caption("Sistema de Gestão de Produtos e Vendas")
        
        # Menu de navegação
        menu = option_menu(
            "Menu Principal",
            [
                "📊 Dashboard",
                "📦 Cadastrar Produto", 
                "💳 Registrar Venda", 
                "📋 Listar Produtos", 
                "📊 Listar Vendas",
                "👀 Visualizar Dados",
                "💾 Backup",
                "⚙️ Configurações"
            ],
            icons=[
                "house", 
                "box-seam", 
                "credit-card", 
                "list-check", 
                "graph-up", 
                "eye", 
                "cloud-arrow-up", 
                "gear"
            ],
            menu_icon="cast",
            default_index=0,
        )
        
        st.session_state.page = menu.lower().replace(" ", "_")
        
        # Informações de uso
        st.markdown("---")
        st.caption("Dados armazenados no Google Drive")
        st.caption("© 2023 MEDIX Health Systems")
    
    # Conteúdo principal
    if st.session_state.page == "📊_dashboard":
        st.title("📊 Dashboard - MEDIX")
        
        # Visão geral dos dados
        produtos = gestao.listar_produtos()
        vendas = gestao.listar_vendas()
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total de Produtos", len(produtos) if not produtos.empty else 0)
        
        with col2:
            st.metric("Total de Vendas", len(vendas) if not vendas.empty else 0)
        
        with col3:
            receita_total = vendas['valor_total'].sum() if not vendas.empty else 0
            st.metric("Receita Total", f"R$ {receita_total:.2f}")
        
        with col4:
            if not vendas.empty and len(vendas) > 0:
                ticket_medio = receita_total / len(vendas)
                st.metric("Ticket Médio", f"R$ {ticket_medio:.2f}")
            else:
                st.metric("Ticket Médio", "R$ 0.00")
        
        # Gráficos do dashboard
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Vendas Recentes")
            if not vendas.empty:
                # Converter data_compra para datetime
                vendas['data_compra'] = pd.to_datetime(vendas['data_compra'])
                
                # Agrupar por dia para os últimos 30 dias
                data_limite = pd.Timestamp.now() - pd.Timedelta(days=30)
                vendas_recentes = vendas[vendas['data_compra'] >= data_limite]
                
                if not vendas_recentes.empty:
                    vendas_por_dia = vendas_recentes.groupby(vendas_recentes['data_compra'].dt.date)['valor_total'].sum().reset_index()
                    vendas_por_dia.columns = ['Data', 'Valor']
                    
                    fig = px.line(
                        vendas_por_dia, 
                        x='Data', 
                        y='Valor',
                        title='Vendas nos Últimos 30 Dias',
                        labels={'Valor': 'Valor Total (R$)'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Não há vendas nos últimos 30 dias.")
            else:
                st.info("Não há vendas registradas.")
        
        with col2:
            st.subheader("🔝 Produtos Mais Vendidos")
            if not vendas.empty:
                produtos_vendidos = vendas.groupby('produto_nome')['quantidade'].sum().reset_index()
                produtos_vendidos = produtos_vendidos.sort_values('quantidade', ascending=False).head(5)
                
                if not produtos_vendidos.empty:
                    fig = px.bar(
                        produtos_vendidos,
                        y='produto_nome',
                        x='quantidade',
                        title='Top 5 Produtos Mais Vendidos',
                        labels={'produto_nome': 'Produto', 'quantidade': 'Quantidade Vendida'},
                        orientation='h'
                    )
                    fig.update_layout(yaxis={'categoryorder': 'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Não há produtos vendidos ainda.")
            else:
                st.info("Não há vendas registradas.")
        
        # Alertas de estoque
        st.subheader("⚠️ Alertas de Estoque")
        if not produtos.empty:
            produtos_fisicos = produtos[produtos['tipo'].isin(['Card', 'Material Físico'])]
            
            if not produtos_fisicos.empty:
                # Filtrar produtos com estoque baixo (menos de 5 unidades)
                baixo_estoque = produtos_fisicos[produtos_fisicos['quantidade'] < 5]
                
                if not baixo_estoque.empty:
                    st.warning("Produtos com estoque baixo (menos de 5 unidades):")
                    for _, produto in baixo_estoque.iterrows():
                        st.info(f"{produto['nome']} - Estoque atual: {produto['quantidade']} unidades")
                else:
                    st.success("Todos os produtos possuem estoque adequado.")
            else:
                st.info("Não há produtos físicos cadastrados.")
        else:
            st.info("Não há produtos cadastrados.")
        
        # Últimas vendas
        st.subheader("📝 Últimas Vendas")
        if not vendas.empty:
            ultimas_vendas = vendas.sort_values('data_registro', ascending=False).head(5)
            
            for _, venda in ultimas_vendas.iterrows():
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.write(f"**{venda['cliente']}** - {venda['produto_nome']}")
                
                with col2:
                    st.write(f"R$ {float(venda['valor_total']):.2f}")
                
                with col3:
                    st.write(pd.to_datetime(venda['data_compra']).strftime('%d/%m/%Y'))
                
                st.markdown("---")
        else:
            st.info("Não há vendas registradas.")
    
    elif st.session_state.page == "📦_cadastrar_produto":
        cadastrar_produto_ui(gestao)
    
    elif st.session_state.page == "💳_registrar_venda":
        registrar_venda_ui(gestao)
    
    elif st.session_state.page == "📋_listar_produtos":
        listar_produtos_ui(gestao)
    
    elif st.session_state.page == "📊_listar_vendas":
        listar_vendas_ui(gestao)
    
    elif st.session_state.page == "👀_visualizar_dados":
        visualizar_planilha_ui(gestao)
    
    elif st.session_state.page == "💾_backup":
        backup_ui(gestao)
    
    elif st.session_state.page == "⚙️_configurações":
        configuracoes_ui(gestao)
