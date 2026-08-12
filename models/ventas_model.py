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
import random
import sqlite3
from datetime import datetime

from models import movimientos_model
from models.database import get_db
from utilities.utilities import resolver_orden_sql

# Whitelist de ordenamientos disponibles para Ventas Realizadas (Aprobadas)
# unicamente -Pendientes se mantiene siempre en orden de llegada (FIFO), a
# proposito, ya que es una cola de trabajo para caja, no un listado a
# reordenar libremente-. Ver resolver_orden_sql.
ORDENES_VENTAS_APROBADAS = {
    'fecha_desc': 'fecha_creacion DESC',
    'fecha_asc': 'fecha_creacion ASC',
    'total_desc': 'total DESC',
    'total_asc': 'total ASC',
    'cliente_asc': 'cliente_nombre COLLATE NOCASE ASC',
    'cliente_desc': 'cliente_nombre COLLATE NOCASE DESC',
}
ORDEN_VENTAS_APROBADAS_DEFAULT = 'fecha_asc'

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

# En Bolivia la factura implica un pequeno incremento sobre el precio: las
# tarifas "_facturado" (PUF/PDF/PPF) incluyen ese incremento, las "normal"/
# "comercial" (PPN/PDN/PDC) no. Se usa para el paso "Con factura / Sin
# factura" del modo "pago por piezas" en el carrito.
TARIFAS_CON_FACTURA = ('PUF', 'PDF', 'PPF')
TARIFAS_SIN_FACTURA = ('PPN', 'PDN', 'PDC')


