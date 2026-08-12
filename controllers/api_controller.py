"""
api_controller.py
Rutas (Controller) JSON consumidas por la app movil (Flutter) de ventas
por QR. No sirve HTML: todo responde JSON, pensado para un cliente nativo
que vive en la misma red local (sin internet).

El carrito de la app movil vive en la memoria de la app, no en la sesion
de Flask (a diferencia del carrito de escritorio en ventas_controller):
aca solo se consultan productos y se recibe el carrito completo al
finalizar la venta (ver crear_venta).
"""
import json
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, session

from controllers.auth_controller import _limpiar_intentos, _registrar_intento_fallido, _usuario_bloqueado
from models import personal_model, productos_model, ventas_model
from utilities.utilities import ROLES_TODOS, ROLES_VENTAS, api_roles_required, guardar_imagen, parse_float, parse_int

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/ping')
def ping():
    """Endpoint publico (sin sesion) para que la app movil verifique que
    encontro el servidor correcto al configurar la IP de la tienda."""
    return jsonify({'ok': True, 'app': 'SGIJ'})


# ============================================================
# Autenticacion (reutiliza personal_model.verificar_credenciales y el
# mismo bloqueo anti-fuerza-bruta que ya usa el login de escritorio)
# ============================================================
@api_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    usuario = (data.get('usuario') or '').strip().lower()
    contrasena = data.get('contrasena') or ''

    if _usuario_bloqueado(usuario):
        return jsonify({'error': 'Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.'}), 429

    personal = personal_model.verificar_credenciales(usuario, contrasena)
    if not personal:
        _registrar_intento_fallido(usuario)
        return jsonify({'error': 'Usuario o contrasena incorrectos.'}), 401

    _limpiar_intentos(usuario)
    session.clear()
    session.permanent = True
    session['id_personal'] = personal['id_personal']
    session['usuario'] = personal['usuario']
    session['rol'] = personal['rol']
    session['nombre_completo'] = f"{personal['nombres']} {personal['apellido_paterno']}"

    return jsonify({
        'id_personal': personal['id_personal'],
        'usuario': personal['usuario'],
        'rol': personal['rol'],
        'nombre_completo': session['nombre_completo'],
    })


@api_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


# ============================================================
# Productos
# ============================================================
def _producto_json(producto):
    return dict(producto)


@api_bp.route('/productos')
@api_roles_required(*ROLES_TODOS)
def productos():
    estado = request.args.get('estado') or None
    busqueda = request.args.get('busqueda') or None
    filas = productos_model.get_all_productos(estado=estado, busqueda=busqueda)
    return jsonify([_producto_json(p) for p in filas])


@api_bp.route('/productos/<int:id_producto>')
@api_roles_required(*ROLES_TODOS)
def producto(id_producto):
    p = productos_model.get_producto(id_producto)
    if not p:
        return jsonify({'error': 'Producto no encontrado.'}), 404
    return jsonify(_producto_json(p))


@api_bp.route('/productos/por-codigo/<path:codigo>')
@api_roles_required(*ROLES_TODOS)
def producto_por_codigo(codigo):
    """Resuelve el codigo_1/codigo_2 extraido del QR escaneado por la app
    movil (el QR trae texto plano con una linea "Codigo: X", ver
    productos_controller._texto_qr_producto).

    El conversor de ruta es <path:codigo>, no <codigo>, a proposito: hay
    codigo_1 reales con una barra adentro (ej. "K2227/28/29", "8804/BLOQUE").
    El cliente manda esa barra como %2F, pero el servidor WSGI la decodifica
    a '/' antes de resolver la ruta -con el conversor por defecto (que no
    matchea '/') esos codigos daban 404 y la app mostraba "no se pudo
    conectar" en vez del error real. <path:...> si matchea '/' dentro del
    valor.

    codigo_2 (query string opcional): codigo_1 ya no identifica un producto
    de forma unica por si solo (ver productos_model.get_producto_por_codigo),
    asi que cualquier QR nuevo manda tambien el codigo_2. Si viene y no hay
    match exacto para el par, o si falta y el codigo_1 es ambiguo entre
    varios productos, se informa con un error especifico en vez de
    devolver el producto equivocado."""
    codigo_2 = request.args.get('codigo_2') or None
    producto, ambiguo = productos_model.get_producto_por_codigo(codigo, codigo_2)
    if ambiguo:
        return jsonify({
            'error': 'Hay mas de un producto con este codigo. Volve a escanear una '
                     'etiqueta que incluya el codigo 2, o reimprimila si es antigua.',
        }), 409
    if not producto:
        return jsonify({'error': 'No se encontro ningun producto con ese codigo.'}), 404
    return jsonify(_producto_json(producto))


