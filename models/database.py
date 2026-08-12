# models/database.py
import os
import random
import shutil
import sqlite3
from datetime import datetime

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


def crear_respaldo():
    """Copia jugueteria.db a database/respaldos/ con la fecha y hora del
    momento en el nombre (ej. jugueteria_20260809_131500.db). A diferencia
    de las migraciones (que ya no respaldan solas, ver comentarios mas
    abajo), este respaldo es bajo demanda: lo dispara el boton "Hacer
    respaldo" de Gestion de Archivos (ver controllers/archivos_controller.py).
    Devuelve (ruta_completa, nombre_archivo)."""
    os.makedirs(Config.RESPALDOS_FOLDER, exist_ok=True)

    marca_tiempo = datetime.now().strftime('%Y%m%d_%H%M%S')
    nombre_archivo = f"jugueteria_{marca_tiempo}.db"
    ruta_completa = os.path.join(Config.RESPALDOS_FOLDER, nombre_archivo)

    shutil.copy2(Config.DATABASE, ruta_completa)
    return ruta_completa, nombre_archivo


def migrar_columna_unidad_venta():
    """Agrega la columna `unidad_venta` a detalle_ventas si todavia no existe
    (bases creadas antes de la funcionalidad de venta por piezas fraccionadas).
    Idempotente: no hace nada si la columna ya esta. El respaldo de la base
    es manual (boton "Hacer respaldo" en Gestion de Archivos, ver
    crear_respaldo), no automatico en cada migracion."""
    conexion = obtener_conexion()
    columnas = [fila['name'] for fila in conexion.execute("PRAGMA table_info(detalle_ventas)")]

    if 'unidad_venta' in columnas:
        conexion.close()
        return

    print("🟡 Actualizando esquema: agregando columna 'unidad_venta' a detalle_ventas...")

    conexion.execute(
        "ALTER TABLE detalle_ventas ADD COLUMN unidad_venta TEXT "
        "CHECK(unidad_venta IN ('pieza', 'cuarta', 'media', 'docena', 'paquete', 'caja'))"
    )
    conexion.commit()
    conexion.close()
    print("🟢 Esquema actualizado correctamente.")


def migrar_columna_codigo_venta():
    """Agrega la columna `codigo_venta` (unica) a ventas si todavia no existe,
    y rellena con un codigo generado cada venta previa a esta funcionalidad
    (usando su propia fecha_venta), para que tambien queden buscables por
    codigo. Idempotente (mismo criterio que migrar_columna_unidad_venta)."""
    conexion = obtener_conexion()
    columnas = [fila['name'] for fila in conexion.execute("PRAGMA table_info(ventas)")]

    if 'codigo_venta' in columnas:
        conexion.close()
        return

    print("🟡 Actualizando esquema: agregando columna 'codigo_venta' a ventas...")

    conexion.execute("ALTER TABLE ventas ADD COLUMN codigo_venta TEXT")
    conexion.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ventas_codigo_venta ON ventas(codigo_venta)"
    )

    ventas_sin_codigo = conexion.execute(
        "SELECT id_venta, fecha_venta FROM ventas WHERE codigo_venta IS NULL"
    ).fetchall()
    for venta in ventas_sin_codigo:
        fecha = venta['fecha_venta'] or datetime.now().strftime('%Y-%m-%d')
        prefijo = f"VTA-{fecha.replace('-', '')}"
        while True:
            codigo = f"{prefijo}-{random.randint(0, 9999):04d}"
            existe = conexion.execute(
                "SELECT 1 FROM ventas WHERE codigo_venta = ?", (codigo,)
            ).fetchone()
            if not existe:
                break
        conexion.execute(
            "UPDATE ventas SET codigo_venta = ? WHERE id_venta = ?", (codigo, venta['id_venta'])
        )

    conexion.commit()
    conexion.close()
    print(f"🟢 Esquema actualizado: {len(ventas_sin_codigo)} venta(s) existentes recibieron codigo.")


def migrar_columna_factura_movil():
    """Agrega las columnas `numero_factura` y `foto_factura` a ventas si
    todavia no existen (bases creadas antes de la app movil de ventas por
    QR). Idempotente: no hace nada si las columnas ya estan."""
    conexion = obtener_conexion()
    columnas = [fila['name'] for fila in conexion.execute("PRAGMA table_info(ventas)")]

    if 'numero_factura' in columnas:
        conexion.close()
        return

    print("🟡 Actualizando esquema: agregando columnas 'numero_factura' y 'foto_factura' a ventas...")

    conexion.execute("ALTER TABLE ventas ADD COLUMN numero_factura TEXT")
    conexion.execute("ALTER TABLE ventas ADD COLUMN foto_factura TEXT")
    conexion.commit()
    conexion.close()
    print("🟢 Esquema actualizado: columnas de factura movil agregadas a ventas.")


