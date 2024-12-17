import streamlit as st
import pandas as pd
import openpyxl
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from datetime import datetime
import re
import io

# Configuração Inicial do Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = "google_sheets_credentials.json"  # Arquivo de credenciais JSON
SPREADSHEET_NAME = "MEDIX_Gestao_Vendas"

# Credenciais do Google
@st.cache_resource
def get_credentials():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def validar_cpf(cpf):
    if not cpf or cpf == '00000000000':
        return True
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11 or len(set(cpf)) == 1:
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

class GestaoVendas:
    def __init__(self):
        self.client = get_credentials()
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

    def listar_produtos(self):
        return get_as_dataframe(self.produtos_sheet)

    def listar_vendas(self):
        return get_as_dataframe(self.vendas_sheet)

    def exportar_excel(self, tipo):
        df = self.listar_produtos() if tipo == "produtos" else self.listar_vendas()
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=tipo.capitalize())
        return output.getvalue()

# Interface do Usuário com Layout Melhorado
def main():
    st.set_page_config(page_title="MEDIX - Gestão", layout="wide")

    # Estilo da Sidebar Melhorado
    st.sidebar.markdown("""
    <style>
        .sidebar .sidebar-content {
            background-color: #F0F2F6;
        }
        .stSelectbox, .stButton {
            margin-top: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

    # Cabeçalho Principal
    col1, col2 = st.columns([1, 4])
    with col1:
        st.image("logo_medix.jpeg", width=150)
    with col2:
        st.title("MEDIX - Gestão de Produtos e Vendas")

    gestao = GestaoVendas()

    # Navegação na Barra Lateral
    menu = st.sidebar.radio("Menu", [
        "📋 Listar Produtos",
        "📊 Listar Vendas",
        "📤 Exportar Dados"
    ])

    if menu == "📋 Listar Produtos":
        st.subheader("Lista de Produtos")
        st.dataframe(gestao.listar_produtos())

    elif menu == "📊 Listar Vendas":
        st.subheader("Lista de Vendas")
        st.dataframe(gestao.listar_vendas())

    elif menu == "📤 Exportar Dados":
        st.subheader("Exportar Dados")
        tipo = st.selectbox("Selecione o Tipo", ["produtos", "vendas"])
        if st.button("Exportar para Excel"):
            try:
                data = gestao.exportar_excel(tipo)
                st.download_button(
                    label="Baixar Excel",
                    data=data,
                    file_name=f"MEDIX_{tipo}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"Erro ao exportar dados: {e}")

if __name__ == "__main__":
    main()
