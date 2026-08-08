"""
movimientos_model.py
Capa de acceso a datos para el historial de movimientos / Kardex.
"""
from models.database import get_db


def get_movimientos(busqueda=None, tipo_movimiento=None):
    """Devuelve el kardex de movimientos, con filtros de texto y tipo."""
    db = get_db()
    query = """
        SELECT m.*, p.nombre AS producto_nombre, p.codigo_1 AS codigo_1,
               per.nombres || ' ' || per.apellido_paterno AS personal_nombre,
               prov.nombre AS proveedor_nombre
        FROM movimientos m
        JOIN productos p ON p.id_producto = m.id_producto
        LEFT JOIN personal per ON per.id_personal = m.id_personal
        LEFT JOIN proveedores prov ON prov.id_proveedor = m.id_proveedor
        WHERE 1 = 1
    """
    params = []

    if busqueda:
        like = f"%{busqueda}%"
        query += " AND (p.nombre LIKE ? OR p.codigo_1 LIKE ? OR p.codigo_2 LIKE ? OR m.motivo_nota LIKE ?)"
        params.extend([like, like, like, like])

    if tipo_movimiento:
        query += " AND m.tipo_movimiento = ?"
        params.append(tipo_movimiento)

    query += " ORDER BY m.fecha DESC, m.id_movimiento DESC"
    return db.execute(query, params).fetchall()
