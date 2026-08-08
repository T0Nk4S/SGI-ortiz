"""
ventas_controller.py
Rutas (Controller) exclusivas de la pestana Ventas.

El carrito de compra vive en la sesion de Flask (session['carrito']) como
una lista de lineas: [{'id_producto':.., 'cantidad':.., 'tipo_precio_aplicado':.., 'precio_personalizado':..}, ...]
Al "Finalizar Venta" se convierte en un encabezado (ventas) + N lineas
(detalle_ventas), y el carrito de sesion se vacia.
"""
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import productos_model, ventas_model
from utilities.utilities import parse_float, parse_int

ventas_bp = Blueprint('ventas', __name__, url_prefix='/ventas')

CLAVE_CARRITO = 'carrito'


# ============================================================
# Listado principal: pendientes + aprobadas
# ============================================================
@ventas_bp.route('/')
def index():
    busqueda = request.args.get('busqueda', '')
    pendientes = ventas_model.get_pendientes()
    aprobadas = ventas_model.get_aprobadas(busqueda or None)
    return render_template(
        'ventas/ventas_view.html',
        pendientes=pendientes,
        aprobadas=aprobadas,
        busqueda=busqueda,
    )


# ============================================================
# Carrito (sesion)
# ============================================================
def _obtener_carrito():
    return session.setdefault(CLAVE_CARRITO, [])


def _guardar_carrito(carrito):
    session[CLAVE_CARRITO] = carrito
    session.modified = True


def _contexto_carrito():
    """Arma la info completa del carrito (producto + precios resueltos +
    subtotales) leyendo siempre los datos actuales de productos, y
    limpiando del carrito cualquier producto que ya no exista."""
    carrito = _obtener_carrito()
    lineas = []
    total = 0
    carrito_valido = []

    for item in carrito:
        producto = productos_model.get_producto(item['id_producto'])
        if not producto:
            continue  # el producto fue eliminado, se descarta la linea
        carrito_valido.append(item)

        precio = ventas_model.resolver_precio(
            producto, item['tipo_precio_aplicado'], item.get('precio_personalizado')
        )
        subtotal = precio * item['cantidad']
        total += subtotal

        tarifas = ventas_model.tarifas_disponibles(producto)
        lineas.append({
            'producto': producto,
            'cantidad': item['cantidad'],
            'tipo_precio_aplicado': item['tipo_precio_aplicado'],
            'precio_personalizado': item.get('precio_personalizado', 0),
            'precio_aplicado': precio,
            'subtotal': subtotal,
            'precios_por_tarifa': {tipo: ventas_model.resolver_precio(producto, tipo) for tipo in tarifas},
        })

    if len(carrito_valido) != len(carrito):
        _guardar_carrito(carrito_valido)

    return lineas, total


def _agregar_producto_al_carrito(carrito, producto):
    """Suma 1 unidad de `producto` al carrito (lista de session), ya sea
    que ya estuviera en el o no. Modifica `carrito` in-place. La tarifa
    por defecto se elige segun las tarifas que ese producto realmente
    tiene cargadas y si se vende por piezas o solo por paquete/docena
    (ver ventas_model.tarifa_sugerida), para no terminar cobrando
    Bs. 0.00 por usar siempre PUF sin verificar si aplica."""
    for item in carrito:
        if item['id_producto'] == producto['id_producto']:
            item['cantidad'] += 1
            return

    carrito.append({
        'id_producto': producto['id_producto'],
        'cantidad': 1,
        'tipo_precio_aplicado': ventas_model.tarifa_sugerida(producto),
        'precio_personalizado': 0,
    })


