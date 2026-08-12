"""
ventas_controller.py
Rutas (Controller) exclusivas de la pestana Ventas.

El carrito de compra vive en la sesion de Flask (session['carrito']) como
una lista de lineas: [{'id_producto':.., 'cantidad':.., 'tipo_precio_aplicado':.., 'precio_personalizado':..}, ...]
Al "Finalizar Venta" se convierte en un encabezado (ventas) + N lineas
(detalle_ventas), y el carrito de sesion se vacia.
"""
import io
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, send_from_directory, session, url_for

from models import productos_model, ventas_model
from utilities.utilities import ROL_EMPLEADO, ROLES_VENTAS, parse_float, parse_int, roles_required

ventas_bp = Blueprint('ventas', __name__, url_prefix='/ventas')

CLAVE_CARRITO = 'carrito'


def _filtro_personal_actual():
    """Empleado solo ve/opera sobre las ventas que el mismo registro;
    los demas roles con acceso a Ventas (Super Admin, Admin) ven todas."""
    return session.get('id_personal') if session.get('rol') == ROL_EMPLEADO else None


# ============================================================
# Listado principal: pendientes + aprobadas
# ============================================================
@ventas_bp.route('/')
@roles_required(*ROLES_VENTAS)
def index():
    busqueda = request.args.get('busqueda', '')
    orden = request.args.get('orden', '')
    filtro = _filtro_personal_actual()
    pendientes = ventas_model.get_pendientes(id_personal_filtro=filtro)
    aprobadas = ventas_model.get_aprobadas(busqueda or None, id_personal_filtro=filtro, orden=orden or None)
    return render_template(
        'ventas/ventas_view.html',
        pendientes=pendientes,
        aprobadas=aprobadas,
        busqueda=busqueda,
        orden_actual=orden or ventas_model.ORDEN_VENTAS_APROBADAS_DEFAULT,
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

        unidad_venta = item.get('unidad_venta')
        cantidad_piezas, precio, subtotal = ventas_model.resolver_linea_venta(
            producto, item['tipo_precio_aplicado'], unidad_venta, item['cantidad'],
            precio_personalizado=item.get('precio_personalizado'),
        )
        total += subtotal

        tarifas = ventas_model.tarifas_disponibles(producto)
        lineas.append({
            'producto': producto,
            'cantidad': item['cantidad'],
            'cantidad_piezas': cantidad_piezas,
            'unidad_venta': unidad_venta,
            'unidades_disponibles': ventas_model.unidades_venta_disponibles(producto),
            'tipo_precio_aplicado': item['tipo_precio_aplicado'],
            'factura_actual': ventas_model.factura_de_tarifa(item['tipo_precio_aplicado']),
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
        'unidad_venta': None,
    })


@ventas_bp.route('/carrito/agregar/<int:id_producto>')
@roles_required(*ROLES_VENTAS)
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
@roles_required(*ROLES_VENTAS)
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
@roles_required(*ROLES_VENTAS)
def carrito():
    """Muestra el carrito actual y el formulario para finalizar la venta."""
    lineas, total = _contexto_carrito()
    return render_template(
        'ventas/carrito_view.html',
        lineas=lineas,
        total=total,
    )


@ventas_bp.route('/carrito/actualizar/<int:id_producto>', methods=['POST'])
@roles_required(*ROLES_VENTAS)
def carrito_actualizar(id_producto):
    """Actualiza cantidad y/o tarifa de una linea del carrito. Si viene marcado
    "Pago por piezas" (modo_pieza), `cantidad` se interpreta como cuantas
    unidades de venta pide el cliente (ej. 2 cuartas) -sigue siendo un numero
    entero-; el resultado en piezas (que puede salir decimal, ej. 7.5) lo
    calcula ventas_model.resolver_venta_pieza, no el cajero."""
    carrito = _obtener_carrito()
    modo_pieza = request.form.get('modo_pieza') == 'on'
    tipo_precio = request.form.get('tipo_precio_aplicado', 'PUF')
    precio_personalizado = parse_float(request.form.get('precio_personalizado'), 0)
    cantidad = max(parse_int(request.form.get('cantidad'), 1), 1)
    unidad_venta = request.form.get('unidad_venta') if modo_pieza else None

    for item in carrito:
        if item['id_producto'] == id_producto:
            item['cantidad'] = cantidad
            item['tipo_precio_aplicado'] = tipo_precio
            item['precio_personalizado'] = precio_personalizado
            item['unidad_venta'] = unidad_venta
            break

    _guardar_carrito(carrito)
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito/quitar/<int:id_producto>', methods=['POST'])
@roles_required(*ROLES_VENTAS)
def carrito_quitar(id_producto):
    """Elimina una linea del carrito."""
    carrito = [item for item in _obtener_carrito() if item['id_producto'] != id_producto]
    _guardar_carrito(carrito)
    flash('Producto quitado del carrito.', 'success')
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito/vaciar', methods=['POST'])
@roles_required(*ROLES_VENTAS)
def carrito_vaciar():
    """Vacia el carrito completo."""
    _guardar_carrito([])
    flash('Carrito vaciado.', 'success')
    return redirect(url_for('ventas.carrito'))


@ventas_bp.route('/carrito/finalizar', methods=['POST'])
@roles_required(*ROLES_VENTAS)
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
            'cantidad': linea['cantidad_piezas'],
            'tipo_precio_aplicado': linea['tipo_precio_aplicado'],
            'unidad_venta': linea['unidad_venta'],
            'precio_aplicado': linea['precio_aplicado'],
        }
        for linea in lineas
    ]

    ventas_model.create_venta(data_header, items)
    _guardar_carrito([])
    flash('Venta registrada como pendiente de aprobacion.', 'success')
    return redirect(url_for('ventas.index'))


