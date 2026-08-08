"""
archivos_controller.py
Rutas (Controller) exclusivas de la pestana Gestion de Archivos:
historial de solo lectura de los archivos Excel que el cliente importo
desde Productos, en orden de llegada.
"""
from flask import Blueprint, render_template, request

from models import archivos_model

archivos_bp = Blueprint('archivos', __name__, url_prefix='/archivos')


@archivos_bp.route('/')
def index():
    """Listado del historial de archivos importados."""
    busqueda = request.args.get('busqueda', '')
    archivos = archivos_model.get_all_archivos(busqueda=busqueda or None)
    return render_template(
        'archivos/archivos_view.html',
        archivos=archivos,
        busqueda=busqueda,
    )
