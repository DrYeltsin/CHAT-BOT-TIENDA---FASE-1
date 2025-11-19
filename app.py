# app.py

import streamlit as st
import os
from google import genai
from google.genai import types
# Importamos todo el módulo db_utils para manipular su variable global 'client'
import db_utils 
from db_utils import setup_sqlite_db_large, get_product_data, chatbot_response, DB_NAME, NUM_PRODUCTS

# --- CONFIGURACIÓN DE STREAMLIT ---
st.set_page_config(page_title="Chatbot de Productos UNI - Etapa 1", layout="wide")
st.title("🤖 Chatbot de Productos - Principales Tecnologías de IA") # <--- TITULO PERSONALIZADO
st.caption("Etapa 1: Consulta a DB con LLM | Desarrollado por: Yeltsin Solano Díaz") # <--- LEYENDA Y NOMBRE PERSONALIZADO

# --- 1. FUNCIÓN DE INICIALIZACIÓN (Cache) ---
@st.cache_resource
def initialize_db(db_name, num_products):
    """Inicializa la base de datos una sola vez."""
    # st.info(f"Creando base de datos SQLite con {num_products} productos en Soles (S/ )...")
    conn = db_utils.setup_sqlite_db_large(db_name, num_products)
    if conn:
        st.success("Base de datos de productos cargada con éxito.")
    return conn

# --- 2. GESTIÓN DE LA CLAVE API Y LA CONEXIÓN ---
st.sidebar.header("🔑 Configuración")
api_key = st.sidebar.text_input("Ingresa tu Clave API de Gemini (AIza...)", type="password")
db_conn = None

if api_key:
    try:
        # ** CORRECCIÓN CLAVE AQUÍ **: Asignamos el cliente a la variable global 'client' en el módulo db_utils
        db_utils.client = genai.Client(api_key=api_key)
        st.sidebar.success("Clave API validada y cliente Gemini listo.")
    except Exception as e:
        st.sidebar.error(f"Error al inicializar Gemini. Revisa la clave: {e}")
        db_utils.client = None

    # Inicializa la base de datos si la API es válida
    if db_utils.client:
        db_conn = initialize_db(DB_NAME, NUM_PRODUCTS)

# --- 3. BUCLE DE CONVERSACIÓN ---
if db_conn and db_utils.client:
    # Inicializar el historial de chat de Streamlit si no existe
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "¡Hola! Soy tu asistente de ventas. Mi catálogo contiene 500 productos. Puedes consultar en lenguaje fluido sobre cualquier producto, sus caracteristicas, disponibilidad y precio en Soles (S/ )."}
        ]

    # Mostrar mensajes anteriores
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Manejar la entrada del usuario
    if prompt := st.chat_input("Pregunta sobre un producto o una familia de productos:"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Buscando en el catálogo y generando respuesta con IA..."):
                # 1. Obtener datos de la DB
                product_info = get_product_data(prompt, db_conn)
                
                # 2. Generar respuesta del Chatbot
                response = chatbot_response(prompt, product_info)
            
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

elif not api_key:
    st.error("Por favor, ingresa tu Clave API de Gemini en la barra lateral para comenzar.")
