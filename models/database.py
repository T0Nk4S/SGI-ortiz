# models/database.py
import os
import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash

from config import Config


def obtener_conexion():
    """Retorna una conexión a la base de datos SQLite con soporte para diccionarios."""
    conexion = sqlite3.connect(Config.DATABASE)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON;")
    return conexion


def get_db():
    """Devuelve la conexión a la base de datos para la request actual."""
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(e=None):
    """Cierra la conexión del request al salir de la request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Crea las tablas si no existen usando schema.sql."""
    os.makedirs(os.path.dirname(current_app.config['DATABASE']), exist_ok=True)
    db = get_db()
    with open(current_app.config['SCHEMA'], 'r', encoding='utf-8') as f:
        db.executescript(f.read())
    db.commit()


def init_app(app):
    """Registra el cierre automático de cada request."""
    app.teardown_appcontext(close_db)


def asegurar_password_admin_por_defecto():
    """La contrasena semilla del usuario admin en schema.sql queda como
    placeholder ('temporal', sin hash) porque SQL puro no puede generar
    un hash de Werkzeug. En el primer arranque sobre una BD nueva, esta
    funcion la reemplaza por el hash real de 'admin123' para que el
    primer ingreso funcione. El administrador real debe cambiar esa
    contrasena desde la pantalla de Usuarios apenas ingrese."""
    db = get_db()
    fila = db.execute(
        "SELECT id_personal FROM personal WHERE usuario = 'admin' AND contrasena_hash = 'temporal'"
    ).fetchone()
    if fila:
        db.execute(
            "UPDATE personal SET contrasena_hash = ? WHERE id_personal = ?",
            (generate_password_hash('admin123'), fila['id_personal']),
        )
        db.commit()


def inicializar_base_de_datos():
    """
    Verifica si la base de datos existe.
    Si no existe, crea la carpeta database/ si hace falta y ejecuta schema.sql.
    Si ya existe, la ignora para conservar los datos.
    """
    db_dir = os.path.dirname(Config.DATABASE)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    if not os.path.exists(Config.DATABASE):
        print("🟡 Base de datos no encontrada. Inicializando esquema...")
        if os.path.exists(Config.SCHEMA):
            try:
                conexion = obtener_conexion()
                with open(Config.SCHEMA, 'r', encoding='utf-8') as file:
                    script_sql = file.read()

                cursor = conexion.cursor()
                cursor.executescript(script_sql)
                conexion.commit()
                conexion.close()
                print(f"🟢 Base de datos creada e inicializada en: {Config.DATABASE}")
            except Exception as e:
                print(f"🔴 Error al inicializar la base de datos: {e}")
        else:
            print(f"🔴 Error: No se encontró el archivo schema.sql en {Config.SCHEMA}")
    else:
        print("🟢 La base de datos ya existe. Conexión lista.")