def _venta_accesible_o_redirigir(id_venta):
    """Trae la venta si el usuario en sesion puede operarla (Super Admin/
    Admin: cualquiera; Empleado: solo la que el mismo registro). Si no
    existe o no le corresponde, devuelve None y ya deja armado el
    flash+redirect - nunca hay que confiar en que el link no aparecio en
    su lista, un Empleado podria escribir la URL a mano."""
    venta = ventas_model.get_venta(id_venta)
    if not venta:
        flash('La venta solicitada no existe.', 'danger')
        return None
    if session.get('rol') == ROL_EMPLEADO and venta['id_personal_registro'] != session.get('id_personal'):
        flash('Solo podes operar sobre las ventas que vos mismo registraste.', 'danger')
        return None
    return venta


@ventas_bp.route('/<int:id_venta>/factura')
@roles_required(*ROLES_VENTAS)
def factura_imagen(id_venta):
    """Sirve la foto de la factura escrita a mano de una venta. Va por una
    ruta con sesion (en vez de static/, que no exige login) porque la foto
    trae datos del cliente (nombre, CI/NIT); ademas reutiliza el mismo
    chequeo de acceso que el resto de la venta (Empleado: solo las propias)."""
    venta = _venta_accesible_o_redirigir(id_venta)
    if not venta:
        return redirect(url_for('ventas.index'))
    if not venta['foto_factura']:
        return '', 404
    return send_from_directory(current_app.config['FACTURAS_FOLDER'], venta['foto_factura'])


# ============================================================
# Aprobacion / rechazo
# ============================================================
@ventas_bp.route('/aprobar/<int:id_venta>', methods=['POST'])
@roles_required(*ROLES_VENTAS)
def aprobar(id_venta):
    """Aprueba una venta pendiente (accion de caja al recibir el dinero).
    Quien aprueba es siempre el usuario en sesion, nunca un valor elegido
    en el formulario: de lo contrario cualquier usuario podria atribuir
    la aprobacion a otra persona."""
    if not _venta_accesible_o_redirigir(id_venta):
        return redirect(url_for('ventas.index'))
    if ventas_model.aprobar_venta(id_venta, session['id_personal']):
        flash('Venta aprobada correctamente.', 'success')
    else:
        flash('Esa venta ya habia sido resuelta (aprobada o rechazada) antes.', 'warning')
    return redirect(url_for('ventas.index'))


@ventas_bp.route('/rechazar/<int:id_venta>', methods=['POST'])
@roles_required(*ROLES_VENTAS)
def rechazar(id_venta):
    """Rechaza una venta pendiente. El registro se elimina, no se conserva."""
    if not _venta_accesible_o_redirigir(id_venta):
        return redirect(url_for('ventas.index'))
    ventas_model.rechazar_venta(id_venta)
    flash('Venta rechazada. El registro no fue guardado.', 'warning')
    return redirect(url_for('ventas.index'))


# ============================================================
# Tickets PDF para papel termico (80mm) - se entregan al cliente en el
# momento de la venta, por eso estan disponibles tanto en Pendiente como
# en Aprobada (no hace falta esperar a que caja apruebe para imprimirlo).
# ============================================================
def _fmt_cantidad(valor):
    """1.0 -> '1', 7.5 -> '7.5' (sin ceros de mas, para el 'X n' del ticket)."""
    texto = f"{valor:.2f}".rstrip('0').rstrip('.')
    return texto or '0'


