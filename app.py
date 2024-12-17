import streamlit as st
import pandas as pd
from datetime import datetime
import re
import io
import openpyxl
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe

# Configuração das credenciais do Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
CLIENT_ID = '1072458931980-mpf2loc5b26l3j5ke1hf0fhghnrfv6i1.apps.googleusercontent.com'
CLIENT_SECRET = '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'

# Nome da planilha
SPREADSHEET_NAME = "MEDIX_Gestao_Vendas"

def get_credentials():
    creds = None
    if 'token' in st.session_state:
        creds = Credentials.from_authorized_user_info(st.session_state['token'], SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                SCOPES
            )
            creds = flow.run_local_server(port=0)
        st.session_state['token'] = creds.to_json()
    return creds

def validar_cpf(cpf):
    if not cpf or cpf == '00000000000':
        return True
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11:
        return False
    if len(set(cpf)) == 1:
        return False
    def calcular_digito_verificador(cpf, peso):
        soma = sum(int(d) * p for d, p in zip(cpf, peso))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto
    peso1 = list(range(10, 1, -1))
    peso2 = list(range(11, 1, -1))
    digito1 = calcular_digito_verificador(cpf[:9], peso1)
    digito2 = calcular_digito_verificador(cpf[:9] + str(digito1), peso2)
    return cpf[-2:] == f"{digito1}{digito2}"