# ============================================================
# Inicio (dashboard)
# ============================================================
@api_bp.route('/inicio/estadisticas')
@api_roles_required(*ROLES_TODOS)
def estadisticas():
    stats = dict(productos_model.get_estadisticas())
    stats['ultimos_productos'] = [dict(p) for p in stats['ultimos_productos']]
    return jsonify(stats)


# ============================================================
# Ventas
# ============================================================
def _venta_json(venta):
    v = dict(venta)
    v['detalle'] = [dict(d) for d in v['detalle']]
    return v


@api_bp.route('/ventas/mias')
@api_roles_required(*ROLES_VENTAS)
def ventas_mias():
    """Ventas (pendientes + aprobadas) registradas por el usuario de la
    sesion actual. A diferencia del escritorio (donde Super Admin/Admin
    ven todas), aca SIEMPRE se filtra al usuario logueado en el telefono,
    sin importar el rol: es "lo que vendio este telefono"."""
    id_personal = session['id_personal']
    pendientes = ventas_model.get_pendientes(id_personal_filtro=id_personal)
    aprobadas = ventas_model.get_aprobadas(id_personal_filtro=id_personal)
    return jsonify({
        'pendientes': [_venta_json(v) for v in pendientes],
        'aprobadas': [_venta_json(v) for v in aprobadas],
    })


@api_bp.route('/ventas', methods=['POST'])
@api_roles_required(*ROLES_VENTAS)
def crear_venta():
    """Crea una venta Pendiente a partir del carrito armado en la app
    movil (multipart/form-data): 'items' es un JSON string con las lineas
    del carrito, 'foto_factura' es la foto de la factura escrita a mano.
    El precio nunca se confia del cliente: cada linea se recalcula aca
    contra el producto actual en base de datos (ventas_model.
    resolver_linea_venta), igual que hace el carrito de escritorio."""
    try:
        items_raw = json.loads(request.form.get('items') or '[]')
    except ValueError:
        return jsonify({'error': 'El campo items no es un JSON valido.'}), 400

    if not items_raw:
        return jsonify({'error': 'El carrito esta vacio.'}), 400

    items = []
    for linea in items_raw:
        producto_bd = productos_model.get_producto(parse_int(linea.get('id_producto')))
        if not producto_bd:
            return jsonify({'error': f"El producto {linea.get('id_producto')} no existe."}), 400

        cantidad = parse_float(linea.get('cantidad'), 0)
        if cantidad <= 0:
            return jsonify({'error': f"Cantidad invalida para \"{producto_bd['nombre']}\"."}), 400

        tipo_precio = linea.get('tipo_precio_aplicado') or 'PUF'
        unidad_venta = linea.get('unidad_venta') or None
        cantidad_piezas, precio, _subtotal = ventas_model.resolver_linea_venta(
            producto_bd, tipo_precio, unidad_venta, cantidad,
            precio_personalizado=parse_float(linea.get('precio_personalizado'), 0),
        )
        if precio <= 0:
            return jsonify({
                'error': f"\"{producto_bd['nombre']}\" no tiene precio cargado para esa tarifa/unidad."
            }), 400

        items.append({
            'id_producto': producto_bd['id_producto'],
            'cantidad': cantidad_piezas,
            'tipo_precio_aplicado': tipo_precio,
            'unidad_venta': unidad_venta,
            'precio_aplicado': precio,
        })

    ubicacion = (request.form.get('ubicacion') or '').strip()
    if not ubicacion:
        return jsonify({'error': 'La ubicacion es obligatoria.'}), 400

    numero_factura = (request.form.get('numero_factura') or '').strip()
    if not numero_factura:
        return jsonify({'error': 'El numero de factura es obligatorio.'}), 400

    foto_factura = None
    archivo = request.files.get('foto_factura')
    if archivo and archivo.filename:
        foto_factura = guardar_imagen(
            archivo, current_app.config['FACTURAS_FOLDER'], current_app.config['ALLOWED_EXTENSIONS'],
        )
    if not foto_factura:
        return jsonify({'error': 'Falta la foto de la factura.'}), 400

    ahora = datetime.now()
    data_header = {
        'id_personal_registro': session['id_personal'],
        'ubicacion': ubicacion,
        'cliente_nombre': (request.form.get('cliente_nombre') or '').strip() or 'Publico General',
        'cliente_ci': (request.form.get('cliente_ci') or '').strip(),
        'observaciones': (request.form.get('observaciones') or '').strip(),
        'numero_factura': numero_factura,
        'foto_factura': foto_factura,
        'fecha_venta': ahora.strftime('%Y-%m-%d'),
        'hora_venta': ahora.strftime('%H:%M:%S'),
    }

    id_venta = ventas_model.create_venta(data_header, items)
    venta = ventas_model.get_venta(id_venta)
    return jsonify({
        'id_venta': id_venta,
        'codigo_venta': venta['codigo_venta'],
        'total': venta['total'],
    }), 201
