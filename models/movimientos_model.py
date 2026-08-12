"""
movimientos_model.py
Capa de acceso a datos para el historial de movimientos / Kardex.
"""
from models.database import get_db
from utilities.utilities import resolver_orden_sql

# Whitelist de ordenamientos disponibles para el Kardex (ver resolver_orden_sql).
ORDENES_MOVIMIENTOS = {
    'fecha_desc': 'm.fecha DESC, m.id_movimiento DESC',
    'fecha_asc': 'm.fecha ASC, m.id_movimiento ASC',
    'cantidad_desc': 'm.cantidad DESC',
    'cantidad_asc': 'm.cantidad ASC',
    'producto_asc': 'p.nombre COLLATE NOCASE ASC',
    'producto_desc': 'p.nombre COLLATE NOCASE DESC',
}
ORDEN_MOVIMIENTOS_DEFAULT = 'fecha_desc'


def registrar_movimiento(id_producto, id_personal, tipo_movimiento, cantidad,
                          motivo_nota=None, id_venta=None, id_proveedor=None):
    """Inserta una fila en el Kardex. `cantidad` va siempre con signo:
    positivo para entradas (INGRESO_MERCADERIA, GARANTIA_ENTRADA, ajustes
    hacia arriba) y negativo para salidas (SALIDA_VENTA, GARANTIA_BAJA,
    DEVOLUCION_PROVEEDOR, ajustes hacia abajo)."""
    db = get_db()
    db.execute(
        """
        INSERT INTO movimientos (
            id_producto, id_personal, id_venta, id_proveedor,
            tipo_movimiento, cantidad, motivo_nota
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (id_producto, id_personal, id_venta, id_proveedor, tipo_movimiento, cantidad, motivo_nota),
    )
    db.commit()


def get_movimientos(busqueda=None, tipo_movimiento=None, orden=None):
    """Devuelve el kardex de movimientos, con filtros de texto, tipo y
    ordenamiento (ver ORDENES_MOVIMIENTOS)."""
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

    orden_sql = resolver_orden_sql(orden, ORDENES_MOVIMIENTOS, ORDEN_MOVIMIENTOS_DEFAULT)
    query += f" ORDER BY {orden_sql}"
    return db.execute(query, params).fetchall()
