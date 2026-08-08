"""
archivos_model.py
Capa de acceso a datos (Model) de la pestana Gestion de Archivos.
Registra, en orden de llegada, cada archivo Excel que el cliente
importa desde Productos.
"""
from models.database import get_db


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


def get_all_archivos(busqueda=None):
    """Historial completo de archivos importados, del mas reciente al
    mas antiguo (el orden de llegada queda preservado por id_archivo)."""
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

    query += " ORDER BY a.id_archivo DESC"
    return db.execute(query, params).fetchall()
