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
    
    # Migración simple
    try:
        c.execute("SELECT month FROM files LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE files ADD COLUMN month INTEGER")
            c.execute("ALTER TABLE files ADD COLUMN year INTEGER")
        except:
            pass

    # Crear admin por defecto
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

def delete_user(cedula):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM users WHERE cedula = ?", (cedula,))
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()

def delete_file_registry(cedula, month, year):
    """Borra el registro y el archivo físico de un usuario en un mes/año especifico"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # Obtener path para borrar físico
        c.execute("SELECT file_path FROM files WHERE cedula=? AND month=? AND year=?", (cedula, month, year))
        rows = c.fetchall()
        for row in rows:
            if row[0] and os.path.exists(row[0]):
                try:
                    os.remove(row[0])
                except:
                    pass
        # Borrar de DB
        c.execute("DELETE FROM files WHERE cedula=? AND month=? AND year=?", (cedula, month, year))
        conn.commit()
        return True
    except Exception as e:
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

def get_monthly_stats(year):
    """Obtiene conteo de archivos por mes para un año dado"""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT month, COUNT(*) as count, MAX(upload_date) as last_update FROM files WHERE year=? GROUP BY month", conn, params=(year,))
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
    
    st.markdown("""
        <style>
        .main { background-color: #f8f9fa; }
        .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
        .metric-card {
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
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
    
    tab_upload, tab_users = st.tabs(["📤 Gestión de Nómina", "👥 Gestión de Usuarios"])
    
    with tab_upload:
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            selected_year = st.selectbox("Año de Gestión", range(2023, 2030), index=datetime.now().year - 2023)
        with col_sel2:
            # Selector solo para subida
            upload_month_name = st.selectbox("Mes para Subir Archivos", list(MESES.values()), index=datetime.now().month - 1)
            upload_month = [k for k, v in MESES.items() if v == upload_month_name][0]
            
        st.divider()
        
        # --- SECCION 1: CARGA DE ARCHIVOS ---
        st.subheader(f"1. Cargar Archivos: {upload_month_name} {selected_year}")
        st.info("⚠️ Si subes un archivo para un usuario que ya tenía nómina este mes, se reemplazará automáticamente.")
        
        uploaded_file = st.file_uploader(f"Subir ZIP de Nómina", type="zip", key="zip_uploader")
        
        if uploaded_file is not None:
            if st.button("Procesar y Guardar Archivos"):
                with st.spinner('Procesando archivos...'):
                    try:
                        zip_path = os.path.join("data", "temp.zip")
                        with open(zip_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        
                        count = 0
                        replaced = 0
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            for file_info in zip_ref.infolist():
                                if file_info.filename.endswith('.pdf') and not file_info.filename.startswith('__MACOSX'):
                                    filename = os.path.basename(file_info.filename)
                                    match = re.search(r'\d{5,12}', filename)
                                    
                                    if match:
                                        cedula_encontrada = match.group(0)
                                        
                                        # 1. Borrar anterior si existe (REEMPLAZO)
                                        if delete_file_registry(cedula_encontrada, upload_month, selected_year):
                                            replaced += 1
                                        
                                        # 2. Guardar nuevo
                                        timestamp = int(datetime.now().timestamp())
                                        safe_filename = f"{selected_year}_{upload_month}_{timestamp}_{filename}"
                                        target_path = os.path.join(UPLOAD_DIR, safe_filename)
                                        
                                        with open(target_path, "wb") as f_out:
                                            f_out.write(zip_ref.read(file_info.filename))
                                            
                                        register_file(filename, cedula_encontrada, target_path, upload_month, selected_year)
                                        count += 1
                        
                        st.success(f"✅ Proceso completado. Archivos procesados: {count}. (Reemplazados: {replaced})")
                        os.remove(zip_path)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error al procesar el archivo: {e}")
        
        st.divider()
        
        # --- SECCION 2: RESUMEN POR MESES ---
        st.subheader(f"2. Estado de Carga por Meses ({selected_year})")
        
        stats_df = get_monthly_stats(selected_year)
        
        # Crear estructura de datos para mostrar todos los meses
        month_data = []
        for m_num, m_name in MESES.items():
            row = stats_df[stats_df['month'] == m_num]
            count = row.iloc[0]['count'] if not row.empty else 0
            last_update = row.iloc[0]['last_update'] if not row.empty else "-"
            status = "✅ Cargado" if count > 0 else "⚪ Sin datos"
            
            month_data.append({
                "Mes": m_name,
                "Estado": status,
                "Archivos Cargados": count,
                "Última Actualización": last_update
            })
            
        display_df = pd.DataFrame(month_data)
        
        # Estilos condicionales
        def style_rows(row):
            color = '#d4edda' if row['Archivos Cargados'] > 0 else '#f8f9fa'
            return [f'background-color: {color}'] * len(row)

        st.dataframe(
            display_df.style.apply(style_rows, axis=1),
            use_container_width=True,
            hide_index=True
        )

    with tab_users:
        st.subheader("Base de Datos de Usuarios")
        st.warning("⚠️ Cuidado: Eliminar un usuario es irreversible.")
        
        users_df = get_all_users()
        
        if not users_df.empty:
            st.metric("Total Usuarios Registrados", len(users_df))
            
            # Encabezados de tabla manual para mejor control de botones
            col_h1, col_h2, col_h3 = st.columns([2, 2, 1])
            col_h1.markdown("**Nombre**")
            col_h2.markdown("**Cédula**")
            col_h3.markdown("**Acción**")
            st.divider()

            for index, row in users_df.iterrows():
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.write(row['nombre'])
                with col2:
                    st.write(row['cedula'])
                with col3:
                    if st.button("🗑️ Eliminar", key=f"del_{row['cedula']}"):
                        if delete_user(row['cedula']):
                            st.success(f"Usuario {row['nombre']} eliminado.")
                            st.rerun()
                st.divider()
        else:
            st.info("No hay usuarios registrados aparte del administrador.")

def worker_panel(cedula):
    st.header("📄 Mis Desprendibles de Nómina")
    
    col1, col2 = st.columns(2)
    with col1:
        filter_year = st.selectbox("Filtrar por Año", [2023, 2024, 2025, 2026], index=1)
    with col2:
        filter_month_name = st.selectbox("Filtrar por Mes", ["Todos"] + list(MESES.values()))
    
    df = get_files_by_cedula(cedula)
    
    if not df.empty:
        df['nombre_mes'] = df['month'].map(MESES)
        
        mask = (df['year'] == filter_year)
        if filter_month_name != "Todos":
            filter_month = [k for k, v in MESES.items() if v == filter_month_name][0]
            mask = mask & (df['month'] == filter_month)
            
        filtered_df = df.loc[mask]
        
        if len(filtered_df) > 0:
            st.write(f"Mostrando {len(filtered_df)} documentos encontrados:")
            
            for index, row in filtered_df.iterrows():
                with st.container():
                    c1, c2, c3 = st.columns([3, 2, 2])
                    with c1:
                        st.subheader(f"📄 {row['filename']}")
                        st.caption(f"Subido el: {row['upload_date']}")
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
            st.warning(f"No hay desprendibles para {filter_month_name} de {filter_year}.")
    else:
        st.info("No tienes desprendibles cargados en el sistema aún.")

if __name__ == '__main__':
    main()
