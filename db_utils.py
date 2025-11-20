import sqlite3
import random
import json
from faker import Faker
from google import genai 
from google.genai import types
import os

# --- Parámetros ---
DB_NAME = "productos_soles.db"
NUM_PRODUCTS = 500
fake = Faker('es_ES') 
global client 
client = None # Se inicializará en app.py con la clave API

# ==============================================================================
# 1. GENERACIÓN Y POBLAMIENTO DE LA BASE DE DATOS (500 Productos en SOLES)
# ==============================================================================

def generate_random_product(product_id):
    """Genera un solo registro de producto con datos aleatorios y realistas."""
    
    families = ['Electrónica', 'Hogar', 'Oficina', 'Deportes', 'Accesorios']
    family = random.choice(families)

    if family == 'Electrónica':
        prod_name = f"{random.choice(['Smart TV', 'Laptop', 'Auriculares'])} {fake.bs()}"
        prod_desc = f"Un {prod_name} de última generación con {random.randint(4, 16)}GB de RAM y procesador de alta velocidad."
    elif family == 'Hogar':
        prod_name = f"Robot Aspirador {fake.word().capitalize()}"
        prod_desc = f"Aspiradora inteligente con {random.randint(1000, 3000)} Pa de succión y función de mapeo láser."
    elif family == 'Oficina':
        prod_name = f"Silla Ergonómica '{fake.company_suffix()}'"
        prod_desc = f"Silla ejecutiva de malla transpirable con soporte lumbar ajustable."
    else: 
        prod_name = f"Zapatillas Deportivas {fake.color_name()} {fake.word()}"
        prod_desc = f"Calzado ideal para running o entrenamiento de alto rendimiento. Talla {random.randint(35, 45)}."

    # Precio en Soles (S/ )
    cost = round(random.uniform(50.0, 5000.0), 2)
    price = round(cost * random.uniform(1.2, 2.5), 2) 
    status = random.choice([True, True, True, False]) # 75% disponible
    suggested_prod_id = None
    if random.random() < 0.15:
        suggested_prod_id = f"PROD{random.randint(1, NUM_PRODUCTS):04d}"

    return (
        f"PROD{product_id:04d}", 
        fake.user_name(),       
        prod_name,              
        prod_desc,              
        fake.url(),             
        'PEN',                   # Código de moneda peruana (Nuevo Sol)
        cost,                   
        price,                  
        suggested_prod_id,      
        family,                 
        fake.word(),            
        random.choice(['Unidad', 'Caja']),
        fake.md5(),             
        random.randint(5, 50),  
        status                  
    )


def setup_sqlite_db_large(db_name, num_products):
    """Crea la base de datos y la pobla con N productos aleatorios."""
    conn = None
    try:
        conn = sqlite3.connect(db_name)
        cur = conn.cursor()
        
        # 1. Creación de la tabla (manteniendo la estructura de tbl_product)
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS tbl_product (
                id INTEGER PRIMARY KEY AUTOINCREMENT, prod_id TEXT NOT NULL UNIQUE,             
                account_id TEXT, prod_name TEXT NOT NULL, prod_desc TEXT NOT NULL,                  
                prod_photo TEXT, prod_currency TEXT, prod_cost REAL, prod_price REAL NOT NULL,                 
                prod_suggested_prod_id TEXT, prod_family TEXT, prod_subfamily TEXT,                      
                prod_uom TEXT, prod_qr_code TEXT, prod_min_stock INTEGER, status BOOLEAN
            );
        """
        cur.execute(create_table_sql)
        cur.execute("DELETE FROM tbl_product") 
        
        products_to_insert = [generate_random_product(i + 1) for i in range(num_products)]
        
        insert_sql = """
            INSERT INTO tbl_product (
                prod_id, account_id, prod_name, prod_desc, prod_photo, prod_currency, prod_cost, prod_price, 
                prod_suggested_prod_id, prod_family, prod_subfamily, prod_uom, prod_qr_code, prod_min_stock, status
            ) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cur.executemany(insert_sql, products_to_insert)
        conn.commit()
        return conn

    except sqlite3.Error as e:
        # Aquí puedes registrar el error en los logs de Streamlit si es necesario
        return None

# ==============================================================================
# 2. LÓGICA DEL CHATBOT: INTEGRACIÓN GEMINI + DB (FINAL Y ROBUSTA)
# ==============================================================================

