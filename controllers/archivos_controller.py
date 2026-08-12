"""
archivos_controller.py
Rutas (Controller) exclusivas de la pestana Gestion de Archivos:
historial de solo lectura de los archivos Excel que el cliente importo
desde Productos, en orden de llegada, y el respaldo manual de la base
de datos.
"""
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, send_from_directory, url_for

from models import archivos_model, database
from utilities.utilities import ROLES_GESTION, roles_required

archivos_bp = Blueprint('archivos', __name__, url_prefix='/archivos')


@archivos_bp.route('/')
@roles_required(*ROLES_GESTION)
def index():
    """Listado del historial de archivos importados."""
    busqueda = request.args.get('busqueda', '')
    orden = request.args.get('orden', '')
    archivos = archivos_model.get_all_archivos(busqueda=busqueda or None, orden=orden or None)
    return render_template(
        'archivos/archivos_view.html',
        archivos=archivos,
        busqueda=busqueda,
        orden_actual=orden or archivos_model.ORDEN_ARCHIVOS_DEFAULT,
    )


@archivos_bp.route('/respaldo', methods=['POST'])
@roles_required(*ROLES_GESTION)
def respaldo():
    """Genera una copia de la base de datos (jugueteria_AAAAMMDD_HHMMSS.db)
    y la entrega para descargar. Es manual (a diferencia de las
    migraciones, que ya no respaldan solas): se dispara con el boton
    "Hacer respaldo" de esta pantalla."""
    try:
        ruta_completa, nombre_archivo = database.crear_respaldo()
    except OSError:
        flash('No se pudo generar el respaldo de la base de datos.', 'danger')
        return redirect(url_for('archivos.index'))

    return send_file(
        ruta_completa,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype='application/octet-stream',
    )


@archivos_bp.route('/importacion/<int:id_archivo>')
@roles_required(*ROLES_GESTION)
def descargar_importacion(id_archivo):
    """Descarga un Excel importado del historial. Va por una ruta con
    sesion (en vez de servirlo directo desde static/, que no exige login)
    porque estos archivos traen precios y costos del inventario completo.
    El nombre en disco sale del registro en BD, nunca de la URL, asi que
    no hay forma de pedir un archivo fuera de IMPORT_FOLDER."""
    archivo = archivos_model.get_archivo(id_archivo)
    if not archivo:
        flash('El archivo solicitado no existe.', 'danger')
        return redirect(url_for('archivos.index'))

    return send_from_directory(
        current_app.config['IMPORT_FOLDER'],
        archivo['nombre_guardado'],
        as_attachment=True,
        download_name=archivo['nombre_original'],
    )
