"""
movimientos_controller.py
Rutas (Controller) exclusivas de la pestana Movimientos (Kardex).
"""
from flask import Blueprint, render_template, request

from models import movimientos_model

movimientos_bp = Blueprint('movimientos', __name__, url_prefix='/movimientos')


@movimientos_bp.route('/')
def index():
    """Listado de movimientos del Kardex con filtros opcionales."""
    busqueda = request.args.get('busqueda', '')
    tipo_filtro = request.args.get('tipo_movimiento', '')

    movimientos = movimientos_model.get_movimientos(
        busqueda=busqueda or None,
        tipo_movimiento=tipo_filtro or None,
    )

    return render_template(
        'movimientos/movimientos_view.html',
        movimientos=movimientos,
        busqueda=busqueda,
        tipo_filtro=tipo_filtro,
    )
