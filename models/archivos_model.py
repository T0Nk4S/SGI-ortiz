"""
archivos_model.py
Capa de acceso a datos (Model) de la pestana Gestion de Archivos.
Registra, en orden de llegada, cada archivo Excel que el cliente
importa desde Productos.
"""
from models.database import get_db
from utilities.utilities import resolver_orden_sql

# Whitelist de ordenamientos disponibles para el historial de Gestion de
# Archivos (ver resolver_orden_sql).
ORDENES_ARCHIVOS = {
    'fecha_desc': 'a.id_archivo DESC',
    'fecha_asc': 'a.id_archivo ASC',
    'registros_desc': 'a.registros_procesados DESC',
    'registros_asc': 'a.registros_procesados ASC',
}
ORDEN_ARCHIVOS_DEFAULT = 'fecha_desc'


def registrar_archivo(nombre_original, nombre_guardado, id_personal, registros_procesados):
    """Guarda en el historial un archivo recien importado."""
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO archivos_importados (
            nombre_original, nombre_guardado, id_personal, registros_procesados
        ) VALUES (?, ?, ?, ?)
        """,
        (nombre_original, nombre_guardado, id_personal, registros_procesados),
    )
    db.commit()
    return cursor.lastrowid


def get_archivo(id_archivo):
    """Un registro puntual del historial, para resolver su descarga
    (ver archivos_controller.descargar_importacion)."""
    db = get_db()
    return db.execute(
        "SELECT * FROM archivos_importados WHERE id_archivo = ?", (id_archivo,)
    ).fetchone()


def get_all_archivos(busqueda=None, orden=None):
    """Historial completo de archivos importados, con busqueda y
    ordenamiento opcionales (ver ORDENES_ARCHIVOS; por defecto, del mas
    reciente al mas antiguo)."""
    db = get_db()
    query = """
        SELECT a.*, per.nombres || ' ' || per.apellido_paterno AS personal_nombre
        FROM archivos_importados a
        LEFT JOIN personal per ON per.id_personal = a.id_personal
        WHERE 1 = 1
    """
    params = []

    if busqueda:
        query += " AND a.nombre_original LIKE ?"
        params.append(f"%{busqueda}%")

    orden_sql = resolver_orden_sql(orden, ORDENES_ARCHIVOS, ORDEN_ARCHIVOS_DEFAULT)
    query += f" ORDER BY {orden_sql}"
    return db.execute(query, params).fetchall()