def _encabezado_ticket(venta, styles):
    from reportlab.platypus import Paragraph

    return [
        Paragraph('Resumen de Venta', styles['TicketTitulo']),
        Paragraph(f"Generado el: {datetime.now():%d/%m/%Y %H:%M:%S}", styles['TicketNormal']),
        Paragraph(f"Codigo: {venta['codigo_venta'] or '-'}", styles['TicketNormal']),
        Paragraph(f"Nombre: {venta['cliente_nombre'] or ''}", styles['TicketNormal']),
        Paragraph("Destino: __________________________", styles['TicketNormal']),
        Paragraph(f"NIT: {venta['cliente_ci'] or ''}", styles['TicketNormal']),
        Paragraph("Transportadora: __________________________", styles['TicketNormal']),
        Paragraph(f"Fecha: {venta['fecha_venta']}", styles['TicketNormal']),
    ]


def _pie_ticket(venta, styles, incluir_total=True):
    from reportlab.platypus import Paragraph

    pie = []
    if incluir_total:
        pie.append(Paragraph(f"Total Venta: {venta['total']:.2f} Bs.", styles['TicketTotal']))
    pie.append(Paragraph(
        "Nota: Por favor, revise cuidadosamente los productos entregados. "
        "Cualquier reclamo o solicitud de ajuste deberá realizarse dentro de un "
        "plazo máximo de 10 días calendario a partir de la fecha de compra. "
        "Pasado este periodo, no se aceptarán cambios ni devoluciones.",
        styles['TicketNota'],
    ))
    pie.append(Paragraph(f"Observaciones: {venta['observaciones'] or ''}", styles['TicketNormal']))
    return pie


def _separador_producto():
    """Linea punteada para diferenciar a simple vista donde termina un
    producto y empieza el siguiente en los tickets de bloques (Resumen
    de cuenta / Venta para almacen)."""
    from reportlab.lib import colors
    from reportlab.platypus import HRFlowable

    return HRFlowable(width='100%', thickness=0.6, color=colors.grey, dash=(2, 2), spaceBefore=3, spaceAfter=5)


