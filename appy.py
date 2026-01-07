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

# Listas auxiliares
MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

# --- FUNCIONES DE BASE DE DATOS ---

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla Usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, nombre TEXT, cedula TEXT, role TEXT)''')
    
    # Tabla Archivos (Actualizada con mes y año)
    c.execute('''CREATE TABLE IF NOT EXISTS files
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, cedula TEXT, 
                  upload_date DATE, file_path TEXT, month INTEGER, year INTEGER)''')
    
    # Migración simple: verificar si existen las columnas nuevas (para bases de datos existentes)
    try:
        c.execute("SELECT month FROM files LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE files ADD COLUMN month INTEGER")
            c.execute("ALTER TABLE files ADD COLUMN year INTEGER")
        except:
            pass

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

def add_user(cedula, password, nombre):
    # Username es la misma cedula
    username = cedula
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
    df = pd.read_sql_query("SELECT filename, upload_date, file_path, month, year FROM files WHERE cedula = ?", conn, params=(cedula,))
    conn.close()
    return df

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT nombre, cedula, role FROM users WHERE role != 'admin'", conn)
    conn.close()
    return df

def register_file(filename, cedula, path, month, year):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().date()
    c.execute("INSERT INTO files (filename, cedula, upload_date, file_path, month, year) VALUES (?, ?, ?, ?, ?, ?)",
              (filename, cedula, today, path, month, year))
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
            st.title(f"👤 {user_name}")
            st.write(f"Rol: **{user_role.upper()}**")
            st.write("---")
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
        st.subheader("Ingreso")
        username = st.text_input("Usuario (Cédula)")
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
        st.info("Su usuario será su número de cédula.")
        
        new_name = st.text_input("Nombre Completo")
        new_cedula = st.text_input("Número de Cédula (Sin puntos ni comas)")
        new_pass = st.text_input("Crear Contraseña", type='password')
        
        if st.button("Registrarse"):
            if new_name and new_pass and new_cedula:
                # Validar que cedula sea numerica
                if not new_cedula.isdigit():
                    st.error("La cédula debe contener solo números.")
                else:
                    if add_user(new_cedula, new_pass, new_name):
                        st.success("✅ Cuenta creada exitosamente. Su usuario es su número de cédula.")
                    else:
                        st.error("El usuario ya existe.")
            else:
                st.warning("Por favor llene todos los campos.")

def admin_panel():
    st.header("📂 Panel de Administración")
    
    tab_upload, tab_users = st.tabs(["📤 Cargar Nómina", "👥 Usuarios Registrados"])
    
    with tab_upload:
        st.subheader("Cargar Archivos Masivos")
        st.info("Seleccione el mes y año, luego suba el archivo ZIP. El sistema asignará los archivos según la cédula en el nombre.")
        
        col1, col2 = st.columns(2)
        with col1:
            selected_year = st.selectbox("Año", range(2023, 2030), index=datetime.now().year - 2023)
        with col2:
            selected_month_name = st.selectbox("Mes", list(MESES.values()), index=datetime.now().month - 1)
            # Obtener numero de mes
            selected_month = [k for k, v in MESES.items() if v == selected_month_name][0]

        uploaded_file = st.file_uploader("Archivo ZIP con Nóminas", type="zip")
        
        if uploaded_file is not None:
            if st.button("Procesar y Guardar Archivos"):
                with st.spinner('Procesando archivos...'):
                    try:
                        # Crear carpeta especifica para el mes/año si se desea mejor organizacion fisica (opcional, aqui usamos DB)
                        # Guardar ZIP temporalmente
                        zip_path = os.path.join("data", "temp.zip")
                        with open(zip_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        
                        # Extraer y procesar
                        count = 0
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            for file_info in zip_ref.infolist():
                                if file_info.filename.endswith('.pdf') and not file_info.filename.startswith('__MACOSX'):
                                    # Limpiar nombre de archivo (quitar rutas de carpetas si existen en el zip)
                                    filename = os.path.basename(file_info.filename)
                                    
                                    # Guardar fisicamente en data/nominas/YYYY_MM_filename
                                    safe_filename = f"{selected_year}_{selected_month}_{filename}"
                                    target_path = os.path.join(UPLOAD_DIR, safe_filename)
                                    
                                    # Extraer contenido
                                    with open(target_path, "wb") as f_out:
                                        f_out.write(zip_ref.read(file_info.filename))
                                    
                                    # Buscar cédula en el nombre
                                    match = re.search(r'\d{5,12}', filename)
                                    if match:
                                        cedula_encontrada = match.group(0)
                                        register_file(filename, cedula_encontrada, target_path, selected_month, selected_year)
                                        count += 1
                        
                        st.success(f"✅ Proceso completado. Se han guardado {count} archivos para {selected_month_name} {selected_year}.")
                        os.remove(zip_path)
                        
                    except Exception as e:
                        st.error(f"Error al procesar el archivo: {e}")

    with tab_users:
        st.subheader("Base de Datos de Usuarios")
        users_df = get_all_users()
        st.dataframe(users_df, use_container_width=True)
        st.caption(f"Total de usuarios registrados: {len(users_df)}")

def worker_panel(cedula):
    st.header("📄 Mis Desprendibles de Nómina")
    
    # Filtros por Año y Mes
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        filter_year = st.selectbox("Filtrar por Año", [2023, 2024, 2025, 2026], index=1)
    with col2:
        filter_month_name = st.selectbox("Filtrar por Mes", ["Todos"] + list(MESES.values()))
    
    # Obtener datos
    df = get_files_by_cedula(cedula)
    
    if not df.empty:
        # Mapear numero de mes a nombre para mostrar
        df['nombre_mes'] = df['month'].map(MESES)
        
        # Aplicar filtros
        mask = (df['year'] == filter_year)
        if filter_month_name != "Todos":
            filter_month = [k for k, v in MESES.items() if v == filter_month_name][0]
            mask = mask & (df['month'] == filter_month)
            
        filtered_df = df.loc[mask]
        
        if len(filtered_df) > 0:
            st.write(f"Mostrando documentos de: **{filter_month_name} {filter_year}**")
            
            for index, row in filtered_df.iterrows():
                with st.container():
                    # Tarjeta de documento
                    c1, c2, c3 = st.columns([3, 2, 2])
                    with c1:
                        st.subheader(f"📄 {row['filename']}")
                        st.caption(f"Cargado el: {row['upload_date']}")
                    with c2:
                        st.info(f"{row['nombre_mes']} {row['year']}")
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
                            st.error("Archivo no encontrado")
                    st.divider()
        else:
            st.warning("No se encontraron desprendibles para la fecha seleccionada.")
    else:
        st.info("No tienes desprendibles cargados en el sistema aún.")

if __name__ == '__main__':
    main()