@ventas_bp.route('/carrito/agregar/<int:id_producto>')
def carrito_agregar(id_producto):
    """Agrega 1 unidad de un producto al carrito."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        flash('El producto solicitado no existe.', 'danger')
        return redirect(url_for('productos.index'))

    carrito = _obtener_carrito()
    _agregar_producto_al_carrito(carrito, producto)
    _guardar_carrito(carrito)
    flash(f"\"{producto['nombre']}\" agregado al carrito.", 'success')
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito/agregar-multiple', methods=['POST'])
def carrito_agregar_multiple():
    """Agrega varios productos al carrito de una sola vez, elegidos con
    los checkboxes del listado de Productos (evita tener que presionar
    "Vender" y volver atras uno por uno)."""
    ids_seleccionados = request.form.getlist('ids_seleccionados', type=int)
    if not ids_seleccionados:
        flash('No seleccionaste ningun producto.', 'warning')
        return redirect(url_for('productos.index'))

    carrito = _obtener_carrito()
    agregados = 0
    for id_producto in ids_seleccionados:
        producto = productos_model.get_producto(id_producto)
        if producto:
            _agregar_producto_al_carrito(carrito, producto)
            agregados += 1

    _guardar_carrito(carrito)
    if agregados:
        flash(f'{agregados} producto(s) agregado(s) al carrito.', 'success')
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito')
def carrito():
    """Muestra el carrito actual y el formulario para finalizar la venta."""
    lineas, total = _contexto_carrito()
    return render_template(
        'ventas/carrito_view.html',
        lineas=lineas,
        total=total,
    )


@ventas_bp.route('/carrito/actualizar/<int:id_producto>', methods=['POST'])
def carrito_actualizar(id_producto):
    """Actualiza cantidad y/o tarifa de una linea del carrito."""
    carrito = _obtener_carrito()
    cantidad = max(parse_int(request.form.get('cantidad'), 1), 1)
    tipo_precio = request.form.get('tipo_precio_aplicado', 'PUF')
    precio_personalizado = parse_float(request.form.get('precio_personalizado'), 0)

    for item in carrito:
        if item['id_producto'] == id_producto:
            item['cantidad'] = cantidad
            item['tipo_precio_aplicado'] = tipo_precio
            item['precio_personalizado'] = precio_personalizado
            break

    _guardar_carrito(carrito)
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito/quitar/<int:id_producto>', methods=['POST'])
def carrito_quitar(id_producto):
    """Elimina una linea del carrito."""
    carrito = [item for item in _obtener_carrito() if item['id_producto'] != id_producto]
    _guardar_carrito(carrito)
    flash('Producto quitado del carrito.', 'success')
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito/vaciar', methods=['POST'])
def carrito_vaciar():
    """Vacia el carrito completo."""
    _guardar_carrito([])
    flash('Carrito vaciado.', 'success')
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito/finalizar', methods=['POST'])
def carrito_finalizar():
    """Convierte el carrito de sesion en una venta Pendiente (encabezado + detalle)."""
    lineas, _total = _contexto_carrito()

    if not lineas:
        flash('El carrito esta vacio.', 'danger')
        return redirect(url_for('ventas.carrito'))

    ahora = datetime.now()
    data_header = {
        'id_personal_registro': session['id_personal'],
        'ubicacion': request.form.get('ubicacion', '').strip(),
        'cliente_nombre': request.form.get('cliente_nombre', '').strip() or 'Publico General',
        'cliente_ci': request.form.get('cliente_ci', '').strip(),
        'observaciones': request.form.get('observaciones', '').strip(),
        'fecha_venta': ahora.strftime('%Y-%m-%d'),
        'hora_venta': ahora.strftime('%H:%M:%S'),
    }

    items = [
        {
            'id_producto': linea['producto']['id_producto'],
            'cantidad': linea['cantidad'],
            'tipo_precio_aplicado': linea['tipo_precio_aplicado'],
            'precio_aplicado': linea['precio_aplicado'],
        }
        for linea in lineas
    ]

    ventas_model.create_venta(data_header, items)
    _guardar_carrito([])
    flash('Venta registrada como pendiente de aprobacion.', 'success')
    return redirect(url_for('ventas.index'))


# ============================================================
# Aprobacion / rechazo
# ============================================================
@ventas_bp.route('/aprobar/<int:id_venta>', methods=['POST'])
def aprobar(id_venta):
    """Aprueba una venta pendiente (accion de caja al recibir el dinero).
    Quien aprueba es siempre el usuario en sesion, nunca un valor elegido
    en el formulario: de lo contrario cualquier usuario podria atribuir
    la aprobacion a otra persona."""
    ventas_model.aprobar_venta(id_venta, session['id_personal'])
    flash('Venta aprobada correctamente.', 'success')
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/rechazar/<int:id_venta>', methods=['POST'])
def rechazar(id_venta):
    """Rechaza una venta pendiente. El registro se elimina, no se conserva."""
    ventas_model.rechazar_venta(id_venta)
    flash('Venta rechazada. El registro no fue guardado.', 'warning')
    return redirect(url_for('ventas.index'))