def get_product_data(user_query, conn):
    """Usa Gemini para generar SQL (soporta múltiples consultas) y ejecuta en la DB."""
    if not client:
        return []
        
    db_schema = """
    CREATE TABLE tbl_product (
        id INTEGER PRIMARY KEY, prod_id TEXT, prod_name TEXT, prod_desc TEXT, 
        prod_price REAL, status BOOLEAN, prod_family TEXT, prod_suggested_prod_id TEXT
    );
    """
    
    prompt_for_sql = f"""
    Eres un experto en bases de datos SQLite. Tu única tarea es convertir la siguiente consulta de lenguaje natural del usuario 
    en una o más consultas SQL SELECT válidas que busquen la información en la tabla 'tbl_product'.
    
    Reglas estrictas:
    1. SOLO genera el comando SQL. NO agregues explicaciones, comillas ni texto adicional.
    2. Si el usuario pide el 'más caro', usa 'SELECT * FROM tbl_product WHERE status = 1 ORDER BY prod_price DESC LIMIT 1'.
    3. Si el usuario pide 'los 3 más caros', usa 'SELECT * FROM tbl_product WHERE status = 1 ORDER BY prod_price DESC LIMIT 3'.
    4. Si el usuario pide 'ofertas', 'más baratos' o 'mejores precios', usa 'SELECT * FROM tbl_product WHERE status = 1 ORDER BY prod_price ASC LIMIT 3'.
    5. Si el usuario pregunta por un 'ejemplo', 'muestra' o 'dame un producto', usa 'SELECT * FROM tbl_product WHERE status = 1 ORDER BY RANDOM() LIMIT 1'.
    6. Si el usuario pide una combinación (ej: '2 caros y 2 baratos'), genera DOS sentencias SELECT completas separadas por un punto y coma (;).
    7. Si el usuario pregunta por un 'tipo' o 'familia' sin especificar cantidad, usa 'WHERE prod_family LIKE %...%' y 'LIMIT 5'.
    8. Solo considera productos cuyo campo 'status' sea TRUE (1), a menos que se especifique lo contrario.
    9. El esquema de la tabla es: {db_schema}.
    
    Consulta del usuario: {user_query}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_for_sql,
            config=types.GenerateContentConfig(
                temperature=0.0 
            )
        )
        sql_query = response.text.strip()
        
        # Procesamiento de múltiples sentencias separadas por punto y coma
        queries = [q.strip() for q in sql_query.split(';') if q.strip()]
        products_info = []
        
        cur = conn.cursor()
        
        for query in queries:
            # Validación básica de seguridad y sintaxis
            if not query.lower().startswith("select"):
                continue
                
            try:
                cur.execute(query)
                results = cur.fetchall()
                column_names = [description[0] for description in cur.description]
                # Agregar los resultados de esta consulta a la lista general
                products_info.extend([dict(zip(column_names, row)) for row in results])
            except Exception as e:
                # Si una sub-consulta falla, continuamos con la siguiente
                print(f"Error ejecutando sub-consulta: {e}")
                continue
        
        return products_info

    except Exception as e:
        return []

def chatbot_response(user_query, products_data):
    """Genera la respuesta final del chatbot (Paso 2)."""
    if not client:
        return "Disculpa, la IA no está configurada. Por favor, ingresa tu clave API de Gemini."
        
    system_instruction = (
        "Eres un amable asistente de ventas. Tu única fuente de información es el catálogo de productos proporcionado. "
        "Debes responder en un tono **siempre amable** y profesional. "
        
        "**Si recibes datos de productos (products_data):** DEBES utilizar estos datos para formular la respuesta. "
        "Si hay varios productos, lístalos amablemente. Si el usuario pidió 'el más caro' y 'el más barato', identifica cuál es cuál basándote en el precio y preséntalos. "
        "**PROHIBIDO RESPONDER FRASES COMO:** 'Lamento informarte', 'no tengo información', 'no he podido encontrar', etc. si 'products_data' contiene datos. "
        
        "Menciona explícitamente el precio, la descripción y la disponibilidad. La moneda es el **Sol Peruano (S/ )**. "
        "Si muestras una lista, menciona al final: '(Recuerda que solo podemos mostrar un máximo de 5 productos por consulta, pero tenemos más en el catálogo)'."
        
        "**Restricción Crucial:** SOLO puedes responder sobre los productos. Si la consulta NO está relacionada O si NO SE ENCONTRÓ NINGÚN DATO DE LA DB, debes responder amablemente que solo puedes asistir con consultas sobre el catálogo."
    )
    
    if products_data:
        data_string = json.dumps(products_data, indent=2)
        final_prompt = (
            f"El usuario preguntó: '{user_query}'.\n"
            f"La base de datos encontró los siguientes productos y detalles: \n{data_string}\n\n"
            "Genera una respuesta clara y amable que aborde la consulta del usuario utilizando esta información. RECUERDA: la moneda es el Sol Peruano (S/ )."
        )
    else:
        final_prompt = f"El usuario preguntó: '{user_query}'. No se encontró información de productos en el catálogo."
        
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=final_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
        return response.text
    except Exception as e:
        return f"Disculpa, hubo un error al generar la respuesta final: {e}"