def migrar_permitir_stock_negativo():
    """Permite que productos.cantidad quede en negativo (= faltante a
    reponer del almacen, ver alerta en Inicio). SQLite no permite quitar
    un CHECK con ALTER TABLE, asi que hay que reconstruir la tabla
    completa (patron recomendado por SQLite: crear nueva, copiar datos,
    borrar la vieja, renombrar). Idempotente: revisa el SQL guardado de
    la tabla y si el CHECK viejo ya no esta, no hace nada. Antes de correr
    una migracion asi (reconstruye tablas) conviene sacar un respaldo
    manual desde Gestion de Archivos."""
    conexion = obtener_conexion()
    definicion_actual = conexion.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='productos'"
    ).fetchone()['sql']

    if 'cantidad >= 0' not in definicion_actual:
        conexion.close()
        return

    print("🟡 Actualizando esquema: permitiendo stock negativo en productos (faltante a reponer)...")

    conexion.execute("PRAGMA foreign_keys = OFF")
    conexion.execute("BEGIN")
    try:
        conexion.execute("""
            CREATE TABLE productos_nueva (
                id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
                foto_url TEXT,
                nombre TEXT NOT NULL,
                codigo_1 TEXT UNIQUE NOT NULL,
                codigo_2 TEXT,
                descripcion TEXT,
                marca TEXT,
                precio_unidad_facturado REAL DEFAULT 0,
                precio_docena_facturado REAL DEFAULT 0,
                precio_paquete_facturado REAL DEFAULT 0,
                precio_paquete_neto REAL DEFAULT 0,
                precio_docena_neto REAL DEFAULT 0,
                precio_docena_comercial REAL DEFAULT 0,
                descuento_porcentaje REAL DEFAULT 0,
                incremento_porcentaje REAL DEFAULT 0,
                pcs_paquete INTEGER DEFAULT 0,
                pcs_caja INTEGER DEFAULT 0,
                venta_fraccionada TEXT DEFAULT 'No' CHECK(venta_fraccionada IN ('Si', 'No')),
                id_ubicacion INTEGER REFERENCES ubicaciones(id_ubicacion),
                posicion TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                estado TEXT DEFAULT 'Activo' CHECK(estado IN ('Activo', 'Inactivo'))
            )
        """)
        conexion.execute("INSERT INTO productos_nueva SELECT * FROM productos")
        conexion.execute("DROP TABLE productos")
        conexion.execute("ALTER TABLE productos_nueva RENAME TO productos")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_prod_codigo1 ON productos(codigo_1)")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_prod_codigo2 ON productos(codigo_2)")

        problemas = conexion.execute("PRAGMA foreign_key_check").fetchall()
        if problemas:
            raise RuntimeError(f"foreign_key_check encontro problemas tras la migracion: {problemas}")

        conexion.execute("COMMIT")
    except Exception:
        conexion.execute("ROLLBACK")
        raise
    finally:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.close()

    print("🟢 Esquema actualizado: productos.cantidad ahora admite valores negativos.")


