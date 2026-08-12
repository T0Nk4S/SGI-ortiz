"""
inicio_controller.py
Rutas (Controller) exclusivas de la pestana Inicio (Dashboard).
"""
from flask import Blueprint, render_template, request

from models import productos_model
from utilities.utilities import obtener_ip_local

inicio_bp = Blueprint('inicio', __name__)


@inicio_bp.route('/')
def index():
    """Dashboard principal con estadisticas rapidas del inventario."""
    stats = productos_model.get_estadisticas()
    # SERVER_PORT refleja el puerto real en el que esta corriendo el
    # servidor (no un valor fijo a mano), sea cual sea la IP/hostname que
    # el usuario haya usado para llegar a esta pagina.
    puerto_servidor = request.environ.get('SERVER_PORT', '5000')
    return render_template(
        'inicio/inicio_view.html',
        stats=stats,
        ip_servidor=obtener_ip_local(),
        puerto_servidor=puerto_servidor,
    )
