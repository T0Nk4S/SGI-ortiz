"""
productos_controller.py
Rutas (Controller) exclusivas de la pestana Productos.
Conecta las vistas (templates/productos) con el modelo (models/productos_model).
"""
import io
import sqlite3

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, session, url_for

from models import movimientos_model, productos_model, ventas_model
from utilities.utilities import (
    ROLES_GESTION,
    ROLES_TODOS,
    ROLES_VENTAS,
    eliminar_imagen,
    generar_imagen_qr,
    guardar_imagen,
    parse_float,
    parse_int,
    roles_required,
)

productos_bp = Blueprint(
    'productos',
    __name__,
    url_prefix='/productos',
)


@productos_bp.route('/')
@roles_required(*ROLES_TODOS)
def index():
    """Listado de productos (Read) con filtro por estado, busqueda y orden."""
    estado = request.args.get('estado', '')
    busqueda = request.args.get('busqueda', '')
    orden = request.args.get('orden', '')
    productos = productos_model.get_all_productos(estado=estado or None, busqueda=busqueda or None, orden=orden or None)
    return render_template(
        'productos/productos_view.html',
        productos=productos,
        estado_filtro=estado,
        busqueda=busqueda,
        orden_actual=orden or productos_model.ORDEN_PRODUCTOS_DEFAULT,
    )


@productos_bp.route('/nuevo', methods=['GET', 'POST'])
@roles_required(*ROLES_GESTION)
def nuevo():
    """Formulario de creacion (Create)."""
    ubicaciones = productos_model.get_ubicaciones()

    if request.method == 'POST':
        data = _extraer_datos_formulario(request)
        try:
            id_producto = productos_model.create_producto(data)
            if data['cantidad'] > 0:
                movimientos_model.registrar_movimiento(
                    id_producto=id_producto,
                    id_personal=session.get('id_personal'),
                    tipo_movimiento='INGRESO_MERCADERIA',
                    cantidad=data['cantidad'],
                    motivo_nota='Alta de producto - stock inicial',
                )
            flash(f"Producto \"{data['nombre']}\" creado correctamente.", 'success')
            return redirect(url_for('productos.index'))
        except sqlite3.IntegrityError:
            flash('Ya existe un producto con esa combinacion de Codigo 1 y Codigo 2.', 'danger')

    return render_template(
        'productos/productos_form.html',
        producto=None,
        ubicaciones=ubicaciones,
        accion='Crear',
    )


@productos_bp.route('/editar/<int:id_producto>', methods=['GET', 'POST'])
@roles_required(*ROLES_GESTION)
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
            diferencia_cantidad = data['cantidad'] - producto['cantidad']
            if diferencia_cantidad != 0:
                movimientos_model.registrar_movimiento(
                    id_producto=id_producto,
                    id_personal=session.get('id_personal'),
                    tipo_movimiento='AJUSTE_INVENTARIO',
                    cantidad=diferencia_cantidad,
                    motivo_nota='Ajuste manual de stock desde edicion de producto',
                )
            flash(f"Producto \"{data['nombre']}\" actualizado correctamente.", 'success')
            return redirect(url_for('productos.index'))
        except sqlite3.IntegrityError:
            flash('Ya existe otro producto con esa combinacion de Codigo 1 y Codigo 2.', 'danger')

    return render_template(
        'productos/productos_form.html',
        producto=producto,
        ubicaciones=ubicaciones,
        accion='Editar',
    )


@productos_bp.route('/ver/<int:id_producto>')
@roles_required(*ROLES_TODOS)
def ver(id_producto):
    """Detalle completo de un producto (Read individual)."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        flash('El producto solicitado no existe.', 'danger')
        return redirect(url_for('productos.index'))
    return render_template('productos/productos_detail.html', producto=producto)


@productos_bp.route('/eliminar/<int:id_producto>', methods=['POST'])
@roles_required(*ROLES_GESTION)
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
@roles_required(*ROLES_GESTION)
def cambiar_estado(id_producto):
    """Alterna el estado Activo/Inactivo de un producto."""
    productos_model.cambiar_estado(id_producto)
    flash('Estado del producto actualizado.', 'success')
    return redirect(url_for('productos.index'))


@productos_bp.route('/reponer/<int:id_producto>', methods=['GET', 'POST'])
@roles_required(*ROLES_VENTAS)
def reponer(id_producto):
    """Accion angosta de reposicion de stock: a diferencia de `editar`,
    solo toca la cantidad (nada de precio/nombre/etc), pensada para que
    Empleado pueda resolver la alerta de faltante de Inicio sin darle
    acceso al formulario completo de edicion de productos."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        flash('El producto solicitado no existe.', 'danger')
        return redirect(url_for('inicio.index'))

    if request.method == 'POST':
        nueva_cantidad = parse_float(request.form.get('cantidad'), producto['cantidad'])
        diferencia = nueva_cantidad - producto['cantidad']
        productos_model.actualizar_cantidad(id_producto, nueva_cantidad)
        if diferencia != 0:
            movimientos_model.registrar_movimiento(
                id_producto=id_producto,
                id_personal=session.get('id_personal'),
                tipo_movimiento='AJUSTE_INVENTARIO',
                cantidad=diferencia,
                motivo_nota='Reposicion de stock desde alerta de Inicio',
            )
        flash(f"Stock de \"{producto['nombre']}\" actualizado.", 'success')
        return redirect(url_for('inicio.index'))

    return render_template('productos/productos_reponer.html', producto=producto)