def _estilos_ticket():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('TicketTitulo', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold', alignment=1, spaceAfter=4))
    styles.add(ParagraphStyle('TicketNormal', parent=styles['Normal'], fontSize=8, leading=10))
    styles.add(ParagraphStyle('TicketCelda', parent=styles['Normal'], fontSize=7, leading=9))
    styles.add(ParagraphStyle('TicketTotal', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=4))
    styles.add(ParagraphStyle('TicketNota', parent=styles['Normal'], fontSize=6.5, leading=8, spaceAfter=4))
    return styles


@ventas_bp.route('/<int:id_venta>/pdf/venta-cliente')
@roles_required(*ROLES_VENTAS)
def pdf_venta_cliente(id_venta):
    """Ticket con tabla de productos, para entregar al cliente en el momento
    de la venta (formato pensado para impresora termica de 80mm)."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph

    venta = _venta_accesible_o_redirigir(id_venta)
    if not venta:
        return redirect(url_for('ventas.index'))

    styles = _estilos_ticket()
    n_items = len(venta['detalle'])
    # Generoso a proposito: nombres/codigos largos pueden envolver a 3
    # lineas en la columna angosta de descripcion, y una segunda pagina
    # en un ticket termico es peor que dejar algo de blanco de mas.
    alto = max(90 * mm, 85 * mm + n_items * 14 * mm)

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=(80 * mm, alto),
        leftMargin=3 * mm, rightMargin=3 * mm, topMargin=3 * mm, bottomMargin=3 * mm,
    )

    elementos = _encabezado_ticket(venta, styles)
    elementos.append(Spacer(1, 6))

    filas = [['Cantidad', 'Descripción / Código', 'Precio', 'Total']]
    for d in venta['detalle']:
        filas.append([
            Paragraph(f"{_fmt_cantidad(d['cantidad'])} {ventas_model.etiqueta_unidad(d)}", styles['TicketCelda']),
            Paragraph(f"{d['producto_nombre']} ({d['producto_codigo']})", styles['TicketCelda']),
            Paragraph(f"{d['precio_aplicado']:.2f} Bs. X {_fmt_cantidad(d['cantidad'])}", styles['TicketCelda']),
            Paragraph(f"{d['subtotal']:.2f} Bs.", styles['TicketCelda']),
        ])

    tabla = Table(filas, colWidths=[13 * mm, 32 * mm, 16 * mm, 13 * mm])
    tabla.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 6))
    elementos.extend(_pie_ticket(venta, styles))

    documento.build(elementos)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=False,
                      download_name=f"{venta['codigo_venta']}.pdf")


@ventas_bp.route('/<int:id_venta>/pdf/resumen-cuenta')
@roles_required(*ROLES_VENTAS)
def pdf_resumen_cuenta(id_venta):
    """Ticket con un bloque de campos por producto (Codigo/Producto/Cantidad/
    Precio/Total), para entregar al cliente (formato termico 80mm)."""
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Paragraph

    venta = _venta_accesible_o_redirigir(id_venta)
    if not venta:
        return redirect(url_for('ventas.index'))

    styles = _estilos_ticket()
    n_items = len(venta['detalle'])
    alto = max(91 * mm, 76 * mm + n_items * 26 * mm)

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=(80 * mm, alto),
        leftMargin=3 * mm, rightMargin=3 * mm, topMargin=3 * mm, bottomMargin=3 * mm,
    )

    elementos = _encabezado_ticket(venta, styles)
    elementos.append(Paragraph(f"Total Venta: {venta['total']:.2f} Bs.", styles['TicketTotal']))
    elementos.append(Spacer(1, 6))

    for d in venta['detalle']:
        elementos.append(Paragraph(f"Código: {d['producto_codigo']}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Producto: {d['producto_nombre']}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Cantidad: {_fmt_cantidad(d['cantidad'])} {ventas_model.etiqueta_unidad(d)}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Precio: {d['precio_aplicado']:.2f} Bs.", styles['TicketNormal']))
        elementos.append(Paragraph(f"Total: {d['subtotal']:.2f} Bs.", styles['TicketNormal']))
        elementos.append(_separador_producto())

    elementos.extend(_pie_ticket(venta, styles, incluir_total=False))

    documento.build(elementos)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=False,
                      download_name=f"{venta['codigo_venta']}.pdf")


@ventas_bp.route('/<int:id_venta>/pdf/venta-almacen')
@roles_required(*ROLES_VENTAS)
def pdf_venta_almacen(id_venta):
    """Reporte de uso interno para almacen: quien registro/aprobo la venta
    y, por cada producto, cuanto se vendio y cuanto queda en stock (formato
    termico 80mm). Solo tiene sentido una vez aprobada la venta (antes de
    eso no hay aprobador ni se descarto el stock todavia)."""
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Paragraph

    venta = _venta_accesible_o_redirigir(id_venta)
    if not venta:
        return redirect(url_for('ventas.index'))
    if venta['estado'] != 'Aprobada':
        flash('El resumen para almacen solo esta disponible para ventas ya aprobadas.', 'warning')
        return redirect(url_for('ventas.index'))

    styles = _estilos_ticket()
    n_items = len(venta['detalle'])
    alto = max(96 * mm, 78 * mm + n_items * 32 * mm)

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=(80 * mm, alto),
        leftMargin=3 * mm, rightMargin=3 * mm, topMargin=3 * mm, bottomMargin=3 * mm,
    )

    elementos = [
        Paragraph('Resumen para Almacén', styles['TicketTitulo']),
        Paragraph(f"Generado el: {datetime.now():%d/%m/%Y %H:%M:%S}", styles['TicketNormal']),
        Paragraph(f"Código de Venta: {venta['codigo_venta'] or '-'}", styles['TicketNormal']),
        Paragraph(f"Usuario que generó la venta: {venta['usuario_nombre']}", styles['TicketNormal']),
        Paragraph(f"Usuario que aprobó la venta: {venta['aprobador_nombre'] or '-'}", styles['TicketNormal']),
        Paragraph(f"Total Venta: {venta['total']:.2f} Bs.", styles['TicketTotal']),
    ]
    elementos.append(Spacer(1, 6))

    for d in venta['detalle']:
        elementos.append(Paragraph(f"Código: {d['producto_codigo']}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Producto: {d['producto_nombre']}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Descripción: {d['producto_descripcion'] or '-'}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Posición: {d['producto_posicion'] or '-'}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Cantidad Vendida: {_fmt_cantidad(d['cantidad'])}", styles['TicketNormal']))
        elementos.append(Paragraph(f"Cantidad Restante: {_fmt_cantidad(d['producto_stock_actual'])}", styles['TicketNormal']))
        elementos.append(_separador_producto())

    elementos.append(Paragraph(
        "Nota: Este resumen es únicamente para uso interno del almacén y debe manejarse con confidencialidad.",
        styles['TicketNota'],
    ))
    elementos.append(Paragraph(f"Observaciones: {venta['observaciones'] or ''}", styles['TicketNormal']))

    documento.build(elementos)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=False,
                      download_name=f"{venta['codigo_venta']}.pdf")
