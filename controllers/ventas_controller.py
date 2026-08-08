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

from models import personal_model, productos_model, ventas_model
from utilities.utilities import parse_float, parse_int

ventas_bp = Blueprint('ventas', __name__, url_prefix='/ventas')

CLAVE_CARRITO = 'carrito'
TIPOS_PRECIO = ['PUF', 'PDF', 'PPF', 'PPN', 'PDN', 'PDC', 'PERSONALIZADO']


# ============================================================
# Listado principal: pendientes + aprobadas
# ============================================================
@ventas_bp.route('/')
def index():
    busqueda = request.args.get('busqueda', '')
    pendientes = ventas_model.get_pendientes()
    aprobadas = ventas_model.get_aprobadas(busqueda or None)
    personal_activo = personal_model.get_personal_activo()
    return render_template(
        'ventas/ventas_view.html',
        pendientes=pendientes,
        aprobadas=aprobadas,
        busqueda=busqueda,
        personal_activo=personal_activo,
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

        lineas.append({
            'producto': producto,
            'cantidad': item['cantidad'],
            'tipo_precio_aplicado': item['tipo_precio_aplicado'],
            'precio_personalizado': item.get('precio_personalizado', 0),
            'precio_aplicado': precio,
            'subtotal': subtotal,
        })

    if len(carrito_valido) != len(carrito):
        _guardar_carrito(carrito_valido)

    return lineas, total


@ventas_bp.route('/carrito/agregar/<int:id_producto>')
def carrito_agregar(id_producto):
    """Agrega 1 unidad de un producto al carrito (tarifa PUF por defecto)."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        flash('El producto solicitado no existe.', 'danger')
        return redirect(url_for('productos.index'))

    carrito = _obtener_carrito()
    for item in carrito:
        if item['id_producto'] == id_producto:
            item['cantidad'] += 1
            break
    else:
        carrito.append({
            'id_producto': id_producto,
            'cantidad': 1,
            'tipo_precio_aplicado': 'PUF',
            'precio_personalizado': 0,
        })

    _guardar_carrito(carrito)
    flash(f"\"{producto['nombre']}\" agregado al carrito.", 'success')
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito')
def carrito():
    """Muestra el carrito actual y el formulario para finalizar la venta."""
    lineas, total = _contexto_carrito()
    personal_activo = personal_model.get_personal_activo()
    return render_template(
        'ventas/carrito_view.html',
        lineas=lineas,
        total=total,
        tipos_precio=TIPOS_PRECIO,
        personal_activo=personal_activo,
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

    id_personal_registro = parse_int(request.form.get('id_personal_registro')) or None
    if not id_personal_registro:
        flash('Debes seleccionar el Usuario que registra la venta.', 'danger')
        return redirect(url_for('ventas.carrito'))

    ahora = datetime.now()
    data_header = {
        'id_personal_registro': id_personal_registro,
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
    """Aprueba una venta pendiente (accion de caja al recibir el dinero)."""
    id_personal_aprobador = parse_int(request.form.get('id_personal_aprobador')) or None
    if not id_personal_aprobador:
        flash('Debes seleccionar quien aprueba la venta.', 'danger')
        return redirect(url_for('ventas.index'))

    ventas_model.aprobar_venta(id_venta, id_personal_aprobador)
    flash('Venta aprobada correctamente.', 'success')
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/rechazar/<int:id_venta>', methods=['POST'])
def rechazar(id_venta):
    """Rechaza una venta pendiente. El registro se elimina, no se conserva."""
    ventas_model.rechazar_venta(id_venta)
    flash('Venta rechazada. El registro no fue guardado.', 'warning')
    return redirect(url_for('ventas.index'))
