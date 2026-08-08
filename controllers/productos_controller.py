"""
productos_controller.py
Rutas (Controller) exclusivas de la pestana Productos.
Conecta las vistas (templates/productos) con el modelo (models/productos_model).
"""
import sqlite3

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from models import productos_model
from utilities.utilities import eliminar_imagen, guardar_imagen, parse_float, parse_int

productos_bp = Blueprint(
    'productos',
    __name__,
    url_prefix='/productos',
)


@productos_bp.route('/')
def index():
    """Listado de productos (Read) con filtro por estado y busqueda."""
    estado = request.args.get('estado', '')
    busqueda = request.args.get('busqueda', '')
    productos = productos_model.get_all_productos(estado=estado or None, busqueda=busqueda or None)
    return render_template(
        'productos/productos_view.html',
        productos=productos,
        estado_filtro=estado,
        busqueda=busqueda,
    )


@productos_bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo():
    """Formulario de creacion (Create)."""
    ubicaciones = productos_model.get_ubicaciones()

    if request.method == 'POST':
        data = _extraer_datos_formulario(request)
        try:
            productos_model.create_producto(data)
            flash(f"Producto \"{data['nombre']}\" creado correctamente.", 'success')
            return redirect(url_for('productos.index'))
        except sqlite3.IntegrityError:
            flash('Ya existe un producto con ese Codigo 1. El codigo 1 debe ser unico.', 'danger')

    return render_template(
        'productos/productos_form.html',
        producto=None,
        ubicaciones=ubicaciones,
        accion='Crear',
    )


@productos_bp.route('/editar/<int:id_producto>', methods=['GET', 'POST'])
def editar(id_producto):
    """Formulario de edicion (Update)."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        flash('El producto solicitado no existe.', 'danger')
        return redirect(url_for('productos.index'))

    ubicaciones = productos_model.get_ubicaciones()

    if request.method == 'POST':
        data = _extraer_datos_formulario(request, producto_actual=producto)
        try:
            productos_model.update_producto(id_producto, data)
            flash(f"Producto \"{data['nombre']}\" actualizado correctamente.", 'success')
            return redirect(url_for('productos.index'))
        except sqlite3.IntegrityError:
            flash('Ya existe otro producto con ese Codigo 1. El codigo 1 debe ser unico.', 'danger')

    return render_template(
        'productos/productos_form.html',
        producto=producto,
        ubicaciones=ubicaciones,
        accion='Editar',
    )


@productos_bp.route('/ver/<int:id_producto>')
def ver(id_producto):
    """Detalle completo de un producto (Read individual)."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        flash('El producto solicitado no existe.', 'danger')
        return redirect(url_for('productos.index'))
    return render_template('productos/productos_detail.html', producto=producto)


@productos_bp.route('/eliminar/<int:id_producto>', methods=['POST'])
def eliminar(id_producto):
    """Elimina un producto (Delete). Si el producto ya tiene ventas o
    movimientos registrados, la base de datos rechaza el borrado (para
    proteger el historial) y sugerimos desactivarlo en su lugar."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        flash('El producto solicitado no existe.', 'danger')
        return redirect(url_for('productos.index'))

    try:
        productos_model.delete_producto(id_producto)
        eliminar_imagen(current_app.config['UPLOAD_FOLDER'], producto['foto_url'])
        flash(f"Producto \"{producto['nombre']}\" eliminado.", 'success')
    except sqlite3.IntegrityError:
        flash(
            f"No se puede eliminar \"{producto['nombre']}\" porque ya tiene ventas u otros "
            "movimientos registrados. Puedes desactivarlo en su lugar.",
            'danger',
        )
    return redirect(url_for('productos.index'))


@productos_bp.route('/estado/<int:id_producto>', methods=['POST'])
def cambiar_estado(id_producto):
    """Alterna el estado Activo/Inactivo de un producto."""
    productos_model.cambiar_estado(id_producto)
    flash('Estado del producto actualizado.', 'success')
    return redirect(url_for('productos.index'))


@productos_bp.route('/qr/<int:id_producto>')
def generar_qr(id_producto):
    """Placeholder: la generacion de QR se implementara en una fase posterior."""
    flash('La generacion de codigo QR se implementara mas adelante.', 'warning')
    return redirect(url_for('productos.index'))


def _extraer_datos_formulario(request, producto_actual=None):
    """Convierte los datos crudos del formulario en un dict listo para
    insertar/actualizar en la base de datos, manejando la imagen subida."""
    foto_filename = producto_actual['foto_url'] if producto_actual else None

    archivo = request.files.get('foto')
    if archivo and archivo.filename:
        if producto_actual and producto_actual['foto_url']:
            eliminar_imagen(current_app.config['UPLOAD_FOLDER'], producto_actual['foto_url'])
        foto_filename = guardar_imagen(
            archivo,
            current_app.config['UPLOAD_FOLDER'],
            current_app.config['ALLOWED_EXTENSIONS'],
            nombre_base=request.form.get('nombre', '').strip(),
        )

    return {
        'foto_url': foto_filename,
        'nombre': request.form.get('nombre', '').strip(),
        'codigo_1': request.form.get('codigo_1', '').strip(),
        'codigo_2': request.form.get('codigo_2', '').strip(),
        'descripcion': request.form.get('descripcion', '').strip(),
        'marca': request.form.get('marca', '').strip(),
        'precio_unidad_facturado': parse_float(request.form.get('precio_unidad_facturado')),
        'precio_docena_facturado': parse_float(request.form.get('precio_docena_facturado')),
        'precio_paquete_facturado': parse_float(request.form.get('precio_paquete_facturado')),
        'precio_paquete_neto': parse_float(request.form.get('precio_paquete_neto')),
        'precio_docena_neto': parse_float(request.form.get('precio_docena_neto')),
        'precio_docena_comercial': parse_float(request.form.get('precio_docena_comercial')),
        'id_ubicacion': parse_int(request.form.get('id_ubicacion')) or None,
        'cantidad': parse_int(request.form.get('cantidad')),
        'pcs_paquete': parse_int(request.form.get('pcs_paquete')),
        'pcs_caja': parse_int(request.form.get('pcs_caja')),
        'posicion': request.form.get('posicion', '').strip(),
        'venta_fraccionada': request.form.get('venta_fraccionada', 'No'),
        'descuento_porcentaje': parse_float(request.form.get('descuento_porcentaje'), 0),
        'incremento_porcentaje': parse_float(request.form.get('incremento_porcentaje'), 0),
        'estado': producto_actual['estado'] if producto_actual else 'Activo',
    }
