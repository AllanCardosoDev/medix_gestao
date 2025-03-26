import streamlit as st
import pandas as pd
from datetime import datetime
import re
import io
import os
import logging
import time
import json
import uuid
import plotly.express as px
import plotly.graph_objects as go
from credentials_manager import get_credentials  # Novo import para o gerenciador de credenciais

# Tentar importar bibliotecas do Google, mas não falhar se não estiverem disponíveis
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    google_imports_successful = True
except ImportError:
    google_imports_successful = False

# Tentar importar o menu de opções
try:
    from streamlit_option_menu import option_menu
    option_menu_available = True
except ImportError:
    option_menu_available = False

# Configuração de logging
logging.basicConfig(level=logging.INFO, 
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

def autenticar_google():
    """Autentica com a API do Google usando o gerenciador de credenciais."""
    if not google_imports_successful:
        st.error("Bibliotecas do Google não estão disponíveis. Verifique se estão instaladas corretamente.")
        return None
        
    try:
        # Usar o gerenciador de credenciais para obter as credenciais
        credentials = get_credentials()
        if credentials:
            logging.info("Credenciais obtidas com sucesso do gerenciador de credenciais")
            return credentials
        else:
            logging.error("Falha ao obter credenciais - objeto de credenciais é None")
            return None
    except Exception as e:
        logging.error(f"Erro na autenticação: {e}")
        st.error(f"Erro na autenticação com Google API: {e}")
        return None

# Classe para gerenciamento com storage local (fallback quando Google falha)
class GestaoVendasLocal:
    def __init__(self):
        self.produtos = []
        self.vendas = []
        self.next_produto_id = 1
        self.next_venda_id = 1
        # Carregar dados se existirem
        self.carregar_dados()
    
    def carregar_dados(self):
        try:
            if os.path.exists('produtos_local.json'):
                with open('produtos_local.json', 'r') as f:
                    self.produtos = json.load(f)
                if self.produtos:
                    self.next_produto_id = max([p.get('id', 0) for p in self.produtos]) + 1
            
            if os.path.exists('vendas_local.json'):
                with open('vendas_local.json', 'r') as f:
                    self.vendas = json.load(f)
                if self.vendas:
                    self.next_venda_id = max([v.get('id', 0) for v in self.vendas]) + 1
        except Exception as e:
            logging.error(f"Erro ao carregar dados locais: {e}")
            st.error(f"Erro ao carregar dados locais: {e}")
    
    def salvar_dados(self):
        try:
            with open('produtos_local.json', 'w') as f:
                json.dump(self.produtos, f)
            
            with open('vendas_local.json', 'w') as f:
                json.dump(self.vendas, f)
        except Exception as e:
            logging.error(f"Erro ao salvar dados locais: {e}")
            st.error(f"Erro ao salvar dados locais: {e}")
    
    def validar_produto(self, nome, id=None):
        if id:
            return not any(p['nome'] == nome and p['id'] != id for p in self.produtos)
        else:
            return not any(p['nome'] == nome for p in self.produtos)
    
    def cadastrar_produto(self, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        try:
            if not self.validar_produto(nome):
                raise ValueError("Já existe um produto com este nome")
            
            produto = {
                'id': self.next_produto_id,
                'nome': nome,
                'tipo': tipo,
                'valor': float(valor),
                'quantidade': int(quantidade or 0),
                'link_download': link_download or "",
                'descricao': descricao or "",
                'data_cadastro': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            self.produtos.append(produto)
            self.next_produto_id += 1
            self.salvar_dados()
            return True
        except Exception as e:
            logging.error(f"Erro ao cadastrar produto: {e}")
            st.error(f"Erro ao cadastrar produto: {e}")
            return False
    
    def editar_produto(self, id, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        try:
            if not self.validar_produto(nome, id):
                raise ValueError("Já existe outro produto com este nome")
            
            for produto in self.produtos:
                if produto['id'] == id:
                    produto['nome'] = nome
                    produto['tipo'] = tipo
                    produto['valor'] = float(valor)
                    produto['quantidade'] = int(quantidade or 0)
                    produto['link_download'] = link_download or ""
                    produto['descricao'] = descricao or ""
                    self.salvar_dados()
                    return True
            
            raise ValueError(f"Produto com ID {id} não encontrado")
        except Exception as e:
            logging.error(f"Erro ao editar produto: {e}")
            st.error(f"Erro ao editar produto: {e}")
            return False
    
    def remover_produto(self, id):
        try:
            # Verificar se há vendas associadas
            if any(v['produto_id'] == id for v in self.vendas):
                raise ValueError("Não é possível remover um produto que possui vendas associadas")
            
            produto_encontrado = False
            for i, produto in enumerate(self.produtos):
                if produto['id'] == id:
                    self.produtos.pop(i)
                    produto_encontrado = True
                    break
            
            if not produto_encontrado:
                raise ValueError(f"Produto com ID {id} não encontrado")
            
            self.salvar_dados()
            return True
        except Exception as e:
            logging.error(f"Erro ao remover produto: {e}")
            st.error(f"Erro ao remover produto: {str(e)}")
            return False
    
    def registrar_venda(self, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra=None):
        try:
            if cpf and not validar_cpf(cpf):
                raise ValueError("CPF inválido")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else ""
            
            # Encontrar o produto
            produto = None
            for p in self.produtos:
                if p['id'] == produto_id:
                    produto = p
                    break
            
            if not produto:
                raise ValueError("Produto não encontrado")
            
            nome_produto = produto['nome']
            valor_unitario = float(produto['valor'])
            tipo_produto = produto['tipo']
            
            # Verificar estoque
            if tipo_produto in ['Card', 'Material Físico']:
                estoque_atual = int(produto['quantidade'])
                if quantidade > estoque_atual:
                    raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual}")
                
                # Atualizar estoque
                produto['quantidade'] = estoque_atual - quantidade
            
            # Formatar datas
            data_registro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not data_compra:
                data_compra = datetime.now().strftime("%Y-%m-%d")
            elif isinstance(data_compra, datetime):
                data_compra = data_compra.strftime("%Y-%m-%d")
            
            valor_total = valor_unitario * quantidade
            
            venda = {
                'id': self.next_venda_id,
                'produto_id': produto_id,
                'produto_nome': nome_produto,
                'cliente': cliente,
                'cpf_cliente': cpf_formatado,
                'email_cliente': email,
                'quantidade': quantidade,
                'valor_total': valor_total,
                'forma_pagamento': forma_pagamento,
                'data_registro': data_registro,
                'data_compra': data_compra,
                'status': "Processando"
            }
            
            self.vendas.append(venda)
            self.next_venda_id += 1
            self.salvar_dados()
            return True
        except Exception as e:
            logging.error(f"Erro ao registrar venda: {e}")
            st.error(f"Erro ao registrar venda: {str(e)}")
            return False
    
    def editar_venda(self, id, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra):
        try:
            if cpf and not validar_cpf(cpf):
                raise ValueError("CPF inválido")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else ""
            
            # Encontrar a venda
            venda = None
            for v in self.vendas:
                if v['id'] == id:
                    venda = v
                    break
            
            if not venda:
                raise ValueError(f"Venda com ID {id} não encontrada")
            
            quantidade_atual = int(venda['quantidade'])
            produto_id_atual = venda['produto_id']
            
            # Encontrar o produto
            produto = None
            for p in self.produtos:
                if p['id'] == produto_id:
                    produto = p
                    break
            
            if not produto:
                raise ValueError("Produto não encontrado")
            
            nome_produto = produto['nome']
            valor_unitario = float(produto['valor'])
            tipo_produto = produto['tipo']
            
            # Ajustar estoque
            if tipo_produto in ['Card', 'Material Físico']:
                # Mesmo produto
                if produto_id == produto_id_atual:
                    produto['quantidade'] = int(produto['quantidade']) + quantidade_atual - quantidade
                    if produto['quantidade'] < 0:
                        raise ValueError(f"Estoque insuficiente. Disponível: {int(produto['quantidade']) + quantidade}")
                else:
                    # Produto diferente
                    # Devolver estoque do produto anterior
                    produto_anterior = None
                    for p in self.produtos:
                        if p['id'] == produto_id_atual:
                            produto_anterior = p
                            break
                    
                    if produto_anterior and produto_anterior['tipo'] in ['Card', 'Material Físico']:
                        produto_anterior['quantidade'] = int(produto_anterior['quantidade']) + quantidade_atual
                    
                    # Reduzir estoque do novo produto
                    if quantidade > int(produto['quantidade']):
                        raise ValueError(f"Estoque insuficiente. Disponível: {produto['quantidade']}")
                    
                    produto['quantidade'] = int(produto['quantidade']) - quantidade
            
            # Atualizar dados da venda
            venda['produto_id'] = produto_id
            venda['produto_nome'] = nome_produto
            venda['cliente'] = cliente
            venda['cpf_cliente'] = cpf_formatado
            venda['email_cliente'] = email
            venda['quantidade'] = quantidade
            venda['valor_total'] = valor_unitario * quantidade
            venda['forma_pagamento'] = forma_pagamento
            
            # Formatar data
            if isinstance(data_compra, datetime):
                venda['data_compra'] = data_compra.strftime("%Y-%m-%d")
            else:
                venda['data_compra'] = data_compra
            
            self.salvar_dados()
            return True
        except Exception as e:
            logging.error(f"Erro ao editar venda: {e}")
            st.error(f"Erro ao editar venda: {str(e)}")
            return False
    
    def remover_venda(self, id):
        try:
            venda_encontrada = False
            venda = None
            
            for i, v in enumerate(self.vendas):
                if v['id'] == id:
                    venda = v
                    venda_encontrada = True
                    self.vendas.pop(i)
                    break
            
            if not venda_encontrada:
                raise ValueError(f"Venda com ID {id} não encontrada")
            
            # Devolver ao estoque se for produto físico
            produto_id = venda['produto_id']
            quantidade = int(venda['quantidade'])
            
            for produto in self.produtos:
                if produto['id'] == produto_id and produto['tipo'] in ['Card', 'Material Físico']:
                    produto['quantidade'] = int(produto['quantidade']) + quantidade
                    break
            
            self.salvar_dados()
            return True
        except Exception as e:
            logging.error(f"Erro ao remover venda: {e}")
            st.error(f"Erro ao remover venda: {str(e)}")
            return False
    
    def listar_produtos(self):
        if not self.produtos:
            return pd.DataFrame(columns=[
                'id', 'nome', 'tipo', 'valor', 'quantidade', 
                'link_download', 'descricao', 'data_cadastro'
            ])
        
        return pd.DataFrame(self.produtos)
    
    def listar_vendas(self):
        if not self.vendas:
            return pd.DataFrame(columns=[
                'id', 'produto_id', 'produto_nome', 'cliente', 'cpf_cliente',
                'email_cliente', 'quantidade', 'valor_total', 'forma_pagamento',
                'data_registro', 'data_compra', 'status'
            ])
        
        return pd.DataFrame(self.vendas)
    
    def realizar_backup(self):
        try:
            # Timestamp para o nome do arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"MEDIX_backup_local_{timestamp}.json"
            
            backup_data = {
                'produtos': self.produtos,
                'vendas': self.vendas
            }
            
            with open(backup_filename, 'w') as f:
                json.dump(backup_data, f, indent=2)
            
            return backup_filename
        except Exception as e:
            logging.error(f"Erro ao realizar backup: {e}")
            st.error(f"Erro ao realizar backup: {e}")
            return None

class GestaoVendasGoogleSheets:
    def __init__(self):
        self.creds = None
        self.drive_service = None
        self.sheets_service = None
        self.gc = None
        self.sheets = None
        self.produtos_sheet = None
        self.vendas_sheet = None
        self.autenticado = False
        
        # Tentar autenticar e inicializar
        try:
            logging.info("Iniciando autenticação com Google API")
            self.creds = autenticar_google()
            if self.creds:
                logging.info("Credenciais obtidas com sucesso, configurando serviços")
                self.drive_service = build('drive', 'v3', credentials=self.creds)
                self.sheets_service = build('sheets', 'v4', credentials=self.creds)
                self.gc = gspread.authorize(self.creds)
                
                # Inicializa as planilhas se não existirem
                logging.info("Inicializando planilhas")
                self.sheets = self.inicializar_planilhas()
                if self.sheets:
                    self.produtos_sheet = self.sheets.worksheet("Produtos")
                    self.vendas_sheet = self.sheets.worksheet("Vendas")
                    
                    # Verifica e corrige headers das planilhas se necessário
                    self.verificar_headers()
                    self.autenticado = True
                    logging.info("Autenticação e inicialização das planilhas concluídas com sucesso")
                else:
                    logging.error("Falha ao inicializar planilhas")
            else:
                logging.error("Falha ao obter credenciais - objeto de credenciais é None")
        except Exception as e:
            logging.error(f"Erro na inicialização do Google Sheets: {e}")
    
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
                logging.info(f"Usando planilha existente: {spreadsheet_id}")
            else:
                # Cria uma nova planilha
                spreadsheet = self.gc.create('MEDIX_Sistema')
                logging.info(f"Criando nova planilha: {spreadsheet.id}")
                
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
            except Exception as e:
                logging.warning(f"Erro ao verificar headers de produtos: {e}")
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
            except Exception as e:
                logging.warning(f"Erro ao verificar headers de vendas: {e}")
                self.vendas_sheet.insert_row([
                    "id", "produto_id", "produto_nome", "cliente", "cpf_cliente",
                    "email_cliente", "quantidade", "valor_total", "forma_pagamento",
                    "data_registro", "data_compra", "status"
                ], 1)
                
        except Exception as e:
            logging.error(f"Erro ao verificar headers: {e}")
    
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
            return pd.DataFrame(columns=[
                'id', 'nome', 'tipo', 'valor', 'quantidade', 
                'link_download', 'descricao', 'data_cadastro'
            ])
    
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
            return pd.DataFrame(columns=[
                'id', 'produto_id', 'produto_nome', 'cliente', 'cpf_cliente',
                'email_cliente', 'quantidade', 'valor_total', 'forma_pagamento',
                'data_registro', 'data_compra', 'status'
            ])
    
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
            return None

# Seleciona o gestor de dados apropriado (Google Sheets ou Local)
def get_gestao():
    """Seleciona e inicializa o gestor de dados apropriado (Google Sheets ou Local)."""
    if 'gestao' not in st.session_state:
        # Tenta inicializar a gestão com Google Sheets
        logging.info("Tentando inicializar gestão com Google Sheets")
        gestao_google = GestaoVendasGoogleSheets()
        
        # Verifica se a autenticação foi bem-sucedida
        if gestao_google.autenticado:
            st.session_state.gestao = gestao_google
            st.session_state.usando_google = True
            logging.info("Usando gestão com Google Sheets")
        else:
            # Fallback para gestão local
            st.session_state.gestao = GestaoVendasLocal()
            st.session_state.usando_google = False
            logging.warning("Autenticação com Google falhou. Usando gestão local (fallback)")
            st.warning("Não foi possível conectar ao Google Drive. Usando armazenamento local.")
    
    return st.session_state.gestao

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
            st.session_state.page = "📦_cadastrar_produto"
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
            st.session_state.page = "📦_cadastrar_produto"
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

def configuracoes_ui(gestao):
    st.markdown("## ⚙️ Configurações")
    
    usando_google = st.session_state.get('usando_google', False)
    
    st.subheader("🔐 Acesso ao Google Drive")
    
    if usando_google:
        st.success("✅ Conectado ao Google Drive")
        st.markdown("""
        O sistema está configurado para salvar os dados na seguinte pasta do Google Drive:
        
        **Pasta:** [Gestão Produtos](https://drive.google.com/drive/folders/1HDN1suMspx1um0xbK34waXZ5VGUmseB6)
        
        Todos os dados de produtos e vendas são armazenados em tempo real em planilhas do Google Sheets 
        dentro desta pasta, garantindo acesso fácil e segurança de backup automático.
        """)
    else:
        st.warning("⚠️ Usando armazenamento local (modo offline)")
        st.markdown("""
        O sistema está usando armazenamento local para salvar os dados.
        
        Para ativar a sincronização com o Google Drive, você precisa configurar as credenciais corretas.
        """)
        
        # Opção para criar secretos
        if st.button("📝 Gerar Template de Credenciais"):
            with st.expander("Configuração das Credenciais"):
                st.code("""
[gcp_service_account]
type = "service_account"
project_id = "medix-system"
private_key_id = "YOUR_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\\nYOUR_PRIVATE_KEY_HERE\\n-----END PRIVATE KEY-----\\n"
client_email = "medix-service@medix-system.iam.gserviceaccount.com"
client_id = "1072458931980-mpf2loc5b26l3j5ke1hf0fhghnrfv6i1.apps.googleusercontent.com"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/medix-service%40medix-system.iam.gserviceaccount.com"
                """, language="toml")
                
                st.markdown("""
                1. Copie este template
                2. No Streamlit Cloud, vá para Configurações > Secrets
                3. Cole o template e substitua os valores
                4. Clique em Save
                """)
                
        # ADICIONE ESTA NOVA SEÇÃO PARA SOLUÇÃO DE PROBLEMAS DE AUTENTICAÇÃO
        st.subheader("🔧 Solução de Problemas de Autenticação")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Executar Gerenciador de Credenciais"):
                try:
                    from credentials_manager import get_credentials
                    with st.spinner("Executando gerenciador de credenciais..."):
                        creds = get_credentials()
                        if creds:
                            st.success("✅ Credenciais obtidas com sucesso!")
                            st.info("Reinicie o aplicativo para aplicar as credenciais.")
                        else:
                            st.error("❌ Falha ao obter credenciais.")
                except Exception as e:
                    st.error(f"❌ Erro ao executar gerenciador de credenciais: {e}")
        
        with col2:
            if st.button("🔍 Diagnosticar Problema"):
                with st.spinner("Analisando problema de autenticação..."):
                    try:
                        # Verificar se o arquivo de credenciais existe
                        if os.path.exists('google_credentials.json'):
                            st.success("✅ Arquivo de credenciais encontrado: google_credentials.json")
                            try:
                                with open('google_credentials.json', 'r') as f:
                                    cred_content = json.load(f)
                                    # Verificar campos essenciais
                                    campos_verificados = [
                                        "type" in cred_content,
                                        "project_id" in cred_content,
                                        "private_key_id" in cred_content,
                                        "private_key" in cred_content,
                                        "client_email" in cred_content
                                    ]
                                    
                                    if all(campos_verificados):
                                        st.success("✅ Formato do arquivo de credenciais parece correto")
                                        
                                        # Verificar se a private_key é válida
                                        pk = cred_content.get("private_key", "")
                                        if "YOUR_PRIVATE_KEY_HERE" in pk or "PRIVATE_KEY" not in pk:
                                            st.error("❌ Chave privada parece ser um placeholder. Substitua pela chave real.")
                                        else:
                                            st.success("✅ Formato da chave privada parece correto")
                                    else:
                                        st.error("❌ Arquivo de credenciais está incompleto")
                            except json.JSONDecodeError:
                                st.error("❌ Arquivo de credenciais não é um JSON válido")
                            except Exception as e:
                                st.error(f"❌ Erro ao analisar arquivo de credenciais: {e}")
                        else:
                            st.warning("⚠️ Arquivo google_credentials.json não encontrado")
                            
                            # Verificar secrets do Streamlit
                            if 'gcp_service_account' in st.secrets:
                                st.success("✅ Credenciais encontradas em st.secrets")
                                
                                # Verificar campos em st.secrets
                                secrets_creds = st.secrets["gcp_service_account"]
                                campos_verificados = [
                                    "type" in secrets_creds,
                                    "project_id" in secrets_creds,
                                    "private_key_id" in secrets_creds,
                                    "private_key" in secrets_creds,
                                    "client_email" in secrets_creds
                                ]
                                
                                if all(campos_verificados):
                                    st.success("✅ Formato das credenciais em st.secrets parece correto")
                                    
                                    # Verificar se a private_key é válida
                                    pk = secrets_creds.get("private_key", "")
                                    if "YOUR_PRIVATE_KEY_HERE" in pk or "PRIVATE_KEY" not in pk:
                                        st.error("❌ Chave privada parece ser um placeholder. Substitua pela chave real.")
                                    else:
                                        st.success("✅ Formato da chave privada parece correto")
                                else:
                                    st.error("❌ Credenciais em st.secrets estão incompletas")
                            else:
                                st.error("❌ Credenciais não encontradas em nenhum lugar conhecido")
                                st.info("Você precisa adicionar suas credenciais do Google em um dos seguintes locais:")
                                st.markdown("""
                                1. Arquivo `google_credentials.json` na raiz do projeto
                                2. Em secrets do Streamlit (`st.secrets["gcp_service_account"]`)
                                3. Na variável de ambiente GOOGLE_APPLICATION_CREDENTIALS
                                """)
                    except Exception as e:
                        st.error(f"❌ Erro durante o diagnóstico: {e}")
    
    # Informações do Sistema
    st.subheader("ℹ️ Informações do Sistema")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Versão:** 1.0.0")
        st.markdown("**Última atualização:** 25/03/2025")
        st.markdown("**Desenvolvido por:** MEDIX Team")
    
    with col2:
        st.markdown(f"**Status:** {'Conectado ao Google Drive' if usando_google else 'Modo Offline'}")
        st.markdown(f"**Armazenamento:** {'Google Sheets' if usando_google else 'Arquivo Local'}")
        st.markdown("**Suporte:** suporte@medix.com")
    
    # Botão para testar conexão
    if st.button("🔄 Testar Conexão com Google Drive"):
        with st.spinner("Testando conexão..."):
            try:
                # Criar uma instância temporária para testar
                gestao_test = GestaoVendasGoogleSheets()
                if gestao_test.autenticado:
                    st.success("✅ Conexão bem sucedida! O sistema está conectado ao Google Drive.")
                    # Atualizar a sessão
                    st.session_state.gestao = gestao_test
                    st.session_state.usando_google = True
                    st.rerun()
                else:
                    st.error("❌ Falha na conexão. Verifique as credenciais.")
            except Exception as e:
                st.error(f"❌ Falha na conexão: {e}")

def dashboard_ui(gestao):
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
    if not vendas.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Vendas Recentes")
            
            # Convertendo data para datetime se necessário
            if 'data_compra' in vendas.columns:
                try:
                    vendas['data_compra'] = pd.to_datetime(vendas['data_compra'])
                    
                    # Últimos 30 dias
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
                except Exception as e:
                    st.error(f"Erro ao processar datas: {e}")
                    st.info("Não foi possível gerar o gráfico de vendas recentes.")
            else:
                st.info("Dados de data não disponíveis.")
        
        with col2:
            st.subheader("🔝 Produtos Mais Vendidos")
            try:
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
            except Exception as e:
                st.error(f"Erro ao processar dados de produtos: {e}")
                st.info("Não foi possível gerar o gráfico de produtos mais vendidos.")
    
    # Alertas de estoque
    st.subheader("⚠️ Alertas de Estoque")
    if not produtos.empty:
        try:
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
        except Exception as e:
            st.error(f"Erro ao processar alertas de estoque: {e}")
            st.info("Não foi possível verificar alertas de estoque.")
    else:
        st.info("Não há produtos cadastrados.")

def menu_principal():
    # Usar option_menu se disponível, caso contrário, usar um seletor padrão
    if option_menu_available:
        with st.sidebar:
            menu = option_menu(
                "Menu Principal",
                [
                    "📊 Dashboard",
                    "📦 Cadastrar Produto", 
                    "💳 Registrar Venda", 
                    "📋 Listar Produtos", 
                    "📊 Listar Vendas",
                    "⚙️ Configurações"
                ],
                icons=[
                    "house", 
                    "box-seam", 
                    "credit-card", 
                    "list-check", 
                    "graph-up", 
                    "gear"
                ],
                menu_icon="cast",
                default_index=0,
            )
        return menu
    else:
        with st.sidebar:
            st.title("MEDIX - Menu")
            menu = st.radio(
                "Selecione uma opção:",
                [
                    "📊 Dashboard",
                    "📦 Cadastrar Produto", 
                    "💳 Registrar Venda", 
                    "📋 Listar Produtos", 
                    "📊 Listar Vendas",
                    "⚙️ Configurações"
                ]
            )
        return menu

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
    
    /* Footer */
    footer {
        visibility: hidden;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Logo e título no sidebar
    with st.sidebar:
        st.title("🩺 MEDIX")
        st.caption("Sistema de Gestão de Produtos e Vendas")
        st.markdown("---")
    
    # Inicializar a gestão (Google ou Local)
    gestao = get_gestao()
    
    # Menu principal
    menu = menu_principal()
    
    # Conteúdo principal com base no menu selecionado
    if menu == "📊 Dashboard":
        dashboard_ui(gestao)
    
    elif menu == "📦 Cadastrar Produto":
        cadastrar_produto_ui(gestao)
    
    elif menu == "💳 Registrar Venda":
        registrar_venda_ui(gestao)
    
    elif menu == "📋 Listar Produtos":
        listar_produtos_ui(gestao)
    
    elif menu == "📊 Listar Vendas":
        st.title("Lista de Vendas")
        st.info("Esta funcionalidade está simplificada para debug. A implementação completa será adicionada em breve.")
        
        vendas = gestao.listar_vendas()
        if not vendas.empty:
            st.dataframe(vendas)
        else:
            st.warning("Não há vendas registradas.")
    
    elif menu == "⚙️ Configurações":
        configuracoes_ui(gestao)
    
    # Rodapé
    with st.sidebar:
        st.markdown("---")
        storage_type = "Google Drive" if st.session_state.get('usando_google', False) else "Local"
        st.caption(f"Armazenamento: {storage_type}")
        st.caption("© 2025 MEDIX Health Systems")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Erro inesperado: {e}")
        logging.error(f"Erro inesperado na aplicação: {e}")
        
        # Fallback para uma interface simplificada
        st.title("MEDIX - Modo de Emergência")
        st.warning("O sistema encontrou um erro e está funcionando em modo limitado.")
        
        basic_option = st.selectbox(
            "O que você gostaria de fazer?",
            ["Ver informações", "Verificar configurações"]
        )
        
        if basic_option == "Ver informações":
            st.info("MEDIX - Sistema de Gestão de Produtos e Vendas")
            st.markdown("""
            Para resolver este problema:
            1. Verifique as credenciais do Google
            2. Reinstale as dependências necessárias
            3. Reinicie a aplicação
            """)
        
        elif basic_option == "Verificar configurações":
            st.subheader("Diagnóstico do Sistema")
            
            st.markdown("**Verificando importações:**")
            try:
                import gspread
                st.success("✅ gspread importado com sucesso")
            except ImportError:
                st.error("❌ gspread não encontrado")
            
            try:
                from google.oauth2.service_account import Credentials
                st.success("✅ google.oauth2 importado com sucesso")
            except ImportError:
                st.error("❌ google.oauth2 não encontrado")
            
            try:
                from streamlit_option_menu import option_menu
                st.success("✅ streamlit_option_menu importado com sucesso")
            except ImportError:
                st.error("❌ streamlit_option_menu não encontrado")
