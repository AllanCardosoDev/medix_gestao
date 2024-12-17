import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import re
import os
import shutil

# Funções auxiliares
def validar_cpf(cpf):
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
    cpf = re.sub(r'\D', '', cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

class GestaoVendas:
    def __init__(self, db_name='medix_vendas.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.criar_tabelas()

    def criar_tabelas(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY,
                nome TEXT NOT NULL UNIQUE,
                tipo TEXT NOT NULL,
                valor REAL NOT NULL,
                quantidade INTEGER,
                link_download TEXT,
                descricao TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY,
                produto_id INTEGER,
                cliente TEXT NOT NULL,
                cpf_cliente TEXT NOT NULL,
                email_cliente TEXT,
                quantidade INTEGER,
                valor_total REAL,
                forma_pagamento TEXT,
                data_compra DATE,
                FOREIGN KEY(produto_id) REFERENCES produtos(id)
            )
        ''')
        self.conn.commit()

    def listar_produtos(self):
        return pd.read_sql_query("SELECT * FROM produtos", self.conn)

    def listar_vendas(self):
        return pd.read_sql_query("""
            SELECT v.id, p.nome as produto, v.cliente, v.cpf_cliente, v.quantidade, 
                   v.valor_total, v.forma_pagamento, v.data_compra 
            FROM vendas v JOIN produtos p ON v.produto_id = p.id
        """, self.conn)

    def cadastrar_produto(self, nome, tipo, valor, quantidade, link_download, descricao):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO produtos (nome, tipo, valor, quantidade, link_download, descricao)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (nome, tipo, valor, quantidade, link_download, descricao))
        self.conn.commit()

    def registrar_venda(self, produto_id, cliente, cpf, email, quantidade, forma_pagamento):
        cursor = self.conn.cursor()
        cursor.execute('SELECT valor FROM produtos WHERE id = ?', (produto_id,))
        valor_unitario = cursor.fetchone()[0]
        valor_total = valor_unitario * quantidade
        cursor.execute('''
            INSERT INTO vendas (produto_id, cliente, cpf_cliente, email_cliente, quantidade, 
                                valor_total, forma_pagamento, data_compra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (produto_id, cliente, formatar_cpf(cpf), email, quantidade, valor_total, forma_pagamento, datetime.now()))
        self.conn.commit()

# Estilos CSS com cores suaves
st.markdown("""
    <style>
    .stApp {
        background-color: #F5F5F5;
    }
    .block-container {
        padding: 2rem;
        background-color: #FFFFFF;
        border-radius: 10px;
    }
    .stTextInput>div>div>input, .stNumberInput>div>div>input {
        border: 1px solid #ddd;
        border-radius: 5px;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 5px;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #45A049;
    }
    h1, h2, h3 {
        color: #333333;
    }
    </style>
""", unsafe_allow_html=True)

# Interface do Usuário
def main():
    st.title("MEDIX - Gestão de Produtos e Vendas")
    menu = st.sidebar.radio("Menu", [
        "Cadastrar Produto", 
        "Registrar Venda", 
        "Listar Produtos", 
        "Listar Vendas", 
        "Backup de Dados"
    ])

    gestao = GestaoVendas()

    if menu == "Cadastrar Produto":
        st.subheader("Cadastro de Novo Produto")
        with st.form("cadastro_produto"):
            col1, col2 = st.columns(2)
            with col1:
                nome = st.text_input("Nome do Produto")
                valor = st.number_input("Valor (R$)", min_value=0.0, step=0.01)
            with col2:
                tipo = st.selectbox("Tipo do Produto", ["PDF", "Card", "Físico", "Serviço Digital"])
                quantidade = st.number_input("Quantidade", min_value=0, step=1)
            link_download = st.text_input("Link de Download (opcional)")
            descricao = st.text_area("Descrição do Produto")
            if st.form_submit_button("Cadastrar"):
                gestao.cadastrar_produto(nome, tipo, valor, quantidade, link_download, descricao)
                st.success("Produto cadastrado com sucesso!")

    elif menu == "Registrar Venda":
        st.subheader("Registro de Venda")
        produtos = gestao.listar_produtos()
        if not produtos.empty:
            produto_id = st.selectbox("Selecione o Produto", produtos['nome'].tolist())
            cliente = st.text_input("Nome do Cliente")
            cpf = st.text_input("CPF do Cliente")
            email = st.text_input("Email do Cliente")
            quantidade = st.number_input("Quantidade", min_value=1, step=1)
            forma_pagamento = st.selectbox("Forma de Pagamento", ["Pix", "Cartão", "Boleto"])
            if st.button("Registrar Venda"):
                produto_selecionado = produtos[produtos['nome'] == produto_id]['id'].values[0]
                gestao.registrar_venda(produto_selecionado, cliente, cpf, email, quantidade, forma_pagamento)
                st.success("Venda registrada com sucesso!")
        else:
            st.warning("Nenhum produto cadastrado. Cadastre um produto primeiro!")

    elif menu == "Listar Produtos":
        st.subheader("Lista de Produtos")
        produtos = gestao.listar_produtos()
        st.dataframe(produtos)

    elif menu == "Listar Vendas":
        st.subheader("Lista de Vendas")
        vendas = gestao.listar_vendas()
        st.dataframe(vendas)

    elif menu == "Backup de Dados":
        st.subheader("Backup de Dados")
        if st.button("Iniciar Backup"):
            shutil.copy2('medix_vendas.db', f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
            st.success("Backup realizado com sucesso!")

if __name__ == "__main__":
    main()