def _adjuntar_detalle(db, ventas_rows):
    """Dado un listado de encabezados de venta, adjunta a cada uno su
    lista de lineas (productos) y los datos de personal involucrado.
    Devuelve una lista de diccionarios (no sqlite3.Row, porque anexamos campos)."""
    resultado = []
    for venta in ventas_rows:
        venta_dict = dict(venta)

        lineas = db.execute(
            """
            SELECT d.*, p.nombre AS producto_nombre, p.foto_url AS producto_foto,
                   p.codigo_1 AS producto_codigo, p.descripcion AS producto_descripcion,
                   p.posicion AS producto_posicion, p.cantidad AS producto_stock_actual
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


def get_pendientes(id_personal_filtro=None):
    """Ventas pendientes en orden FIFO (la mas antigua primero), con su
    detalle. Si se entrega id_personal_filtro (Empleado: solo ve las
    propias), se restringe a las registradas por ese usuario."""
    db = get_db()
    if id_personal_filtro:
        ventas = db.execute(
            "SELECT * FROM ventas WHERE estado = 'Pendiente' AND id_personal_registro = ? "
            "ORDER BY fecha_creacion ASC",
            (id_personal_filtro,),
        ).fetchall()
    else:
        ventas = db.execute(
            "SELECT * FROM ventas WHERE estado = 'Pendiente' ORDER BY fecha_creacion ASC"
        ).fetchall()
    return _adjuntar_detalle(db, ventas)


def get_venta(id_venta):
    """Una venta puntual (cualquier estado) con su detalle, para los tickets PDF."""
    db = get_db()
    venta = db.execute("SELECT * FROM ventas WHERE id_venta = ?", (id_venta,)).fetchone()
    if not venta:
        return None
    return _adjuntar_detalle(db, [venta])[0]


def contar_pendientes(id_personal_filtro=None):
    """Conteo rapido de ventas pendientes, usado para el badge del sidebar.
    Filtrado por usuario cuando corresponde (ver get_pendientes)."""
    db = get_db()
    if id_personal_filtro:
        return db.execute(
            "SELECT COUNT(*) AS c FROM ventas WHERE estado = 'Pendiente' AND id_personal_registro = ?",
            (id_personal_filtro,),
        ).fetchone()['c']
    return db.execute(
        "SELECT COUNT(*) AS c FROM ventas WHERE estado = 'Pendiente'"
    ).fetchone()['c']


def get_aprobadas(busqueda=None, id_personal_filtro=None, orden=None):
    """Ventas aprobadas, con su detalle. La busqueda filtra por cliente,
    carnet, usuario, ubicacion, codigo o nombre de producto.
    id_personal_filtro restringe a las registradas por ese usuario
    (Empleado: solo ve las propias). orden ver ORDENES_VENTAS_APROBADAS
    (por defecto, orden de llegada)."""
    db = get_db()
    orden_sql = resolver_orden_sql(orden, ORDENES_VENTAS_APROBADAS, ORDEN_VENTAS_APROBADAS_DEFAULT)

    if busqueda:
        like = f"%{busqueda}%"
        condiciones = """
              AND (
                    v.cliente_nombre LIKE ? OR v.cliente_ci LIKE ?
                    OR v.ubicacion LIKE ? OR p.nombre LIKE ?
                    OR per.nombres LIKE ? OR per.apellido_paterno LIKE ?
                    OR v.codigo_venta LIKE ?
              )
        """
        params = [like, like, like, like, like, like, like]
        if id_personal_filtro:
            condiciones += " AND v.id_personal_registro = ?"
            params.append(id_personal_filtro)
        ids = db.execute(
            f"""
            SELECT DISTINCT v.id_venta
            FROM ventas v
            LEFT JOIN detalle_ventas d ON d.id_venta = v.id_venta
            LEFT JOIN productos p ON d.id_producto = p.id_producto
            LEFT JOIN personal per ON per.id_personal = v.id_personal_registro
            WHERE v.estado = 'Aprobada'
            {condiciones}
            ORDER BY v.fecha_creacion ASC
            """,
            params,
        ).fetchall()
        id_list = [row['id_venta'] for row in ids]
        if not id_list:
            return []
        placeholders = ','.join('?' for _ in id_list)
        ventas = db.execute(
            f"SELECT * FROM ventas WHERE id_venta IN ({placeholders}) ORDER BY {orden_sql}",
            id_list,
        ).fetchall()
    elif id_personal_filtro:
        ventas = db.execute(
            f"SELECT * FROM ventas WHERE estado = 'Aprobada' AND id_personal_registro = ? "
            f"ORDER BY {orden_sql}",
            (id_personal_filtro,),
        ).fetchall()
    else:
        ventas = db.execute(
            f"SELECT * FROM ventas WHERE estado = 'Aprobada' ORDER BY {orden_sql}"
        ).fetchall()

    return _adjuntar_detalle(db, ventas)


def factura_de_tarifa(tipo_precio_aplicado):
    """'con' o 'sin' segun el grupo de la tarifa (ver TARIFAS_CON_FACTURA /
    TARIFAS_SIN_FACTURA); None si es PERSONALIZADO o no reconocida."""
    if tipo_precio_aplicado in TARIFAS_CON_FACTURA:
        return 'con'
    if tipo_precio_aplicado in TARIFAS_SIN_FACTURA:
        return 'sin'
    return None


_ETIQUETA_POR_TARIFA = {
    'PUF': 'Piezas',
    'PDF': 'Docena', 'PDN': 'Docena', 'PDC': 'Docena',
    'PPF': 'Paquete', 'PPN': 'Paquete',
    'PERSONALIZADO': 'Piezas',
}


def etiqueta_unidad(detalle):
    """Unidad para mostrar en los tickets al cliente: si la linea se vendio
    con 'pago por piezas' (unidad_venta), esa unidad tal cual (Cuarta,
    Media, Docena...); si es una venta normal, la unidad que corresponde
    a la tarifa usada (PDF/PDN/PDC->Docena, PPF/PPN->Paquete, PUF/
    PERSONALIZADO->Piezas)."""
    if detalle['unidad_venta']:
        return detalle['unidad_venta'].capitalize()
    return _ETIQUETA_POR_TARIFA.get(detalle['tipo_precio_aplicado'], 'Piezas')


def resolver_precio(producto, tipo_precio_aplicado, precio_personalizado=None):
    """Devuelve el precio unitario segun la tarifa elegida para una linea del carrito."""
    if tipo_precio_aplicado == 'PERSONALIZADO':
        return precio_personalizado or 0
    campo = CAMPO_POR_TIPO_PRECIO.get(tipo_precio_aplicado)
    return producto[campo] if campo else 0


# ============================================================
# Venta por piezas fraccionadas (pieza / cuarta / media / docena /
# paquete / caja) - calculo automatico para agilizar la venta en
# mostrador sin que el cajero tenga que sacar cuentas a mano.
# ============================================================
PIEZAS_DOCENA = 12
UNIDADES_VENTA = ('pieza', 'cuarta', 'media', 'docena', 'paquete', 'caja')

# Tarifas que usan la docena (12 piezas fijas) como contenedor de referencia.
_TARIFAS_DOCENA = {'PDF', 'PDN', 'PDC'}
# Tarifas que usan el paquete (pcs_paquete piezas, variable por producto).
_TARIFAS_PAQUETE = {'PPF', 'PPN'}


def _piezas_contenedor(producto, tipo_precio_aplicado):
    """Piezas que representa el 'contenedor' de la tarifa elegida:
    PUF -> 1 pieza suelta, PDF/PDN/PDC -> 1 docena (12), PPF/PPN -> 1 paquete
    (pcs_paquete). Devuelve 0 si la tarifa no tiene contenedor valido para
    ese producto (ej. PPF en un producto sin pcs_paquete cargado)."""
    if tipo_precio_aplicado == 'PUF':
        return 1
    if tipo_precio_aplicado in _TARIFAS_DOCENA:
        return PIEZAS_DOCENA
    if tipo_precio_aplicado in _TARIFAS_PAQUETE:
        return producto['pcs_paquete'] or 0
    return 0


def unidades_venta_disponibles(producto):
    """Unidades de venta que tiene sentido ofrecer para este producto puntual:
    paquete solo si tiene pcs_paquete cargado, caja solo si tiene pcs_caja."""
    disponibles = ['pieza', 'cuarta', 'media', 'docena']
    if (producto['pcs_paquete'] or 0) > 0:
        disponibles.append('paquete')
    if (producto['pcs_caja'] or 0) > 0:
        disponibles.append('caja')
    return disponibles


def resolver_venta_pieza(producto, tipo_precio_aplicado, unidad_venta, cantidad_unidades):
    """Calcula una linea de venta por piezas fraccionadas.

    1. precio_por_pieza = precio de la tarifa elegida / piezas de su contenedor.
    2. piezas_de_la_unidad = cuantas piezas representa la unidad_venta elegida
       (cuarta/media se calculan sobre el contenedor de la tarifa elegida).
    3. piezas_totales = piezas_de_la_unidad * cantidad_unidades (sin redondear,
       se permiten decimales, ej. 7.5).
    4. subtotal = precio_por_pieza * piezas_totales.

    Devuelve (piezas_totales, precio_por_pieza, subtotal). Si la combinacion
    no es valida (tarifa sin contenedor, o unidad no disponible para el
    producto) devuelve (0, 0, 0) en vez de reventar, para que la UI se apoye
    en el aviso de "sin precio cargado" que ya existe."""
    if unidad_venta not in unidades_venta_disponibles(producto):
        return 0, 0, 0

    contenedor = _piezas_contenedor(producto, tipo_precio_aplicado)
    precio_tarifa = resolver_precio(producto, tipo_precio_aplicado)
    if contenedor <= 0 or precio_tarifa <= 0:
        return 0, 0, 0

    precio_por_pieza = precio_tarifa / contenedor

    piezas_por_unidad = {
        'pieza': 1,
        'cuarta': contenedor / 4,
        'media': contenedor / 2,
        'docena': PIEZAS_DOCENA,
        'paquete': producto['pcs_paquete'] or 0,
        'caja': producto['pcs_caja'] or 0,
    }[unidad_venta]

    piezas_totales = piezas_por_unidad * cantidad_unidades
    subtotal = precio_por_pieza * piezas_totales
    return piezas_totales, precio_por_pieza, subtotal


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


def resolver_linea_venta(producto, tipo_precio_aplicado, unidad_venta, cantidad, precio_personalizado=None):
    """Resuelve una linea de carrito (escritorio o app movil) contra el
    producto ACTUAL en base de datos: cuantas piezas representa, el precio
    unitario y el subtotal. Centraliza la rama "pago por piezas" (usa
    resolver_venta_pieza) vs tarifa normal (resolver_precio * cantidad)
    para que ningun caller tenga que confiar en un precio mandado por el
    cliente. Devuelve (cantidad_piezas, precio_aplicado, subtotal)."""
    if unidad_venta:
        return resolver_venta_pieza(producto, tipo_precio_aplicado, unidad_venta, cantidad)

    precio = resolver_precio(producto, tipo_precio_aplicado, precio_personalizado)
    return cantidad, precio, precio * cantidad


def generar_codigo_venta(db, fecha):
    """Codigo unico buscable para una venta: VTA-AAAAMMDD-XXXX (4 digitos
    al azar). Reintenta si por casualidad ya existe (coleccion practicamente
    imposible, pero el codigo debe ser unico para poder buscarlo)."""
    prefijo = f"VTA-{fecha:%Y%m%d}"
    for _ in range(20):
        codigo = f"{prefijo}-{random.randint(0, 9999):04d}"
        existe = db.execute("SELECT 1 FROM ventas WHERE codigo_venta = ?", (codigo,)).fetchone()
        if not existe:
            return codigo
    raise RuntimeError("No se pudo generar un codigo_venta unico tras varios intentos.")


def create_venta(data_header, items):
    """Crea una venta (encabezado) en estado Pendiente junto con sus lineas.
    `items` es una lista de dicts:
    [{'id_producto':.., 'cantidad':.., 'tipo_precio_aplicado':.., 'precio_aplicado':..}, ...]
    El total del encabezado se calcula como la suma de los subtotales."""
    db = get_db()

    total = sum(item['cantidad'] * item['precio_aplicado'] for item in items)
    data_header = dict(data_header)
    data_header['total'] = total
    # numero_factura/foto_factura: solo los manda la app movil de ventas
    # por QR (ver controllers/api_controller.py); el carrito de escritorio
    # no los conoce, por eso quedan en NULL para esas ventas.
    data_header.setdefault('numero_factura', None)
    data_header.setdefault('foto_factura', None)

    # generar_codigo_venta ya verifica que el codigo no exista antes de
    # usarlo, pero si dos ventas se crean en el mismo instante podrian
    # "pasar" esa verificacion las dos con el mismo numero (carrera). El
    # indice UNIQUE de la base lo va a rechazar de todas formas: en vez de
    # dejar que ese error rompa la venta, se reintenta con un codigo nuevo.
    for intento in range(5):
        data_header['codigo_venta'] = generar_codigo_venta(db, datetime.now())
        try:
            cursor = db.execute(
                """
                INSERT INTO ventas (
                    codigo_venta, id_personal_registro, ubicacion, cliente_nombre, cliente_ci,
                    observaciones, numero_factura, foto_factura, estado, fecha_venta, hora_venta, total
                ) VALUES (
                    :codigo_venta, :id_personal_registro, :ubicacion, :cliente_nombre, :cliente_ci,
                    :observaciones, :numero_factura, :foto_factura, 'Pendiente', :fecha_venta, :hora_venta, :total
                )
                """,
                data_header,
            )
            break
        except sqlite3.IntegrityError:
            if intento == 4:
                raise
    id_venta = cursor.lastrowid

    for item in items:
        subtotal = item['cantidad'] * item['precio_aplicado']
        db.execute(
            """
            INSERT INTO detalle_ventas (id_venta, id_producto, cantidad, tipo_precio_aplicado, unidad_venta, precio_aplicado, subtotal)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id_venta, item['id_producto'], item['cantidad'], item['tipo_precio_aplicado'],
                item.get('unidad_venta'), item['precio_aplicado'], subtotal,
            ),
        )

    db.commit()
    return id_venta


