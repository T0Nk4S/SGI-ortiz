"""
productos_model.py
Capa de acceso a datos (Model) exclusiva de la pestana Productos.
No debe contener logica de rutas ni de renderizado de vistas.
"""
from models import movimientos_model
from models.database import get_db, obtener_conexion


def get_all_productos(estado=None, busqueda=None):
    """Lista productos, con filtro opcional por estado y por texto
    (busca en nombre, codigo_1 y codigo_2)."""
    db = get_db()
    query = """
        SELECT p.*, u.nombre AS ubicacion_nombre
        FROM productos p
        LEFT JOIN ubicaciones u ON p.id_ubicacion = u.id_ubicacion
        WHERE 1 = 1
    """
    params = []

    if estado:
        query += " AND p.estado = ?"
        params.append(estado)

    if busqueda:
        query += " AND (p.nombre LIKE ? OR p.codigo_1 LIKE ? OR p.codigo_2 LIKE ?)"
        like = f"%{busqueda}%"
        params.extend([like, like, like])

    query += " ORDER BY p.nombre ASC"

    return db.execute(query, params).fetchall()


def get_producto(id_producto):
    """Obtiene un solo producto por su id, incluyendo el nombre de la ubicacion."""
    db = get_db()
    return db.execute(
        """
        SELECT p.*, u.nombre AS ubicacion_nombre
        FROM productos p
        LEFT JOIN ubicaciones u ON p.id_ubicacion = u.id_ubicacion
        WHERE p.id_producto = ?
        """,
        (id_producto,),
    ).fetchone()


def contar_productos():
    """Conteo rapido del catalogo, usado para el contador del sidebar."""
    db = get_db()
    return db.execute("SELECT COUNT(*) AS c FROM productos").fetchone()['c']


def get_ubicaciones():
    """Devuelve todas las ubicaciones disponibles para el select del formulario."""
    db = get_db()
    return db.execute("SELECT * FROM ubicaciones ORDER BY nombre ASC").fetchall()


def create_producto(data):
    """Inserta un nuevo producto. `data` es un dict con las llaves del formulario."""
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO productos (
            foto_url, nombre, codigo_1, codigo_2, descripcion, marca,
            precio_unidad_facturado, precio_docena_facturado, precio_paquete_facturado,
            precio_paquete_neto, precio_docena_neto, precio_docena_comercial,
            id_ubicacion, cantidad, pcs_paquete, pcs_caja, posicion,
            venta_fraccionada, descuento_porcentaje, incremento_porcentaje, estado
        ) VALUES (
            :foto_url, :nombre, :codigo_1, :codigo_2, :descripcion, :marca,
            :precio_unidad_facturado, :precio_docena_facturado, :precio_paquete_facturado,
            :precio_paquete_neto, :precio_docena_neto, :precio_docena_comercial,
            :id_ubicacion, :cantidad, :pcs_paquete, :pcs_caja, :posicion,
            :venta_fraccionada, :descuento_porcentaje, :incremento_porcentaje, :estado
        )
        """,
        data,
    )
    db.commit()
    return cursor.lastrowid


def update_producto(id_producto, data):
    """Actualiza todos los campos editables de un producto existente."""
    db = get_db()
    data = dict(data)
    data['id_producto'] = id_producto
    db.execute(
        """
        UPDATE productos SET
            foto_url = :foto_url,
            nombre = :nombre,
            codigo_1 = :codigo_1,
            codigo_2 = :codigo_2,
            descripcion = :descripcion,
            marca = :marca,
            precio_unidad_facturado = :precio_unidad_facturado,
            precio_docena_facturado = :precio_docena_facturado,
            precio_paquete_facturado = :precio_paquete_facturado,
            precio_paquete_neto = :precio_paquete_neto,
            precio_docena_neto = :precio_docena_neto,
            precio_docena_comercial = :precio_docena_comercial,
            id_ubicacion = :id_ubicacion,
            cantidad = :cantidad,
            pcs_paquete = :pcs_paquete,
            pcs_caja = :pcs_caja,
            posicion = :posicion,
            venta_fraccionada = :venta_fraccionada,
            descuento_porcentaje = :descuento_porcentaje,
            incremento_porcentaje = :incremento_porcentaje
        WHERE id_producto = :id_producto
        """,
        data,
    )
    db.commit()


def delete_producto(id_producto):
    """Elimina definitivamente un producto de la base de datos.
    NOTA: si el producto ya tiene ventas o movimientos asociados, esto
    fallara por restriccion de llave foranea (a proposito, para proteger
    el historial). En ese caso, usar cambiar_estado() para desactivarlo."""
    db = get_db()
    db.execute("DELETE FROM productos WHERE id_producto = ?", (id_producto,))
    db.commit()


def cambiar_estado(id_producto):
    """Alterna el estado de un producto entre Activo <-> Inactivo."""
    db = get_db()
    producto = db.execute(
        "SELECT estado FROM productos WHERE id_producto = ?", (id_producto,)
    ).fetchone()
    if producto:
        nuevo_estado = 'Inactivo' if producto['estado'] == 'Activo' else 'Activo'
        db.execute(
            "UPDATE productos SET estado = ? WHERE id_producto = ?",
            (nuevo_estado, id_producto),
        )
        db.commit()


def get_estadisticas():
    """Estadisticas basicas para el dashboard (Inicio).
    'Sin stock' se calcula al vuelo (cantidad = 0), no se guarda en la BD."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS c FROM productos").fetchone()['c']
    activos = db.execute(
        "SELECT COUNT(*) AS c FROM productos WHERE estado = 'Activo'"
    ).fetchone()['c']
    inactivos = db.execute(
        "SELECT COUNT(*) AS c FROM productos WHERE estado = 'Inactivo'"
    ).fetchone()['c']
    sin_stock = db.execute(
        "SELECT COUNT(*) AS c FROM productos WHERE cantidad = 0"
    ).fetchone()['c']
    stock_total = db.execute(
        "SELECT COALESCE(SUM(cantidad), 0) AS s FROM productos"
    ).fetchone()['s']
    ultimos_productos = db.execute(
        "SELECT * FROM productos ORDER BY id_producto DESC LIMIT 5"
    ).fetchall()

    return {
        'total': total,
        'activos': activos,
        'inactivos': inactivos,
        'sin_stock': sin_stock,
        'stock_total': stock_total,
        'ultimos_productos': ultimos_productos,
    }

