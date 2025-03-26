# Here are the changes you need to make to app.py:

# 1. Add this import at the top of app.py, with your other imports
from credentials_manager import get_credentials

# 2. Replace the existing autenticar_google() function with this simpler version
def autenticar_google():
    """Autentica com a API do Google usando o gerenciador de credenciais."""
    if not google_imports_successful:
        st.error("Bibliotecas do Google não estão disponíveis. Verifique se estão instaladas corretamente.")
        return None
        
    try:
        # Usar o gerenciador de credenciais para obter as credenciais
        return get_credentials()
    except Exception as e:
        logging.error(f"Erro na autenticação: {e}")
        st.error(f"Erro na autenticação com Google API: {e}")
        return None

# 3. Update the GestaoVendasGoogleSheets.__init__ method for better error handling
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
            self.creds = autenticar_google()
            if self.creds:
                logging.info("Credenciais obtidas com sucesso do gerenciador de credenciais")
                self.drive_service = build('drive', 'v3', credentials=self.creds)
                self.sheets_service = build('sheets', 'v4', credentials=self.creds)
                self.gc = gspread.authorize(self.creds)
                
                # Inicializa as planilhas se não existirem
                self.sheets = self.inicializar_planilhas()
                if self.sheets:
                    self.produtos_sheet = self.sheets.worksheet("Produtos")
                    self.vendas_sheet = self.sheets.worksheet("Vendas")
                    
                    # Verifica e corrige headers das planilhas se necessário
                    self.verificar_headers()
                    self.autenticado = True
                    logging.info("Autenticação e inicialização das planilhas concluídas com sucesso")
            else:
                logging.error("Falha ao obter credenciais - objeto de credenciais é None")
        except Exception as e:
            logging.error(f"Erro na inicialização do Google Sheets: {e}")
            
    # Rest of the class remains the same...

# 4. Update the get_gestao() function to provide better feedback
def get_gestao():
    if 'gestao' not in st.session_state:
        # Tenta inicializar a gestão com Google Sheets
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

# 5. Add the following to your configuracoes_ui function to provide a way to test/fix credentials:
# (Add this within the existing function where appropriate)

# Within the configuracoes_ui function, add this option when not using Google:
if not usando_google:
    st.subheader("🔧 Solução de Problemas de Autenticação")
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
