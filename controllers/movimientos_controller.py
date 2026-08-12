"""
movimientos_controller.py
Rutas (Controller) exclusivas de la pestana Movimientos (Kardex).
"""
from flask import Blueprint, render_template, request

from models import movimientos_model
from utilities.utilities import ROLES_VENTAS, roles_required

movimientos_bp = Blueprint('movimientos', __name__, url_prefix='/movimientos')


@movimientos_bp.route('/')
@roles_required(*ROLES_VENTAS)
def index():
    """Listado de movimientos del Kardex con filtros opcionales."""
    busqueda = request.args.get('busqueda', '')
    tipo_filtro = request.args.get('tipo_movimiento', '')
    orden = request.args.get('orden', '')

    movimientos = movimientos_model.get_movimientos(
        busqueda=busqueda or None,
        tipo_movimiento=tipo_filtro or None,
        orden=orden or None,
    )

    return render_template(
        'movimientos/movimientos_view.html',
        movimientos=movimientos,
        busqueda=busqueda,
        tipo_filtro=tipo_filtro,
        orden_actual=orden or movimientos_model.ORDEN_MOVIMIENTOS_DEFAULT,
    )