def obtener_todos_los_productos():
    """Compatibilidad con el controlador de import/export Excel/PDF."""
    db = get_db()
    return db.execute(
        """
        SELECT
            p.codigo_1,
            p.nombre,
            p.precio_unidad_facturado AS precio_venta,
            p.precio_unidad_facturado AS costo,
            p.cantidad AS stock
        FROM productos p
        ORDER BY p.nombre ASC
        """
    ).fetchall()


def guardar_o_actualizar_desde_excel(datos=None, nombre=None, precio=None, costo=None, stock=None, id_personal=None):
    """Procesa una fila importada de Excel y la persiste en SQLite.

    Acepta dos formatos compatibles:
    1) un dict con campos del Excel ya normalizados
    2) la firma legacy (codigo, nombre, precio, costo, stock)

    Si se entrega `id_personal`, cada cambio de stock queda registrado en
    el Kardex (AJUSTE_INVENTARIO si el producto ya existia, INGRESO_MERCADERIA
    si se crea uno nuevo con stock inicial)."""
    if isinstance(datos, dict):
        data = dict(datos)
        codigo = data.get('codigo_1') or data.get('codigo')
    else:
        codigo = datos
        data = {
            'codigo_1': codigo,
            'nombre': nombre,
            'codigo_2': None,
            'descripcion': '',
            'marca': '',
            'precio_unidad_facturado': float(precio or 0),
            'precio_docena_facturado': 0,
            'precio_paquete_facturado': 0,
            'precio_paquete_neto': 0,
            'precio_docena_neto': 0,
            'precio_docena_comercial': 0,
            'descuento_porcentaje': 0,
            'incremento_porcentaje': 0,
            'pcs_paquete': 0,
            'pcs_caja': 0,
            'venta_fraccionada': 'No',
            'ubicacion_nombre': None,
            'posicion': '',
            'cantidad': int(stock or 0),
        }

    data.setdefault('codigo_1', codigo)
    data.setdefault('codigo_2', '')
    data.setdefault('descripcion', '')
    data.setdefault('marca', '')
    data.setdefault('precio_unidad_facturado', 0)
    data.setdefault('precio_docena_facturado', 0)
    data.setdefault('precio_paquete_facturado', 0)
    data.setdefault('precio_paquete_neto', 0)
    data.setdefault('precio_docena_neto', 0)
    data.setdefault('precio_docena_comercial', 0)
    data.setdefault('descuento_porcentaje', 0)
    data.setdefault('incremento_porcentaje', 0)
    data.setdefault('pcs_paquete', 0)
    data.setdefault('pcs_caja', 0)
    data.setdefault('venta_fraccionada', 'No')
    data.setdefault('ubicacion_nombre', None)
    data.setdefault('posicion', '')
    data.setdefault('cantidad', 0)

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # 1. Resolver o insertar la ubicación si viene especificada
    id_ubicacion = None
    if data.get('ubicacion_nombre'):
        cursor.execute(
            "SELECT id_ubicacion FROM ubicaciones WHERE nombre = ?",
            (data['ubicacion_nombre'],),
        )
        ub = cursor.fetchone()
        if ub:
            id_ubicacion = ub['id_ubicacion']
        else:
            cursor.execute(
                "INSERT INTO ubicaciones (nombre) VALUES (?)",
                (data['ubicacion_nombre'],),
            )
            id_ubicacion = cursor.lastrowid

    # 2. Verificar si el producto ya existe por codigo_1
    cursor.execute(
        "SELECT id_producto, cantidad FROM productos WHERE codigo_1 = ?",
        (data['codigo_1'],),
    )
    existente = cursor.fetchone()

    if existente:
        query = """
            UPDATE productos SET
                nombre = ?,
                codigo_2 = ?,
                descripcion = ?,
                marca = ?,
                precio_unidad_facturado = ?,
                precio_docena_facturado = ?,
                precio_paquete_facturado = ?,
                precio_paquete_neto = ?,
                precio_docena_neto = ?,
                precio_docena_comercial = ?,
                descuento_porcentaje = ?,
                incremento_porcentaje = ?,
                pcs_paquete = ?,
                pcs_caja = ?,
                venta_fraccionada = ?,
                id_ubicacion = ?,
                posicion = ?,
                cantidad = ?
            WHERE codigo_1 = ?
        """
        params = (
            data['nombre'],
            data['codigo_2'],
            data['descripcion'],
            data['marca'],
            data['precio_unidad_facturado'],
            data['precio_docena_facturado'],
            data['precio_paquete_facturado'],
            data['precio_paquete_neto'],
            data['precio_docena_neto'],
            data['precio_docena_comercial'],
            data['descuento_porcentaje'],
            data['incremento_porcentaje'],
            data['pcs_paquete'],
            data['pcs_caja'],
            data['venta_fraccionada'],
            id_ubicacion,
            data['posicion'],
            data['cantidad'],
            data['codigo_1'],
        )
        cursor.execute(query, params)
        diferencia_cantidad = data['cantidad'] - existente['cantidad']
    else:
        query = """
            INSERT INTO productos (
                nombre, codigo_1, codigo_2, descripcion, marca,
                precio_unidad_facturado, precio_docena_facturado,
                precio_paquete_facturado, precio_paquete_neto,
                precio_docena_neto, precio_docena_comercial,
                descuento_porcentaje, incremento_porcentaje,
                pcs_paquete, pcs_caja, venta_fraccionada,
                id_ubicacion, posicion, cantidad
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data['nombre'],
            data['codigo_1'],
            data['codigo_2'],
            data['descripcion'],
            data['marca'],
            data['precio_unidad_facturado'],
            data['precio_docena_facturado'],
            data['precio_paquete_facturado'],
            data['precio_paquete_neto'],
            data['precio_docena_neto'],
            data['precio_docena_comercial'],
            data['descuento_porcentaje'],
            data['incremento_porcentaje'],
            data['pcs_paquete'],
            data['pcs_caja'],
            data['venta_fraccionada'],
            id_ubicacion,
            data['posicion'],
            data['cantidad'],
        )
        cursor.execute(query, params)
        nuevo_id_producto = cursor.lastrowid

    conexion.commit()
    conexion.close()

    if id_personal:
        if existente and diferencia_cantidad != 0:
            movimientos_model.registrar_movimiento(
                id_producto=existente['id_producto'],
                id_personal=id_personal,
                tipo_movimiento='AJUSTE_INVENTARIO',
                cantidad=diferencia_cantidad,
                motivo_nota='Importacion desde Excel',
            )
        elif not existente and data['cantidad'] > 0:
            movimientos_model.registrar_movimiento(
                id_producto=nuevo_id_producto,
                id_personal=id_personal,
                tipo_movimiento='INGRESO_MERCADERIA',
                cantidad=data['cantidad'],
                motivo_nota='Alta de producto via importacion Excel',
            )