def aprobar_venta(id_venta, id_personal_aprobador):
    """Aprueba una venta pendiente, descuenta el stock de cada producto
    vendido (en piezas reales) y deja registrada la salida correspondiente
    en el Kardex. El cambio de estado se hace PRIMERO y con guarda
    (WHERE estado = 'Pendiente'): si otra request ya la aprobo antes
    (doble click, doble submit), este UPDATE no afecta ninguna fila y se
    corta ahi, sin descontar stock ni registrar movimientos de nuevo.
    Devuelve True si esta llamada fue la que efectivamente aprobo la
    venta, False si ya estaba resuelta."""
    db = get_db()

    cursor = db.execute(
        """
        UPDATE ventas
        SET estado = 'Aprobada', id_personal_aprobador = ?, fecha_resolucion = CURRENT_TIMESTAMP
        WHERE id_venta = ? AND estado = 'Pendiente'
        """,
        (id_personal_aprobador, id_venta),
    )
    if cursor.rowcount == 0:
        db.commit()
        return False

    lineas = db.execute(
        """
        SELECT d.id_producto, d.cantidad, d.tipo_precio_aplicado, d.unidad_venta,
               p.pcs_paquete
        FROM detalle_ventas d
        JOIN productos p ON p.id_producto = d.id_producto
        WHERE d.id_venta = ?
        """,
        (id_venta,),
    ).fetchall()

    for linea in lineas:
        # detalle_ventas.cantidad es "cuantas unidades de lo que se eligio"
        # (ej. 2 docenas via tarifa PDF, o ya piezas reales si vino de
        # "pago por piezas"), no siempre piezas sueltas -> hay que
        # convertir a piezas reales para descontar del stock/Kardex.
        if linea['unidad_venta']:
            piezas_reales = linea['cantidad']
        else:
            contenedor = _piezas_contenedor(linea, linea['tipo_precio_aplicado']) or 1
            piezas_reales = linea['cantidad'] * contenedor

        # Sin piso en 0: si la venta pide mas de lo que hay en tienda, el
        # stock queda en negativo a proposito -es el registro de cuanto
        # falta reponer desde el almacen (ver productos_model.obtener_productos_con_faltante
        # y la alerta en Inicio)-, la venta no se bloquea por eso.
        db.execute(
            "UPDATE productos SET cantidad = cantidad - ? WHERE id_producto = ?",
            (piezas_reales, linea['id_producto']),
        )
        movimientos_model.registrar_movimiento(
            id_producto=linea['id_producto'],
            id_personal=id_personal_aprobador,
            tipo_movimiento='SALIDA_VENTA',
            cantidad=-piezas_reales,
            motivo_nota=f'Venta aprobada #{id_venta}',
            id_venta=id_venta,
        )

    db.commit()
    return True


def rechazar_venta(id_venta):
    """Rechaza una venta pendiente: el encabezado se elimina y sus lineas
    se eliminan en cascada (ON DELETE CASCADE), no se conserva historial."""
    db = get_db()
    db.execute("DELETE FROM ventas WHERE id_venta = ? AND estado = 'Pendiente'", (id_venta,))
    db.commit()