def formatar_cpf(cpf):
    if not cpf or cpf == '00000000000':
        return cpf
    cpf = re.sub(r'\D', '', cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

class GestaoVendas:
    def __init__(self):
        creds = get_credentials()
        self.client = gspread.authorize(creds)
        self.sheet = self.get_or_create_spreadsheet()
        self.produtos_sheet = self.get_or_create_worksheet("Produtos")
        self.vendas_sheet = self.get_or_create_worksheet("Vendas")

    def get_or_create_spreadsheet(self):
        try:
            return self.client.open(SPREADSHEET_NAME)
        except gspread.SpreadsheetNotFound:
            return self.client.create(SPREADSHEET_NAME)

    def get_or_create_worksheet(self, name):
        try:
            return self.sheet.worksheet(name)
        except gspread.WorksheetNotFound:
            return self.sheet.add_worksheet(title=name, rows="1000", cols="20")

    def cadastrar_produto(self, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        try:
            produtos = self.listar_produtos()
            if not produtos.empty and produtos['nome'].str.lower().eq(nome.lower()).any():
                raise ValueError("Já existe um produto com este nome")

            novo_id = 1 if produtos.empty else produtos['id'].max() + 1
            novo_produto = pd.DataFrame({
                'id': [novo_id],
                'nome': [nome],
                'tipo': [tipo],
                'valor': [valor],
                'quantidade': [quantidade],
                'link_download': [link_download],
                'descricao': [descricao]
            })
            produtos = pd.concat([produtos, novo_produto], ignore_index=True)
            set_with_dataframe(self.produtos_sheet, produtos)
            return True
        except Exception as e:
            st.error(f"Erro ao cadastrar produto: {e}")
            return False

    def editar_produto(self, id, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        try:
            produtos = self.listar_produtos()
            if produtos[produtos['id'] != id]['nome'].str.lower().eq(nome.lower()).any():
                raise ValueError("Já existe outro produto com este nome")

            produtos.loc[produtos['id'] == id, ['nome', 'tipo', 'valor', 'quantidade', 'link_download', 'descricao']] = [
                nome, tipo, valor, quantidade, link_download, descricao
            ]
            set_with_dataframe(self.produtos_sheet, produtos)
            return True
        except Exception as e:
            st.error(f"Erro ao editar produto: {e}")
            return False

    def remover_produto(self, id):
        try:
            produtos = self.listar_produtos()
            produtos = produtos[produtos['id'] != id]
            set_with_dataframe(self.produtos_sheet, produtos)
            return True
        except Exception as e:
            st.error(f"Erro ao remover produto: {e}")
            return False

    def registrar_venda(self, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra=None):
        try:
            if cpf and not validar_cpf(cpf):
                st.warning("CPF inválido. A venda será registrada, mas verifique o CPF.")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else None
            
            produtos = self.listar_produtos()
            produto = produtos[produtos['id'] == produto_id].iloc[0]
            
            if produto.empty:
                raise ValueError("Produto não encontrado")
            
            valor_unitario = produto['valor']
            tipo_produto = produto['tipo']
            estoque_atual = produto['quantidade']
            
            if tipo_produto in ['Card', 'Físico'] and (estoque_atual is None or quantidade > estoque_atual):
                raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual or 0}")
            
            valor_total = valor_unitario * quantidade
            data_registro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if not data_compra:
                data_compra = datetime.now().date().strftime("%Y-%m-%d")

            vendas = self.listar_vendas()
            novo_id = 1 if vendas.empty else vendas['id'].max() + 1
            
            nova_venda = pd.DataFrame({
                'id': [novo_id],
                'produto_id': [produto_id],
                'cliente': [cliente],
                'cpf_cliente': [cpf_formatado],
                'email_cliente': [email],
                'quantidade': [quantidade],
                'valor_total': [valor_total],
                'forma_pagamento': [forma_pagamento],
                'data_registro': [data_registro],
                'data_compra': [data_compra],
                'status': ["Processando"]
            })
            
            vendas = pd.concat([vendas, nova_venda], ignore_index=True)
            set_with_dataframe(self.vendas_sheet, vendas)
            
            if tipo_produto in ['Card', 'Físico']:
                produtos.loc[produtos['id'] == produto_id, 'quantidade'] -= quantidade
                set_with_dataframe(self.produtos_sheet, produtos)
            
            return True
        except Exception as e:
            st.error(f"Erro ao registrar venda: {e}")
            return False

    def editar_venda(self, id, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra):
        try:
            if cpf and not validar_cpf(cpf):
                st.warning("CPF inválido. A venda será atualizada, mas verifique o CPF.")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else None
            
            vendas = self.listar_vendas()
            venda_atual = vendas[vendas['id'] == id].iloc[0]
            if venda_atual.empty:
                raise ValueError("Venda não encontrada")
            
            produtos = self.listar_produtos()
            produto = produtos[produtos['id'] == produto_id].iloc[0]
            if produto.empty:
                raise ValueError("Produto não encontrado")
            
            valor_unitario = produto['valor']
            tipo_produto = produto['tipo']
            estoque_atual = produto['quantidade']
            
            if tipo_produto in ['Card', 'Físico']:
                estoque_ajustado = estoque_atual + venda_atual['quantidade'] - quantidade
                if estoque_ajustado < 0:
                    raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual}")
                
                produtos.loc[produtos['id'] == produto_id, 'quantidade'] = estoque_ajustado
                set_with_dataframe(self.produtos_sheet, produtos)
            
            valor_total = valor_unitario * quantidade
            
            vendas.loc[vendas['id'] == id, [
                'produto_id', 'cliente', 'cpf_cliente', 'email_cliente', 'quantidade',
                'valor_total', 'forma_pagamento', 'data_compra'
            ]] = [
                produto_id, cliente, cpf_formatado, email, quantidade,
                valor_total, forma_pagamento, data_compra
            ]
            
            set_with_dataframe(self.vendas_sheet, vendas)
            
            return True
        except Exception as e:
            st.error(f"Erro ao editar venda: {e}")
            return False

    def remover_venda(self, id):
        try:
            vendas = self.listar_vendas()
            venda = vendas[vendas['id'] == id].iloc[0]
            if venda.empty:
                raise ValueError("Venda não encontrada")
            
            produtos = self.listar_produtos()
            produto = produtos[produtos['id'] == venda['produto_id']].iloc[0]
            
            if produto['tipo'] in ['Card', 'Físico']:
                produtos.loc[produtos['id'] == venda['produto_id'], 'quantidade'] += venda['quantidade']
                set_with_dataframe(self.produtos_sheet, produtos)
            
            vendas = vendas[vendas['id'] != id]
            set_with_dataframe(self.vendas_sheet, vendas)
            return True
        except Exception as e:
            st.error(f"Erro ao remover venda: {e}")
            return False

    def listar_produtos(self):
        return get_as_dataframe(self.produtos_sheet)

    def listar_vendas(self):
        vendas = get_as_dataframe(self.vendas_sheet)
        produtos = get_as_dataframe(self.produtos_sheet)
        return vendas.merge(produtos[['id', 'nome', 'tipo']], left_on='produto_id', right_on='id', suffixes=('', '_produto'))

    def exportar_excel(self, tipo='vendas'):
        if tipo == 'vendas':
            df = self.listar_vendas()
        else:
            df = self.listar_produtos()
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=tipo.capitalize())
        
        return output.getvalue()

