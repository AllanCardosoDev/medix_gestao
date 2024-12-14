import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import re
import base64



def validar_cpf(cpf):
    """Validação básica de CPF"""
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
    """Formata o CPF com pontos e traço"""
    cpf = re.sub(r'\D', '', cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

class GestaoVendas:
    def __init__(self, db_name='medix_vendas.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.migrar_banco_dados()
        self.criar_tabelas()

    def migrar_banco_dados(self):
        """Migra o banco de dados para a nova estrutura"""
        cursor = self.conn.cursor()
        
        try:
            # Verificar e adicionar colunas necessárias
            colunas_necessarias = [
                'cpf_cliente', 
                'data_compra',  # Nova coluna para data específica da compra
                'data_registro'  # Mantém a data de registro no sistema
            ]
            
            for coluna in colunas_necessarias:
                try:
                    cursor.execute(f"ALTER TABLE vendas ADD COLUMN {coluna} TEXT")
                except sqlite3.OperationalError:
                    # Coluna já existe
                    pass
            
            self.conn.commit()
        except Exception as e:
            st.error(f"Erro ao migrar banco de dados: {e}")

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
                data_registro DATETIME,
                data_compra DATE,
                status TEXT DEFAULT 'Processando',
                FOREIGN KEY(produto_id) REFERENCES produtos(id)
            )
        ''')
        self.conn.commit()

    def validar_produto(self, nome):
        """Verifica se o produto já existe"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM produtos WHERE nome = ?', (nome,))
        return cursor.fetchone()[0] == 0

    def cadastrar_produto(self, nome, tipo, valor, quantidade=None, link_download=None, descricao=None):
        cursor = self.conn.cursor()
        try:
            # Validação de produto único
            if not self.validar_produto(nome):
                raise ValueError("Já existe um produto com este nome")

            cursor.execute('''
                INSERT INTO produtos (nome, tipo, valor, quantidade, link_download, descricao) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (nome, tipo, valor, quantidade, link_download, descricao))
            self.conn.commit()
            return True
        except Exception as e:
            st.error(f"Erro ao cadastrar produto: {e}")
            return False

    def registrar_venda(self, produto_id, cliente, cpf, email, quantidade, forma_pagamento, data_compra=None):
        cursor = self.conn.cursor()
        
        # Validar CPF
        if not validar_cpf(cpf):
            raise ValueError("CPF inválido")
        
        # Formatar CPF
        cpf_formatado = formatar_cpf(cpf)
        
        # Buscar detalhes do produto
        cursor.execute('SELECT valor, tipo, quantidade FROM produtos WHERE id = ?', (produto_id,))
        produto = cursor.fetchone()
        
        if not produto:
            raise ValueError("Produto não encontrado")
        
        valor_unitario, tipo_produto, estoque_atual = produto
        
        # Verificação de estoque apenas para produtos físicos
        if tipo_produto in ['Card', 'Físico'] and (estoque_atual is None or quantidade > estoque_atual):
            raise ValueError(f"Estoque insuficiente. Disponível: {estoque_atual or 0}")
        
        valor_total = valor_unitario * quantidade
        data_registro = datetime.now()
        
        # Se data_compra não for fornecida, usa a data atual
        if not data_compra:
            data_compra = data_registro.date()

        # Registrar venda
        cursor.execute('''
            INSERT INTO vendas (
                produto_id, cliente, cpf_cliente, email_cliente, quantidade, 
                valor_total, forma_pagamento, data_registro, data_compra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            produto_id, 
            cliente, 
            cpf_formatado, 
            email, 
            quantidade, 
            valor_total, 
            forma_pagamento, 
            data_registro,
            data_compra
        ))
        
        # Atualizar estoque apenas para produtos físicos
        if tipo_produto in ['Card', 'Físico']:
            cursor.execute('''
                UPDATE produtos 
                SET quantidade = quantidade - ? 
                WHERE id = ?
            ''', (quantidade, produto_id))
        
        self.conn.commit()
        return True

    def listar_produtos(self):
        return pd.read_sql_query("SELECT * FROM produtos", self.conn)

    def listar_vendas(self):
        return pd.read_sql_query("""
            SELECT 
                v.id, 
                p.nome as produto, 
                p.tipo as tipo_produto,
                v.cliente, 
                v.cpf_cliente,
                v.email_cliente,
                v.quantidade, 
                v.valor_total, 
                v.forma_pagamento,
                v.data_registro,
                v.data_compra,
                v.status
            FROM vendas v
            JOIN produtos p ON v.produto_id = p.id
            ORDER BY v.data_registro DESC
        """, self.conn)

    def exportar_excel(self, tipo='vendas'):
        if tipo == 'vendas':
            df = self.listar_vendas()
        else:
            df = self.listar_produtos()
        
        nome_arquivo = f'MEDIX_{tipo}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        df.to_excel(nome_arquivo, index=False)
        return nome_arquivo

def main():
    st.set_page_config(
        page_title="MEDIX - Gestão de Produtos", 
        page_icon="🩺",
        layout="wide"
    )
    
    # Estilo personalizado
    st.markdown("""
    <style>
    .big-font {
        font-size:20px !important;
        color: #0083B8;
    }
    .highlight {
        background-color: #F0F2F6;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Verificar se o logo existe
    try:
        logo_path = "logo_medix.jpeg"
        col1, col2 = st.columns([1, 4])
        with col1:
            st.image(logo_path, width=150)
    except FileNotFoundError:
        col1, col2 = st.columns([1, 4])
        with col1:
            st.image(get_base64_logo(), width=150)
        st.warning("Logo não encontrado. Adicione um arquivo logo_medix.jpeg")

    # Título
    st.title("MEDIX - Gestão de Produtos e Vendas")

    # Inicializar sessão
    if 'gestao' not in st.session_state:
        st.session_state.gestao = GestaoVendas()
    
    gestao = st.session_state.gestao

    # Menu lateral
    menu = st.sidebar.radio("Navegação", [
        "Cadastrar Produto", 
        "Registrar Venda", 
        "Listar Produtos", 
        "Listar Vendas",
        "Exportar Dados"
    ])

    if menu == "Cadastrar Produto":
        st.subheader("📦 Cadastro de Novo Produto")
        
        # Formulário de cadastro
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

    elif menu == "Registrar Venda":
        st.subheader("💳 Registro de Nova Venda")
        
        # Verificar se há produtos cadastrados
        produtos = gestao.listar_produtos()
        
        if produtos.empty:
            st.warning("Não há produtos cadastrados. Cadastre um produto primeiro.")
        else:
            with st.form("registro_venda"):
                col1, col2 = st.columns(2)
                with col1:
                    # Criar opções de seleção
                    opcoes_produtos = dict(zip(produtos['nome'], produtos['id']))
                    produto_selecionado = st.selectbox(
                        "Selecione o Produto", 
                        list(opcoes_produtos.keys())
                    )
                    
                    cliente = st.text_input("Nome do Cliente")
                    cpf = st.text_input("CPF do Cliente", help="Digite apenas números")
                    email = st.text_input("Email do Cliente")
                
                with col2:
                    # Encontrar detalhes do produto selecionado
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
                    
                    # Novo campo para data da compra
                    data_compra = st.date_input("Data da Compra", datetime.now())
                
                submit_venda = st.form_submit_button("Registrar Venda")
                
                if submit_venda:
                    try:
                        # Validações adicionais
                        if not cliente:
                            st.error("Nome do cliente é obrigatório")
                            st.stop()
                        
                        if not cpf:
                            st.error("CPF do cliente é obrigatório")
                            st.stop()
                        
                        produto_id = opcoes_produtos[produto_selecionado]
                        gestao.registrar_venda(
                            produto_id, 
                            cliente, 
                            cpf,
                            email, 
                            quantidade, 
                            forma_pagamento,
                            data_compra  # Passa a data da compra
                        )
                        st.success("Venda registrada com sucesso!")
                    except ValueError as e:
                        st.error(str(e))

    elif menu == "Listar Produtos":
        produtos = gestao.listar_produtos()
        if not produtos.empty:
            st.dataframe(produtos)
        else:
            st.warning("Nenhum produto cadastrado")

    elif menu == "Listar Vendas":
        vendas = gestao.listar_vendas()
        if not vendas.empty:
            st.dataframe(vendas)
        else:
            st.warning("Nenhuma venda registrada")

    elif menu == "Exportar Dados":
        tipo = st.selectbox("Tipo de Exportação", ["vendas", "produtos"])
        if st.button("Exportar Excel"):
            try:
                arquivo = gestao.exportar_excel(tipo)
                st.success(f"Arquivo {arquivo} gerado com sucesso!")
                with open(arquivo, 'rb') as f:
                    st.download_button(
                        label="Baixar Arquivo",
                        data=f.read(),
                        file_name=arquivo,
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
            except Exception as e:
                st.error(f"Erro ao exportar: {e}")

if __name__ == "__main__":
    main()