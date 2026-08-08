"""
inicio_controller.py
Rutas (Controller) exclusivas de la pestana Inicio (Dashboard).
"""
from flask import Blueprint, render_template

from models import productos_model

inicio_bp = Blueprint('inicio', __name__)


@inicio_bp.route('/')
def index():
    """Dashboard principal con estadisticas rapidas del inventario."""
    stats = productos_model.get_estadisticas()
    return render_template('inicio/inicio_view.html', stats=stats)