def cadastrar_produto_ui(gestao):
    st.subheader("📦 Cadastro de Novo Produto")
    
    with st.form("cadastro_produto"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome do Produto")
            valor = st.number_input("Valor", min_value=0.0, step=0.01)
            
        with col2:
            tipo = st.selectbox("Tipo de Produto", [
                "PDF", 
                "Card", 
                "Físico", 
                "Serviço Digital"
            ])
            quantidade = st.number_input("Quantidade (opcional)", min_value=0, step=1)
        
        link_download = st.text_input("Link de Download (para produtos digitais)")
        descricao = st.text_area("Descrição do Produto")
        
        submit = st.form_submit_button("Cadastrar Produto")
        
        if submit:
            if not nome:
                st.error("Nome do produto é obrigatório")
            else:
                sucesso = gestao.cadastrar_produto(
                    nome, 
                    tipo, 
                    valor, 
                    quantidade if tipo in ['Card', 'Físico'] else None, 
                    link_download, 
                    descricao
                )
                if sucesso:
                    st.success("Produto cadastrado com sucesso!")
                else:
                    st.error("Erro ao cadastrar produto")

def registrar_venda_ui(gestao):
    st.subheader("💳 Registro de Nova Venda")
    
    produtos = gestao.listar_produtos()
    
    if produtos.empty:
        st.warning("Não há produtos cadastrados. Cadastre um produto primeiro.")
    else:
        with st.form("registro_venda"):
            col1, col2 = st.columns(2)
            with col1:
                opcoes_produtos = dict(zip(produtos['nome'], produtos['id']))
                produto_selecionado = st.selectbox(
                    "Selecione o Produto", 
                    list(opcoes_produtos.keys())
                )
                
                cliente = st.text_input("Nome do Cliente")
                cpf = st.text_input("CPF do Cliente (opcional)", help="Digite apenas números ou deixe em branco")
                email = st.text_input("Email do Cliente")
            
            with col2:
                produto_info = produtos[produtos['nome'] == produto_selecionado].iloc[0]
                tipo_produto = produto_info['tipo']
                estoque_max = produto_info['quantidade'] or 1
                
                quantidade = st.number_input(
                    "Quantidade", 
                    min_value=1, 
                    max_value=int(estoque_max) if tipo_produto in ['Card', 'Físico'] else None, 
                    step=1
                )
                
                forma_pagamento = st.selectbox("Forma de Pagamento", [
                    "Pix", 
                    "Cartão de Crédito", 
                    "Cartão de Débito", 
                    "Transferência Bancária"
                ])
                
                data_compra = st.date_input("Data da Compra", datetime.now())
            
            submit_venda = st.form_submit_button("Registrar Venda")
            
            if submit_venda:
                try:
                    if not cliente:
                        st.error("Nome do cliente é obrigatório")
                        st.stop()
                    
                    produto_id = opcoes_produtos[produto_selecionado]
                    sucesso = gestao.registrar_venda(
                        produto_id, 
                        cliente, 
                        cpf,
                        email, 
                        quantidade, 
                        forma_pagamento,
                        data_compra
                    )
                    if sucesso:
                        st.success("Venda registrada com sucesso!")
                    else:
                        st.error("Erro ao registrar venda")
                except ValueError as e:
                    st.error(str(e))

def listar_produtos_ui(gestao):
    st.subheader("📋 Lista de Produtos")
    produtos = gestao.listar_produtos()
    if not produtos.empty:
        for index, row in produtos.iterrows():
            with st.expander(f"{row['nome']} - {row['tipo']}"):
                col1, col2, col3 = st.columns([3,1,1])
                with col1:
                    st.write(f"**Descrição:** {row['descricao']}")
                    st.write(f"**Valor:** R$ {row['valor']:.2f}")
                    if row['tipo'] in ['Card', 'Físico']:
                        st.write(f"**Quantidade em estoque:** {row['quantidade']}")
                    if row['tipo'] in ['PDF', 'Serviço Digital']:
                        st.write(f"**Link de download:** {row['link_download']}")
                with col2:
                    if st.button(f"Editar {row['nome']}", key=f"edit_{row['id']}"):
                        st.session_state.editing_product = row['id']
                with col3:
                    if st.button(f"Remover {row['nome']}", key=f"remove_{row['id']}"):
                        if gestao.remover_produto(row['id']):
                            st.success(f"Produto {row['nome']} removido com sucesso!")
                            st.rerun()
                        else:
                            st.error(f"Erro ao remover o produto {row['nome']}")
        
        if 'editing_product' in st.session_state:
            produto = produtos[produtos['id'] == st.session_state.editing_product].iloc[0]
            st.subheader(f"Editando: {produto['nome']}")
            with st.form(key=f"edit_product_{produto['id']}"):
                nome = st.text_input("Nome do Produto", value=produto['nome'])
                tipo = st.selectbox("Tipo de Produto", ["PDF", "Card", "Físico", "Serviço Digital"], index=["PDF", "Card", "Físico", "Serviço Digital"].index(produto['tipo']))
                valor = st.number_input("Valor", min_value=0.0, value=float(produto['valor']), step=0.01)
                
                quantidade_valor = produto['quantidade'] if pd.notna(produto['quantidade']) else 0
                quantidade = st.number_input("Quantidade", min_value=0, value=int(quantidade_valor), step=1)
                
                link_download = st.text_input("Link de Download", value=produto['link_download'] if pd.notna(produto['link_download']) else "")
                descricao = st.text_area("Descrição", value=produto['descricao'] if pd.notna(produto['descricao']) else "")
                
                submit_edit = st.form_submit_button("Atualizar Produto")
                
                if submit_edit:
                    if gestao.editar_produto(st.session_state.editing_product, nome, tipo, valor, quantidade, link_download, descricao):
                        st.success("Produto atualizado com sucesso!")
                        del st.session_state.editing_product
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar o produto")
    else:
        st.warning("Nenhum produto cadastrado")

def listar_vendas_ui(gestao):
    st.subheader("📊 Lista de Vendas")
    vendas = gestao.listar_vendas()
    if not vendas.empty:
        for index, row in vendas.iterrows():
            with st.expander(f"Venda {row['id']} - {row['cliente']}"):
                col1, col2, col3 = st.columns([3,1,1])
                with col1:
                    st.write(f"**Produto:** {row['nome']}")
                    st.write(f"**Quantidade:** {row['quantidade']}")
                    st.write(f"**Valor Total:** R$ {row['valor_total']:.2f}")
                    st.write(f"**Data da Compra:** {row['data_compra']}")
                    st.write(f"**Forma de Pagamento:** {row['forma_pagamento']}")
                    st.write(f"**CPF:** {row['cpf_cliente'] or 'Não informado'}")
                    st.write(f"**Email:** {row['email_cliente'] or 'Não informado'}")
                with col2:
                    if st.button(f"Editar Venda {row['id']}", key=f"edit_venda_{row['id']}"):
                        st.session_state.editing_sale = row['id']
                with col3:
                    if st.button(f"Remover Venda {row['id']}", key=f"remove_venda_{row['id']}"):
                        if gestao.remover_venda(row['id']):
                            st.success(f"Venda {row['id']} removida com sucesso!")
                            st.rerun()
                        else:
                            st.error(f"Erro ao remover a venda {row['id']}")
        
        if 'editing_sale' in st.session_state:
            venda = vendas[vendas['id'] == st.session_state.editing_sale].iloc[0]
            st.subheader(f"Editando Venda: {venda['id']}")
            with st.form(key=f"edit_sale_{venda['id']}"):
                produtos = gestao.listar_produtos()
                opcoes_produtos = dict(zip(produtos['nome'], produtos['id']))
                produto_selecionado = st.selectbox("Produto", list(opcoes_produtos.keys()), index=list(opcoes_produtos.keys()).index(venda['nome']))
                cliente = st.text_input("Nome do Cliente", value=venda['cliente'])
                cpf = st.text_input("CPF do Cliente (opcional)", value=venda['cpf_cliente'] if venda['cpf_cliente'] else "")
                email = st.text_input("Email do Cliente", value=venda['email_cliente'] if venda['email_cliente'] else "")
                quantidade = st.number_input("Quantidade", min_value=1, value=int(venda['quantidade']))
                forma_pagamento = st.selectbox("Forma de Pagamento", ["Pix", "Cartão de Crédito", "Cartão de Débito", "Transferência Bancária"], index=["Pix", "Cartão de Crédito", "Cartão de Débito", "Transferência Bancária"].index(venda['forma_pagamento']))
                data_compra = st.date_input("Data da Compra", value=pd.to_datetime(venda['data_compra']).date() if venda['data_compra'] else datetime.now())
                
                submit_edit = st.form_submit_button("Atualizar Venda")
                
                if submit_edit:
                    if gestao.editar_venda(st.session_state.editing_sale, opcoes_produtos[produto_selecionado], cliente, cpf, email, quantidade, forma_pagamento, data_compra):
                        st.success("Venda atualizada com sucesso!")
                        del st.session_state.editing_sale
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar a venda")
    else:
        st.warning("Nenhuma venda registrada")

def exportar_dados_ui(gestao):
    st.subheader("📤 Exportar Dados")
    tipo = st.selectbox("Tipo de Exportação", ["vendas", "produtos"])
    if st.button("Exportar Excel"):
        try:
            excel_data = gestao.exportar_excel(tipo)
            st.success(f"Arquivo gerado com sucesso!")
            st.download_button(
                label="Baixar Arquivo Excel",
                data=excel_data,
                file_name=f'MEDIX_{tipo}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        except Exception as e:
            st.error(f"Erro ao exportar: {e}")

def visualizar_planilha_ui(gestao):
    st.subheader("👀 Visualizar Planilha")
    tipo = st.radio("Selecione o tipo de dados", ["Produtos", "Vendas"])
    
    if tipo == "Produtos":
        df = gestao.listar_produtos()
        st.write("### Planilha de Produtos")
    else:
        df = gestao.listar_vendas()
        st.write("### Planilha de Vendas")
    
    st.dataframe(df)

def main():
    st.set_page_config(
        page_title="MEDIX - Gestão de Produtos",
        page_icon="🩺",
        layout="wide"
    )
    
    st.markdown("""
    <style>
    .sidebar .sidebar-content {
        background-color: #f0f2f6;
    }
    .sidebar .sidebar-content .stSelectbox {
        background-color: #ffffff;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .sidebar .sidebar-content .stSelectbox:hover {
        background-color: #e6e9ef;
    }
    .big-font {
        font-size: 20px !important;
        color: #0083B8;
    }
    .highlight {
        background-color: #F0F2F6;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

    try:
        logo_path = "logo_medix.jpeg"
        col1, col2 = st.columns([1, 4])
        with col1:
            st.image(logo_path, width=150)
    except FileNotFoundError:
        st.warning("Logo não encontrado. Adicione um arquivo logo_medix.jpeg")

    st.title("MEDIX - Gestão de Produtos e Vendas")

    if 'gestao' not in st.session_state:
        st.session_state.gestao = GestaoVendas()
    
    gestao = st.session_state.gestao

    menu_options = {
        "📦 Cadastrar Produto": cadastrar_produto_ui,
        "💳 Registrar Venda": registrar_venda_ui,
        "📋 Listar Produtos": listar_produtos_ui,
        "📊 Listar Vendas": listar_vendas_ui,
        "📤 Exportar Dados": exportar_dados_ui,
        "👀 Visualizar Planilha": visualizar_planilha_ui
    }

    menu = st.sidebar.selectbox("Navegação", list(menu_options.keys()))

    menu_options[menu](gestao)

if __name__ == "__main__":
    main()
