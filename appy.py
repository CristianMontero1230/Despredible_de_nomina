import streamlit as st
import pandas as pd
import os
import sqlite3
import hashlib
import zipfile
import shutil
from datetime import datetime
import re

# Configuración de la página
st.set_page_config(
    page_title="Portal de Nómina",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Directorios de trabajo
UPLOAD_DIR = "data/nominas"
DB_FILE = "data/sistema_nomina.db"

# Asegurar directorios
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

# --- FUNCIONES DE BASE DE DATOS ---

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla Usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, nombre TEXT, cedula TEXT, role TEXT)''')
    # Tabla Archivos
    c.execute('''CREATE TABLE IF NOT EXISTS files
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, cedula TEXT, upload_date DATE, file_path TEXT)''')
    
    # Crear admin por defecto si no existe
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", 
                  ('admin', make_hashes('admin123'), 'Administrador', '0000', 'admin'))
    except sqlite3.IntegrityError:
        pass
        
    conn.commit()
    conn.close()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return True
    return False

def add_user(username, password, nombre, cedula):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, nombre, cedula, role) VALUES (?, ?, ?, ?, ?)",
                  (username, make_hashes(password), nombre, cedula, 'user'))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def login_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    data = c.fetchall()
    conn.close()
    if data:
        if check_hashes(password, data[0][1]):
            return data[0]
    return False

def get_files_by_cedula(cedula):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT filename, upload_date, file_path FROM files WHERE cedula = ?", conn, params=(cedula,))
    conn.close()
    return df

def register_file(filename, cedula, path):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().date()
    c.execute("INSERT INTO files (filename, cedula, upload_date, file_path) VALUES (?, ?, ?, ?)",
              (filename, cedula, today, path))
    conn.commit()
    conn.close()

# --- LÓGICA DE INTERFAZ ---

def main():
    init_db()
    
    # Estilos CSS personalizados
    st.markdown("""
        <style>
        .main {
            background-color: #f8f9fa;
        }
        .stButton>button {
            width: 100%;
            border-radius: 5px;
            height: 3em;
        }
        .success-box {
            padding: 1rem;
            border-radius: 0.5rem;
            background-color: #d4edda;
            color: #155724;
            margin-bottom: 1rem;
        }
        </style>
    """, unsafe_allow_html=True)

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = None

    if not st.session_state['logged_in']:
        menu_login()
    else:
        user_role = st.session_state['user_info'][4] # role index
        user_name = st.session_state['user_info'][2] # nombre index
        
        with st.sidebar:
            st.title(f"Hola, {user_name}")
            st.write(f"Rol: {user_role.upper()}")
            if st.button("Cerrar Sesión"):
                st.session_state['logged_in'] = False
                st.session_state['user_info'] = None
                st.rerun()

        if user_role == 'admin':
            admin_panel()
        else:
            worker_panel(st.session_state['user_info'][3]) # cedula

def menu_login():
    st.title("🔐 Portal de Nómina Corporativo")
    
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab1:
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type='password')
        if st.button("Entrar"):
            user = login_user(username, password)
            if user:
                st.session_state['logged_in'] = True
                st.session_state['user_info'] = user
                st.success(f"Bienvenido {user[2]}")
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")

    with tab2:
        st.subheader("Crear nueva cuenta")
        new_user = st.text_input("Crear Usuario")
        new_pass = st.text_input("Crear Contraseña", type='password')
        new_name = st.text_input("Nombre Completo")
        new_cedula = st.text_input("Número de Cédula (Sin puntos ni comas)")
        
        if st.button("Registrarse"):
            if new_user and new_pass and new_cedula:
                if add_user(new_user, new_pass, new_name, new_cedula):
                    st.success("Cuenta creada exitosamente. Por favor inicie sesión.")
                else:
                    st.error("El usuario ya existe.")
            else:
                st.warning("Por favor llene todos los campos.")

def admin_panel():
    st.header("📂 Panel de Administración")
    st.info("Sube aquí el archivo ZIP con los desprendibles de nómina. El sistema extraerá y asignará cada archivo automáticamente.")
    
    uploaded_file = st.file_uploader("Cargar Nómina Masiva (ZIP)", type="zip")
    
    if uploaded_file is not None:
        if st.button("Procesar Archivos"):
            with st.spinner('Procesando archivos...'):
                try:
                    # Guardar ZIP temporalmente
                    zip_path = os.path.join("data", "temp.zip")
                    with open(zip_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    # Extraer y procesar
                    count = 0
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        for file_info in zip_ref.infolist():
                            if file_info.filename.endswith('.pdf'):
                                # Extraer archivo
                                filename = os.path.basename(file_info.filename)
                                target_path = os.path.join(UPLOAD_DIR, filename)
                                
                                # Extraer directamente
                                with open(target_path, "wb") as f_out:
                                    f_out.write(zip_ref.read(file_info.filename))
                                
                                # Intentar encontrar cédula en el nombre del archivo
                                # Busca secuencias de 5 a 12 dígitos
                                match = re.search(r'\d{5,12}', filename)
                                if match:
                                    cedula_encontrada = match.group(0)
                                    register_file(filename, cedula_encontrada, target_path)
                                    count += 1
                    
                    st.success(f"✅ Proceso completado. Se han cargado y asignado {count} archivos exitosamente.")
                    os.remove(zip_path) # Limpieza
                    
                except Exception as e:
                    st.error(f"Error al procesar el archivo: {e}")

def worker_panel(cedula):
    st.header("📄 Mis Desprendibles de Nómina")
    
    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Fecha Inicio", value=datetime(2023, 1, 1))
    with col2:
        end_date = st.date_input("Fecha Fin", value=datetime.now())
        
    # Obtener datos
    df = get_files_by_cedula(cedula)
    
    if not df.empty:
        # Convertir fecha para filtrar
        df['upload_date'] = pd.to_datetime(df['upload_date']).dt.date
        
        mask = (df['upload_date'] >= start_date) & (df['upload_date'] <= end_date)
        filtered_df = df.loc[mask]
        
        st.write(f"Se encontraron {len(filtered_df)} documentos.")
        
        # Mostrar tabla interactiva
        for index, row in filtered_df.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1:
                    st.write(f"**Documento:** {row['filename']}")
                with c2:
                    st.write(f"📅 {row['upload_date']}")
                with c3:
                    try:
                        with open(row['file_path'], "rb") as pdf_file:
                            st.download_button(
                                label="⬇️ Descargar PDF",
                                data=pdf_file,
                                file_name=row['filename'],
                                mime="application/pdf",
                                key=f"btn_{index}"
                            )
                    except FileNotFoundError:
                        st.error("Archivo no encontrado en servidor")
                st.divider()
    else:
        st.info("No tienes desprendibles cargados en el sistema aún.")

if __name__ == '__main__':
    main()
