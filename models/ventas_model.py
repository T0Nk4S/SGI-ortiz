"""
ventas_model.py
Capa de acceso a datos (Model) exclusiva de la pestana Ventas.

Estructura: cada venta es un ENCABEZADO (tabla ventas) que tiene una o
varias LINEAS (tabla detalle_ventas) -> soporta tanto la venta de un
solo producto como un carrito con varios productos distintos, cada uno
pudiendo usar una tarifa distinta (PUF, PDF, PPF, PPN, PDN, PDC o un
precio personalizado).

Reglas de negocio que implementa:
- Toda venta nace en estado 'Pendiente' junto con sus lineas de detalle.
- Si se aprueba, pasa a 'Aprobada' (se conserva permanentemente) y se
  descuenta el stock de cada producto vendido.
- Si se rechaza ('Rechazada'), el encabezado se ELIMINA y sus lineas se
  eliminan en cascada (no se conserva historial de rechazadas).
"""
from models import movimientos_model
from models.database import get_db

# Relacion entre el tipo de precio aplicado y la columna correspondiente
# en la tabla productos. 'PERSONALIZADO' no mapea a ninguna columna:
# su precio se captura manualmente al momento de la venta.
CAMPO_POR_TIPO_PRECIO = {
    'PUF': 'precio_unidad_facturado',
    'PDF': 'precio_docena_facturado',
    'PPF': 'precio_paquete_facturado',
    'PPN': 'precio_paquete_neto',
    'PDN': 'precio_docena_neto',
    'PDC': 'precio_docena_comercial',
}


def _adjuntar_detalle(db, ventas_rows):
    """Dado un listado de encabezados de venta, adjunta a cada uno su
    lista de lineas (productos) y los datos de personal involucrado.
    Devuelve una lista de diccionarios (no sqlite3.Row, porque anexamos campos)."""
    resultado = []
    for venta in ventas_rows:
        venta_dict = dict(venta)

        lineas = db.execute(
            """
            SELECT d.*, p.nombre AS producto_nombre, p.foto_url AS producto_foto
            FROM detalle_ventas d
            JOIN productos p ON d.id_producto = p.id_producto
            WHERE d.id_venta = ?
            ORDER BY d.id_detalle ASC
            """,
            (venta_dict['id_venta'],),
        ).fetchall()
        venta_dict['detalle'] = lineas
        venta_dict['total_items'] = sum(l['cantidad'] for l in lineas)

        registrador = db.execute(
            "SELECT nombres, apellido_paterno FROM personal WHERE id_personal = ?",
            (venta_dict['id_personal_registro'],),
        ).fetchone()
        venta_dict['usuario_nombre'] = (
            f"{registrador['nombres']} {registrador['apellido_paterno']}" if registrador else '-'
        )

        if venta_dict['id_personal_aprobador']:
            aprobador = db.execute(
                "SELECT nombres, apellido_paterno FROM personal WHERE id_personal = ?",
                (venta_dict['id_personal_aprobador'],),
            ).fetchone()
            venta_dict['aprobador_nombre'] = (
                f"{aprobador['nombres']} {aprobador['apellido_paterno']}" if aprobador else '-'
            )
        else:
            venta_dict['aprobador_nombre'] = None

        resultado.append(venta_dict)
    return resultado


def get_pendientes():
    """Ventas pendientes en orden FIFO (la mas antigua primero), con su detalle."""
    db = get_db()
    ventas = db.execute(
        "SELECT * FROM ventas WHERE estado = 'Pendiente' ORDER BY fecha_creacion ASC"
    ).fetchall()
    return _adjuntar_detalle(db, ventas)


def contar_pendientes():
    """Conteo rapido de ventas pendientes, usado para el badge del sidebar."""
    db = get_db()
    return db.execute(
        "SELECT COUNT(*) AS c FROM ventas WHERE estado = 'Pendiente'"
    ).fetchone()['c']


def get_aprobadas(busqueda=None):
    """Ventas aprobadas, ordenadas por orden de llegada, con su detalle.
    La busqueda filtra por cliente, carnet, usuario, ubicacion o nombre de producto."""
    db = get_db()

    if busqueda:
        like = f"%{busqueda}%"
        ids = db.execute(
            """
            SELECT DISTINCT v.id_venta
            FROM ventas v
            LEFT JOIN detalle_ventas d ON d.id_venta = v.id_venta
            LEFT JOIN productos p ON d.id_producto = p.id_producto
            LEFT JOIN personal per ON per.id_personal = v.id_personal_registro
            WHERE v.estado = 'Aprobada'
              AND (
                    v.cliente_nombre LIKE ? OR v.cliente_ci LIKE ?
                    OR v.ubicacion LIKE ? OR p.nombre LIKE ?
                    OR per.nombres LIKE ? OR per.apellido_paterno LIKE ?
              )
            ORDER BY v.fecha_creacion ASC
            """,
            (like, like, like, like, like, like),
        ).fetchall()
        id_list = [row['id_venta'] for row in ids]
        if not id_list:
            return []
        placeholders = ','.join('?' for _ in id_list)
        ventas = db.execute(
            f"SELECT * FROM ventas WHERE id_venta IN ({placeholders}) ORDER BY fecha_creacion ASC",
            id_list,
        ).fetchall()
    else:
        ventas = db.execute(
            "SELECT * FROM ventas WHERE estado = 'Aprobada' ORDER BY fecha_creacion ASC"
        ).fetchall()

    return _adjuntar_detalle(db, ventas)