@productos_bp.route('/qr/<int:id_producto>/imagen.png')
@roles_required(*ROLES_TODOS)
def qr_imagen(id_producto):
    """Genera al vuelo la imagen PNG del codigo QR de un producto (texto
    plano con sus datos clave: sirve para escanear sin depender de que
    el sistema este accesible por red, ideal para etiquetas impresas)."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        return '', 404

    buffer = generar_imagen_qr(_texto_qr_producto(producto))
    return send_file(buffer, mimetype='image/png')


def _texto_qr_producto(producto):
    """Arma el texto plano que se codifica en el QR de un producto.
    codigo_1 no identifica un producto de forma unica por si solo (ver
    productos_model.get_producto_por_codigo): si el producto tiene codigo_2
    cargado, se agrega una linea "Codigo2: X" para que el escaneo pueda
    resolverlo sin ambiguedad. Las etiquetas impresas antes de este cambio
    solo traen "Codigo:" -siguen funcionando mientras ese codigo_1 no
    choque con el de otro producto; si choca, hay que reimprimirlas."""
    lineas = [
        'El Comercio Ortiz',
        producto['nombre'],
        f"Codigo: {producto['codigo_1']}",
    ]
    if producto['codigo_2']:
        lineas.append(f"Codigo2: {producto['codigo_2']}")
    lineas.append(
        f"PUF: Bs {producto['precio_unidad_facturado']:.2f}  |  PDF: Bs {producto['precio_docena_facturado']:.2f}"
    )
    ubicacion = ' '.join(filter(None, [producto['ubicacion_nombre'], producto['posicion']]))
    if ubicacion:
        lineas.append(f'Ubicacion: {ubicacion}')
    return '\n'.join(lineas)


@productos_bp.route('/etiqueta/<int:id_producto>')
@roles_required(*ROLES_TODOS)
def etiqueta(id_producto):
    """Genera un PDF de etiqueta/sticker (QR + info del producto) listo
    para imprimir, en el mismo tamano fisico que las etiquetas de codigo
    de barras que ya usa el cliente. ?tamano=pequena (5.6x4.5cm, default)
    o ?tamano=grande (10x15cm)."""
    producto = productos_model.get_producto(id_producto)
    if not producto:
        return '', 404

    tamano = request.args.get('tamano', 'pequena')
    buffer = _generar_etiqueta_pdf(producto, tamano)
    return send_file(
        buffer, mimetype='application/pdf', as_attachment=False,
        download_name=f"etiqueta_{producto['codigo_1']}.pdf",
    )


# Nombre amigable de cada tarifa para las etiquetas (ver
# ventas_model.CAMPO_POR_TIPO_PRECIO para el mapeo tipo -> columna).
_ETIQUETAS_TARIFA = {
    'PUF': 'Unidad',
    'PDF': 'Docena Fact.',
    'PPF': 'Paquete Fact.',
    'PPN': 'Paquete Neto',
    'PDN': 'Docena Neto',
    'PDC': 'Docena Com.',
}


def _generar_etiqueta_pdf(producto, tamano):
    """Arma el PDF de la etiqueta: 'pequena' (5.6x4.5cm) trae QR + nombre +
    codigo + precio unidad, pensada para el espacio angosto de una
    etiqueta de estante; 'grande' (10x15cm) trae ademas todas las tarifas
    con precio cargado (mismo criterio que ventas_model.tarifas_disponibles)
    y la ubicacion."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import BaseDocTemplate, Frame, Image, PageTemplate, Paragraph, Spacer, Table, TableStyle

    es_grande = tamano == 'grande'
    ancho = 10 * cm if es_grande else 5.6 * cm
    alto = 15 * cm if es_grande else 4.5 * cm
    margen = 5 * mm if es_grande else 1.5 * mm
    tam_qr = 6 * cm  # solo se usa en la grande; la chica calcula el suyo segun la columna (ver abajo)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        'EtiquetaNombre', parent=styles['Normal'], alignment=1,
        fontName='Helvetica-Bold', fontSize=13 if es_grande else 7,
        leading=15 if es_grande else 8,
    ))
    styles.add(ParagraphStyle(
        'EtiquetaCodigo', parent=styles['Normal'], alignment=1,
        fontSize=9 if es_grande else 5.5, leading=10 if es_grande else 6.5,
        textColor='#4b5563',
    ))
    styles.add(ParagraphStyle(
        'EtiquetaPrecio', parent=styles['Normal'], alignment=1,
        fontName='Helvetica-Bold', fontSize=16 if es_grande else 10,
        leading=18 if es_grande else 11, spaceBefore=2,
    ))
    styles.add(ParagraphStyle(
        'EtiquetaColumnaEncabezado', parent=styles['Normal'], alignment=1,
        fontName='Helvetica-Bold', fontSize=10, leading=11, textColor='#6b7280',
    ))
    styles.add(ParagraphStyle(
        'EtiquetaColumnaPrecio', parent=styles['Normal'], alignment=1,
        fontName='Helvetica-Bold', fontSize=14, leading=16,
    ))
    styles.add(ParagraphStyle(
        'EtiquetaUbicacion', parent=styles['Normal'], alignment=1,
        fontSize=8, leading=9, textColor='#6b7280',
    ))

    buffer_qr = generar_imagen_qr(_texto_qr_producto(producto))

    if es_grande:
        elementos = [Image(buffer_qr, width=tam_qr, height=tam_qr, hAlign='CENTER')]
        elementos.append(Spacer(1, 2 * mm))
        elementos.append(Paragraph(producto['nombre'], styles['EtiquetaNombre']))

        codigos = f"Cod: {producto['codigo_1']}"
        if producto['codigo_2']:
            codigos += f" / {producto['codigo_2']}"
        elementos.append(Paragraph(codigos, styles['EtiquetaCodigo']))

        # Dos columnas, mismo criterio que ya usa el carrito de escritorio
        # para agrupar tarifas (ventas_model.TARIFAS_SIN_FACTURA/
        # TARIFAS_CON_FACTURA): izquierda las tarifas "normal"/"comercial"
        # (sin el incremento de facturar), derecha las "_facturado".
        columna_sin_factura = [
            tipo for tipo in ventas_model.TARIFAS_SIN_FACTURA
            if (producto[ventas_model.CAMPO_POR_TIPO_PRECIO[tipo]] or 0) > 0
        ]
        columna_con_factura = [
            tipo for tipo in ventas_model.TARIFAS_CON_FACTURA
            if (producto[ventas_model.CAMPO_POR_TIPO_PRECIO[tipo]] or 0) > 0
        ]
        filas = max(len(columna_sin_factura), len(columna_con_factura))

        if filas:
            def _celda(columna, indice):
                if indice >= len(columna):
                    return ''
                tipo = columna[indice]
                precio = producto[ventas_model.CAMPO_POR_TIPO_PRECIO[tipo]]
                return Paragraph(
                    f"{_ETIQUETAS_TARIFA[tipo]}<br/>Bs {precio:.2f}",
                    styles['EtiquetaColumnaPrecio'],
                )

            datos_tabla = [[
                Paragraph('Sin factura', styles['EtiquetaColumnaEncabezado']),
                Paragraph('Con factura', styles['EtiquetaColumnaEncabezado']),
            ]]
            for indice in range(filas):
                datos_tabla.append([_celda(columna_sin_factura, indice), _celda(columna_con_factura, indice)])

            ancho_columna = (ancho - 2 * margen) / 2
            tabla_precios = Table(datos_tabla, colWidths=[ancho_columna, ancho_columna])
            tabla_precios.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LINEAFTER', (0, 0), (0, -1), 0.75, colors.HexColor('#e5e7eb')),
                ('LINEBELOW', (0, 0), (-1, 0), 0.75, colors.HexColor('#e5e7eb')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elementos.append(Spacer(1, 2 * mm))
            elementos.append(tabla_precios)

        ubicacion = ' '.join(filter(None, [producto['ubicacion_nombre'], producto['posicion']]))
        if ubicacion:
            elementos.append(Spacer(1, 3 * mm))
            elementos.append(Paragraph(f"Ubicacion: {ubicacion}", styles['EtiquetaUbicacion']))
    else:
        # QR a la izquierda, info a la derecha (en vez de todo apilado
        # verticalmente): mas prolijo, tipo etiqueta de precio real, y de
        # paso libera todo el alto de la etiqueta para el texto en vez de
        # competir con el QR por espacio vertical.
        ancho_util = ancho - 2 * margen
        ancho_qr_col = ancho_util * 0.55
        ancho_info_col = ancho_util - ancho_qr_col
        tam_qr_chica = ancho_qr_col - 4

        nombre = producto['nombre']
        if len(nombre) > 40:
            nombre = nombre[:39].rstrip() + '…'

        columna_info = [
            Paragraph(nombre, styles['EtiquetaNombre']),
            Paragraph(f"Cod: {producto['codigo_1']}", styles['EtiquetaCodigo']),
        ]

        # Todas las tarifas con precio cargado (mismo criterio de "tarifa
        # disponible" que ventas_model.tarifas_disponibles: no asume que
        # siempre es PUF, hay productos que solo se venden por paquete o
        # docena). Con siglas (PUF/PDF/...) como en la BD/tabla de
        # Productos, no con nombres largos. Con 1 sola tarifa se muestra
        # grande; con varias, todas juntas en una sola fila (sin columnas)
        # para dejarle mas ancho al QR.
        tarifas_con_precio = ventas_model.tarifas_disponibles(producto)
        if len(tarifas_con_precio) == 1:
            tipo_unico = tarifas_con_precio[0]
            precio = producto[ventas_model.CAMPO_POR_TIPO_PRECIO[tipo_unico]]
            columna_info.append(Paragraph(f"{tipo_unico} Bs {precio:.2f}", styles['EtiquetaPrecio']))
        elif tarifas_con_precio:
            if len(tarifas_con_precio) <= 2:
                fuente, interlineado = 8.5, 10
            elif len(tarifas_con_precio) <= 4:
                fuente, interlineado = 7, 8.5
            else:
                fuente, interlineado = 6, 7.5
            estilo_precio_fila = ParagraphStyle(
                'EtiquetaPrecioFila', parent=styles['Normal'], alignment=1,
                fontName='Helvetica-Bold', fontSize=fuente, leading=interlineado,
            )
            texto_precios = '&nbsp;&nbsp;&nbsp;'.join(
                f"{tipo} {producto[ventas_model.CAMPO_POR_TIPO_PRECIO[tipo]]:.2f}"
                for tipo in tarifas_con_precio
            )
            columna_info.append(Paragraph(texto_precios, estilo_precio_fila))

        imagen_qr = Image(buffer_qr, width=tam_qr_chica, height=tam_qr_chica, hAlign='CENTER')
        tabla_chica = Table([[imagen_qr, columna_info]], colWidths=[ancho_qr_col, ancho_info_col])
        tabla_chica.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 3),
            ('LEFTPADDING', (1, 0), (1, 0), 3),
            ('RIGHTPADDING', (1, 0), (1, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        # Tabla exterior de 1 celda: centra el bloque QR+info en el alto
        # COMPLETO de la etiqueta. Sin esto, el Frame apila el contenido
        # desde arriba y deja un espacio en blanco abajo si el bloque no
        # llena los 4.5cm -se veia descentrado.
        tabla_centrada = Table([[tabla_chica]], colWidths=[ancho_util], rowHeights=[alto - 2 * margen])
        tabla_centrada.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        elementos = [tabla_centrada]

    # Frame con padding interno en 0: SimpleDocTemplate por si solo le
    # suma ~6pt extra de relleno a cada margen, que en una etiqueta tan
    # chica alcanza para tirar el contenido a una segunda pagina en
    # blanco. Con esto el area util es exactamente alto/ancho menos
    # `margen`, sin sorpresas -critico porque el tamano fisico del
    # sticker no es negociable.
    buffer = io.BytesIO()
    documento = BaseDocTemplate(buffer, pagesize=(ancho, alto), leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0)
    frame = Frame(
        margen, margen, ancho - 2 * margen, alto - 2 * margen,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    documento.addPageTemplates([PageTemplate(id='etiqueta', frames=[frame])])
    documento.build(elementos)
    buffer.seek(0)
    return buffer


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
        'cantidad': parse_float(request.form.get('cantidad')),
        'pcs_paquete': parse_int(request.form.get('pcs_paquete')),
        'pcs_caja': parse_int(request.form.get('pcs_caja')),
        'posicion': request.form.get('posicion', '').strip(),
        'venta_fraccionada': request.form.get('venta_fraccionada', 'No'),
        'descuento_porcentaje': parse_float(request.form.get('descuento_porcentaje'), 0),
        'incremento_porcentaje': parse_float(request.form.get('incremento_porcentaje'), 0),
        'estado': producto_actual['estado'] if producto_actual else 'Activo',
    }
