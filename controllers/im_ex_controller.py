import io
import os

import pandas as pd
from flask import Blueprint, current_app, request, redirect, session, url_for, flash, send_file

from models import archivos_model
from models.productos_model import guardar_o_actualizar_desde_excel, obtener_todos_los_productos
from utilities.utilities import guardar_archivo_importado

im_ex_bp = Blueprint('im_ex', __name__)

@im_ex_bp.route('/exportar-productos-pdf', methods=['GET'])
def exportar_productos_pdf():
    """Exporta el inventario de productos a un PDF sencillo."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    productos = obtener_todos_los_productos()

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph('Productos', styles['Title']))
    elementos.append(Spacer(1, 12))

    datos = [['Código 1', 'Nombre', 'Precio Venta', 'Costo', 'Stock']]
    for producto in productos:
        datos.append([
            producto['codigo_1'] or '',
            producto['nombre'] or '',
            producto['precio_venta'] or 0,
            producto['costo'] or 0,
            producto['stock'] or 0,
        ])

    tabla = Table(datos, colWidths=[45, 180, 55, 55, 45])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    elementos.append(tabla)

    documento.build(elementos)
    buffer.seek(0)

    return send_file(
        buffer,
        download_name='productos.pdf',
        mimetype='application/pdf',
        as_attachment=True,
    )

@im_ex_bp.route('/importar-productos-excel', methods=['POST'])
def importar_productos_excel():
    if 'archivo_excel' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('productos.index'))
    
    file = request.files['archivo_excel']
    
    if file.filename == '':
        flash('Por favor selecciona un archivo Excel.', 'danger')
        return redirect(url_for('productos.index'))

    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            # Guardar una copia fisica del archivo para el historial de
            # Gestion de Archivos, antes de leerlo con pandas
            nombre_guardado = guardar_archivo_importado(file, current_app.config['IMPORT_FOLDER'])
            ruta_guardada = os.path.join(current_app.config['IMPORT_FOLDER'], nombre_guardado)

            # Leer el archivo Excel
            df = pd.read_excel(ruta_guardada)

            # Limpiar nombres de columnas: eliminar espacios al inicio/final
            df.columns = [str(col).strip() for col in df.columns]

            registros_procesados = 0
            
            for index, row in df.iterrows():
                # Obtener Código1 eliminando ceros/espacios extras
                codigo_1_raw = row.get('Código1') or row.get('Codigo1') or row.get('Codigo 1')
                
                if pd.notna(codigo_1_raw):
                    codigo_1 = str(codigo_1_raw).strip()
                    
                    # Ignorar filas vacías o encabezados repetidos
                    if codigo_1 and codigo_1.lower() != 'nan':
                        
                        # Función auxiliar para convertir a flotante seguro
                        def to_float(val):
                            try:
                                return float(val) if pd.notna(val) else 0.0
                            except (ValueError, TypeError):
                                return 0.0

                        # Función auxiliar para convertir a entero seguro
                        def to_int(val, default=0):
                            try:
                                return int(val) if pd.notna(val) else default
                            except (ValueError, TypeError):
                                return default

                        datos_producto = {
                            'nombre': str(row.get('Nombre', '')).strip() if pd.notna(row.get('Nombre')) else '',
                            'codigo_1': codigo_1,
                            'codigo_2': str(row.get('Código2', '')).strip() if pd.notna(row.get('Código2')) else '',
                            'descripcion': str(row.get('Descripción', '')).strip() if pd.notna(row.get('Descripción')) else '',
                            'precio_unidad_facturado': to_float(row.get('Precio Unidad Facturado')),
                            'precio_docena_facturado': to_float(row.get('Precio Docena Facturado')),
                            'precio_paquete_facturado': to_float(row.get('Precio Paquete Facturado')),
                            'precio_paquete_neto': to_float(row.get('Precio Paquete Normal')),
                            'precio_docena_neto': to_float(row.get('Precio Docena Normal')),
                            'precio_docena_comercial': to_float(row.get('Precio Docena Caja')),
                            'descuento_porcentaje': to_float(row.get('Descuento (%)')),
                            'incremento_porcentaje': to_float(row.get('Incremento (%)')),
                            'marca': str(row.get('Marca', '')).strip() if pd.notna(row.get('Marca')) else '',
                            'pcs_paquete': to_int(row.get('Piezas por Paquete'), default=1),
                            'pcs_caja': to_int(row.get('Piezas por Caja'), default=1),
                            'ubicacion_nombre': str(row.get('Ubicación', '')).strip() if pd.notna(row.get('Ubicación')) else '',
                            'cantidad': to_int(row.get('Cantidad'), default=0),
                            'posicion': str(row.get('Posición', '')).strip() if pd.notna(row.get('Posición')) else '',
                            'venta_fraccionada': str(row.get('Docena (si/no)', 'No')).strip().capitalize() if pd.notna(row.get('Docena (si/no)')) else 'No'
                        }

                        guardar_o_actualizar_desde_excel(datos_producto)
                        registros_procesados += 1

            archivos_model.registrar_archivo(
                nombre_original=file.filename,
                nombre_guardado=nombre_guardado,
                id_personal=session.get('id_personal'),
                registros_procesados=registros_procesados,
            )

            if registros_procesados > 0:
                flash(f'¡Éxito! Se procesaron {registros_procesados} productos correctamente.', 'success')
            else:
                flash('No se encontraron registros válidos en el archivo Excel. Verifica que las columnas tengan los encabezados correctos (ej: Código1, Nombre, Cantidad).', 'warning')

        except Exception as e:
            flash(f'Error al procesar el archivo Excel: {str(e)}', 'danger')
    else:
        flash('Formato de archivo no válido. Sube un archivo Excel (.xlsx o .xls).', 'warning')

    return redirect(url_for('productos.index'))