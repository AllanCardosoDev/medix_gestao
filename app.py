import streamlit as st
import pandas as pd
from datetime import datetime
import re
import io
import openpyxl
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.oauth2 import service_account
import gspread

# Configuração das credenciais do Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'path/to/your/service_account_file.json'  # Você precisa criar este arquivo

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# ID da sua planilha do Google Sheets
SPREADSHEET_ID = 'your_spreadsheet_id_here'

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
        self.sheet = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
        self.produtos_sheet = self.sheet.worksheet("Produtos")
        self.vendas_sheet = self.sheet.worksheet("Vendas")

    def cadastrar_produto(self, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        try:
            produtos = self.produtos_sheet.get_all_records()
            if any(p['nome'] == nome for p in produtos):
                raise ValueError("Já existe um produto com este nome")

            novo_id = len(produtos) + 1
            self.produtos_sheet.append_row([
                novo_id, nome, tipo, valor, quantidade, link_download, descricao
            ])
            return True
        except Exception as e:
            st.error(f"Erro ao cadastrar produto: {e}")
            return False

    def editar_produto(self, id, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        try:
            produtos = self.produtos_sheet.get_all_records()
            if any(p['nome'] == nome and p['id'] != id for p in produtos):
                raise ValueError("Já existe outro produto com este nome")

            row = self.produtos_sheet.find(str(id)).row
            self.produtos_sheet.update(f'A{row}:G{row}', [[
                id, nome, tipo, valor, quantidade, link_download, descricao
            ]])
            return True
        except Exception as e:
            st.error(f"Erro ao editar produto: {e}")
            return False

    def remover_produto(self, id):
        try:
            row = self.produtos_sheet.find(str(id)).row
            self.produtos_sheet.delete_rows(row)
            return True
        except Exception as e:
            st.error(f"Erro ao remover produto: {e}")
            return False

    def registrar_venda(self, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra=None):
        try:
            if cpf and not validar_cpf(cpf):
                st.warning("CPF inválido. A venda será registrada, mas verifique o CPF.")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else None
            
            produtos = self.produtos_sheet.get_all_records()
            produto = next((p for p in produtos if p['id'] == produto_id), None)
            
            if not produto:
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

            vendas = self.vendas_sheet.get_all_records()
            novo_id = len(vendas) + 1
            
            self.vendas_sheet.append_row([
                novo_id, produto_id, cliente, cpf_formatado, email, quantidade,
                valor_total, forma_pagamento, data_registro, data_compra, "Processando"
            ])
            
            if tipo_produto in ['Card', 'Físico']:
                row = self.produtos_sheet.find(str(produto_id)).row
                novo_estoque = estoque_atual - quantidade
                self.produtos_sheet.update_cell(row, 5, novo_estoque)
            
            return True
        except Exception as e:
            st.error(f"Erro ao registrar venda: {e}")
            return False

    def editar_venda(self, id, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra):
        try:
            if cpf and not validar_cpf(cpf):
                st.warning("CPF inválido. A venda será atualizada, mas verifique o CPF.")
            
            cpf_formatado = formatar_cpf(cpf) if cpf else None
            
            vendas = self.vendas_sheet.get_all_records()
            venda_atual = next((v for v in vendas if v['id'] == id), None)
            if not venda_atual:
                raise ValueError("Venda não encontrada")
            
            produtos = self.produtos_sheet.get_all_records()
            produto = next((p for p in produtos if p['id'] == produto_id), None)
            if not produto:
                raise ValueError("Produto não encontrado")
            
            valor_unitario = produto['valor']
            tipo_produto = produto['tipo']
            estoque_atual = produto['quantidade']
            
            if tipo_produto in ['Card', 'Físico']:
                estoque_ajustado = estoque_atual + venda_atual['quantidade'] - quantidade
                if estoque_ajustado < 0:
                    raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual}")
                
                row = self.produtos_sheet.find(str(produto_id)).row
                self.produtos_sheet.update_cell(row, 5, estoque_ajustado)
            
            valor_total = valor_unitario * quantidade
            
            row = self.vendas_sheet.find(str(id)).row
            self.vendas_sheet.update(f'A{row}:K{row}', [[
                id, produto_id, cliente, cpf_formatado, email, quantidade,
                valor_total, forma_pagamento, venda_atual['data_registro'], data_compra, venda_atual['status']
            ]])
            
            return True
        except Exception as e:
            st.error(f"Erro ao editar venda: {e}")
            return False

    def remover_venda(self, id):
        try:
            vendas = self.vendas_sheet.get_all_records()
            venda = next((v for v in vendas if v['id'] == id), None)
            if not venda:
                raise ValueError("Venda não encontrada")
            
            produtos = self.produtos_sheet.get_all_records()
            produto = next((p for p in produtos if p['id'] == venda['produto_id']), None)
            
            if produto['tipo'] in ['Card', 'Físico']:
                row = self.produtos_sheet.find(str(venda['produto_id'])).row
                novo_estoque = produto['quantidade'] + venda['quantidade']
                self.produtos_sheet.update_cell(row, 5, novo_estoque)
            
            row = self.vendas_sheet.find(str(id)).row
            self.vendas_sheet.delete_rows(row)
            return True
        except Exception as e:
            st.error(f"Erro ao remover venda: {e}")
            return False

    def listar_produtos(self):
        return pd.DataFrame(self.produtos_sheet.get_all_records())

    def listar_vendas(self):
        vendas = pd.DataFrame(self.vendas_sheet.get_all_records())
        produtos = pd.DataFrame(self.produtos_sheet.get_all_records())
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
                produto_info = produtos[produtos['nome'] == produto_selecionado]
                tipo_produto = produto_info['tipo'].values[0]
                estoque_max = produto_info['quantidade'].values[0] or 1
                
                quantidade = st.number_input(
                    "Quantidade", 
                    min_value=1, 
                    max_value=int(estoque_max) if tipo_produto in ['Card', 'Físico'] else 1, 
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
                    gestao.registrar_venda(
                        produto_id, 
                        cliente, 
                        cpf,
                        email, 
                        quantidade, 
                        forma_pagamento,
                        data_compra
                    )
                    st.success("Venda registrada com sucesso!")
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
                data_compra = st.date_input("Data da Compra", value=datetime.strptime(venda['data_compra'], '%Y-%m-%d').date() if venda['data_compra'] else datetime.now())
                
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
    .sidebar .sidebar-content .stRadio > div {
        background-color: #ffffff;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .sidebar .sidebar-content .stRadio > div:hover {
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

    menu = st.sidebar.radio("Navegação", [
        "📦 Cadastrar Produto", 
        "💳 Registrar Venda", 
        "📋 Listar Produtos", 
        "📊 Listar Vendas",
        "📤 Exportar Dados",
        "👀 Visualizar Planilha"
    ])

    if menu == "📦 Cadastrar Produto":
        cadastrar_produto_ui(gestao)
    elif menu == "💳 Registrar Venda":
        registrar_venda_ui(gestao)
    elif menu == "📋 Listar Produtos":
        listar_produtos_ui(gestao)
    elif menu == "📊 Listar Vendas":
        listar_vendas_ui(gestao)
    elif menu == "📤 Exportar Dados":
        exportar_dados_ui(gestao)
    elif menu == "👀 Visualizar Planilha":
        visualizar_planilha_ui(gestao)

if __name__ == "__main__":
    main()