def resolver_precio(producto, tipo_precio_aplicado, precio_personalizado=None):
    """Devuelve el precio unitario segun la tarifa elegida para una linea del carrito."""
    if tipo_precio_aplicado == 'PERSONALIZADO':
        return precio_personalizado or 0
    campo = CAMPO_POR_TIPO_PRECIO.get(tipo_precio_aplicado)
    return producto[campo] if campo else 0


# Orden de preferencia al sugerir una tarifa por defecto: si el producto
# se vende por piezas (venta_fraccionada = 'Si') tiene sentido cobrar por
# unidad primero; si solo se vende empaquetado, se prioriza paquete/docena.
_ORDEN_TARIFA_FRACCIONADO = ['PUF', 'PPF', 'PDF', 'PDN', 'PPN', 'PDC']
_ORDEN_TARIFA_PAQUETE = ['PPF', 'PDF', 'PDN', 'PPN', 'PDC', 'PUF']


def tarifas_disponibles(producto):
    """Tarifas que realmente tienen un precio cargado (> 0) para este
    producto puntual. Evita ofrecer/usar una tarifa en 0 por descuido."""
    return [
        tipo for tipo, campo in CAMPO_POR_TIPO_PRECIO.items()
        if (producto[campo] or 0) > 0
    ]


def tarifa_sugerida(producto):
    """Elige la tarifa por defecto al agregar un producto al carrito,
    respetando si el producto se vende por piezas o solo por paquete/docena.
    Si ninguna tarifa tiene precio cargado, sugiere PERSONALIZADO para
    forzar que el cajero indique el precio a mano (en vez de cobrar 0)."""
    disponibles = tarifas_disponibles(producto)
    if not disponibles:
        return 'PERSONALIZADO'

    orden = _ORDEN_TARIFA_FRACCIONADO if producto['venta_fraccionada'] == 'Si' else _ORDEN_TARIFA_PAQUETE
    for tarifa in orden:
        if tarifa in disponibles:
            return tarifa
    return disponibles[0]


def create_venta(data_header, items):
    """Crea una venta (encabezado) en estado Pendiente junto con sus lineas.
    `items` es una lista de dicts:
    [{'id_producto':.., 'cantidad':.., 'tipo_precio_aplicado':.., 'precio_aplicado':..}, ...]
    El total del encabezado se calcula como la suma de los subtotales."""
    db = get_db()

    total = sum(item['cantidad'] * item['precio_aplicado'] for item in items)
    data_header = dict(data_header)
    data_header['total'] = total

    cursor = db.execute(
        """
        INSERT INTO ventas (
            id_personal_registro, ubicacion, cliente_nombre, cliente_ci,
            observaciones, estado, fecha_venta, hora_venta, total
        ) VALUES (
            :id_personal_registro, :ubicacion, :cliente_nombre, :cliente_ci,
            :observaciones, 'Pendiente', :fecha_venta, :hora_venta, :total
        )
        """,
        data_header,
    )
    id_venta = cursor.lastrowid

    for item in items:
        subtotal = item['cantidad'] * item['precio_aplicado']
        db.execute(
            """
            INSERT INTO detalle_ventas (id_venta, id_producto, cantidad, tipo_precio_aplicado, precio_aplicado, subtotal)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (id_venta, item['id_producto'], item['cantidad'], item['tipo_precio_aplicado'], item['precio_aplicado'], subtotal),
        )

    db.commit()
    return id_venta


def aprobar_venta(id_venta, id_personal_aprobador):
    """Aprueba una venta pendiente, descuenta el stock de cada producto
    vendido y deja registrada la salida correspondiente en el Kardex."""
    db = get_db()

    lineas = db.execute(
        "SELECT id_producto, cantidad FROM detalle_ventas WHERE id_venta = ?", (id_venta,)
    ).fetchall()

    for linea in lineas:
        db.execute(
            "UPDATE productos SET cantidad = MAX(cantidad - ?, 0) WHERE id_producto = ?",
            (linea['cantidad'], linea['id_producto']),
        )
        movimientos_model.registrar_movimiento(
            id_producto=linea['id_producto'],
            id_personal=id_personal_aprobador,
            tipo_movimiento='SALIDA_VENTA',
            cantidad=-linea['cantidad'],
            motivo_nota=f'Venta aprobada #{id_venta}',
            id_venta=id_venta,
        )

    db.execute(
        """
        UPDATE ventas
        SET estado = 'Aprobada', id_personal_aprobador = ?, fecha_resolucion = CURRENT_TIMESTAMP
        WHERE id_venta = ? AND estado = 'Pendiente'
        """,
        (id_personal_aprobador, id_venta),
    )
    db.commit()


def rechazar_venta(id_venta):
    """Rechaza una venta pendiente: el encabezado se elimina y sus lineas
    se eliminan en cascada (ON DELETE CASCADE), no se conserva historial."""
    db = get_db()
    db.execute("DELETE FROM ventas WHERE id_venta = ? AND estado = 'Pendiente'", (id_venta,))
    db.commit()