def migrar_codigo1_no_unico():
    """codigo_1 dejaba de identificar un producto de forma confiable: el
    cliente confirmo que se repite entre productos distintos en su catalogo
    real. Esta migracion le saca el UNIQUE a codigo_1 solo y en su lugar
    exige que la COMBINACION codigo_1 + codigo_2 sea unica (dos productos
    reales distintos compartiendo ambos codigos a la vez es practicamente
    imposible). Sin esto, importar el catalogo completo por Excel podia
    pisar silenciosamente un producto con los datos de otro que compartiera
    codigo_1 (ver models/productos_model.py: guardar_o_actualizar_desde_excel
    matcheaba solo por codigo_1). Mismo patron de reconstruccion de tabla
    que las migraciones anteriores. Idempotente."""
    conexion = obtener_conexion()
    definicion_actual = conexion.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='productos'"
    ).fetchone()['sql']

    if 'codigo_1 TEXT UNIQUE NOT NULL' not in definicion_actual:
        conexion.close()
        return

    print("🟡 Actualizando esquema: codigo_1 ya no es unico por si solo, ahora lo es junto a codigo_2...")

    conexion.execute("PRAGMA foreign_keys = OFF")
    conexion.execute("BEGIN")
    try:
        conexion.execute("""
            CREATE TABLE productos_nueva (
                id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
                foto_url TEXT,
                nombre TEXT NOT NULL,
                codigo_1 TEXT NOT NULL,
                codigo_2 TEXT,
                descripcion TEXT,
                marca TEXT,
                precio_unidad_facturado REAL DEFAULT 0,
                precio_docena_facturado REAL DEFAULT 0,
                precio_paquete_facturado REAL DEFAULT 0,
                precio_paquete_neto REAL DEFAULT 0,
                precio_docena_neto REAL DEFAULT 0,
                precio_docena_comercial REAL DEFAULT 0,
                descuento_porcentaje REAL DEFAULT 0,
                incremento_porcentaje REAL DEFAULT 0,
                pcs_paquete INTEGER DEFAULT 0,
                pcs_caja INTEGER DEFAULT 0,
                venta_fraccionada TEXT DEFAULT 'No' CHECK(venta_fraccionada IN ('Si', 'No')),
                id_ubicacion INTEGER REFERENCES ubicaciones(id_ubicacion),
                posicion TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                estado TEXT DEFAULT 'Activo' CHECK(estado IN ('Activo', 'Inactivo')),
                UNIQUE(codigo_1, codigo_2)
            )
        """)
        conexion.execute("INSERT INTO productos_nueva SELECT * FROM productos")
        conexion.execute("DROP TABLE productos")
        conexion.execute("ALTER TABLE productos_nueva RENAME TO productos")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_prod_codigo1 ON productos(codigo_1)")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_prod_codigo2 ON productos(codigo_2)")

        problemas = conexion.execute("PRAGMA foreign_key_check").fetchall()
        if problemas:
            raise RuntimeError(f"foreign_key_check encontro problemas tras la migracion: {problemas}")

        conexion.execute("COMMIT")
    except Exception:
        conexion.execute("ROLLBACK")
        raise
    finally:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.close()

    print("🟢 Esquema actualizado: codigo_1 + codigo_2 ahora identifican un producto de forma unica (codigo_1 solo, ya no).")


def migrar_roles_personal():
    """Reemplaza los 3 roles viejos (Administrador/Empleado/Cajero) por los
    4 nuevos (Super Admin/Admin/Empleado/Bodega), remapeando los datos
    existentes: Administrador->Super Admin, Cajero->Empleado (Empleado
    queda igual). Mismo patron de reconstruccion de tabla que las
    migraciones anteriores, pero esta vez ademas transforma los valores
    durante la copia (via CASE) en vez de solo relajar una restriccion.
    Idempotente."""
    conexion = obtener_conexion()
    definicion_actual = conexion.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='personal'"
    ).fetchone()['sql']

    if 'Administrador' not in definicion_actual:
        conexion.close()
        return

    print("🟡 Actualizando esquema: migrando roles de personal a Super Admin/Admin/Empleado/Bodega...")

    conexion.execute("PRAGMA foreign_keys = OFF")
    conexion.execute("BEGIN")
    try:
        conexion.execute("""
            CREATE TABLE personal_nueva (
                id_personal INTEGER PRIMARY KEY AUTOINCREMENT,
                nombres TEXT NOT NULL,
                apellido_paterno TEXT NOT NULL,
                apellido_materno TEXT,
                ci TEXT UNIQUE NOT NULL,
                telefono TEXT,
                usuario TEXT UNIQUE NOT NULL,
                contrasena_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK(rol IN ('Super Admin', 'Admin', 'Empleado', 'Bodega')),
                estado INTEGER DEFAULT 1 CHECK(estado IN (0, 1))
            )
        """)
        conexion.execute("""
            INSERT INTO personal_nueva
                (id_personal, nombres, apellido_paterno, apellido_materno, ci, telefono,
                 usuario, contrasena_hash, rol, estado)
            SELECT
                id_personal, nombres, apellido_paterno, apellido_materno, ci, telefono,
                usuario, contrasena_hash,
                CASE rol
                    WHEN 'Administrador' THEN 'Super Admin'
                    WHEN 'Cajero' THEN 'Empleado'
                    ELSE rol
                END,
                estado
            FROM personal
        """)
        conexion.execute("DROP TABLE personal")
        conexion.execute("ALTER TABLE personal_nueva RENAME TO personal")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_personal_ci ON personal(ci)")

        problemas = conexion.execute("PRAGMA foreign_key_check").fetchall()
        if problemas:
            raise RuntimeError(f"foreign_key_check encontro problemas tras la migracion: {problemas}")

        conexion.execute("COMMIT")
    except Exception:
        conexion.execute("ROLLBACK")
        raise
    finally:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.close()

    print("🟢 Esquema actualizado: roles de personal migrados correctamente.")


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
        migrar_columna_unidad_venta()
        migrar_columna_codigo_venta()
        migrar_permitir_stock_negativo()
        migrar_codigo1_no_unico()
        migrar_roles_personal()
        migrar_columna_factura_movil()