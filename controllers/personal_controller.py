"""
personal_controller.py
Rutas (Controller) exclusivas de la pestana Personal (administracion de
los usuarios del sistema). Solo accesible para usuarios con rol
Administrador (ver utilities.admin_required).
"""
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import personal_model
from utilities.utilities import admin_required

personal_bp = Blueprint('personal', __name__, url_prefix='/personal')


@personal_bp.route('/')
@admin_required
def index():
    """Listado de usuarios (Read) con filtro por estado y busqueda."""
    estado_raw = request.args.get('estado', '')
    busqueda = request.args.get('busqueda', '')
    estado = int(estado_raw) if estado_raw in ('0', '1') else None

    personal = personal_model.get_all_personal(estado=estado, busqueda=busqueda or None)
    return render_template(
        'personal/personal_view.html',
        personal=personal,
        estado_filtro=estado_raw,
        busqueda=busqueda,
    )


@personal_bp.route('/nuevo', methods=['GET', 'POST'])
@admin_required
def nuevo():
    """Formulario de creacion (Create)."""
    if request.method == 'POST':
        data, error_contrasena = _extraer_datos_formulario(request, requiere_contrasena=True)

        if not personal_model.usuario_disponible(data['usuario']):
            flash('Ya existe una cuenta con ese nombre de usuario.', 'danger')
        elif error_contrasena:
            flash(error_contrasena, 'danger')
        else:
            try:
                personal_model.create_personal(data)
                flash(f"Usuario \"{data['usuario']}\" creado correctamente.", 'success')
                return redirect(url_for('personal.index'))
            except sqlite3.IntegrityError:
                flash('Ya existe una cuenta con ese CI o usuario. Deben ser unicos.', 'danger')

    return render_template('personal/personal_form.html', persona=None, accion='Crear')


@personal_bp.route('/editar/<int:id_personal>', methods=['GET', 'POST'])
@admin_required
def editar(id_personal):
    """Formulario de edicion (Update)."""
    persona = personal_model.get_personal(id_personal)
    if not persona:
        flash('El usuario solicitado no existe.', 'danger')
        return redirect(url_for('personal.index'))

    if request.method == 'POST':
        data, error_contrasena = _extraer_datos_formulario(request, requiere_contrasena=False)

        if not personal_model.usuario_disponible(data['usuario'], id_personal_excluir=id_personal):
            flash('Ya existe otra cuenta con ese nombre de usuario.', 'danger')
        elif error_contrasena:
            flash(error_contrasena, 'danger')
        elif (
            persona['rol'] == 'Administrador'
            and data['rol'] != 'Administrador'
            and personal_model.contar_administradores_activos(id_personal_excluir=id_personal) == 0
        ):
            flash('No puedes quitar el rol de Administrador al ultimo administrador activo.', 'danger')
        else:
            try:
                personal_model.update_personal(id_personal, data)
                flash(f"Usuario \"{data['usuario']}\" actualizado correctamente.", 'success')
                return redirect(url_for('personal.index'))
            except sqlite3.IntegrityError:
                flash('Ya existe otra cuenta con ese CI o usuario. Deben ser unicos.', 'danger')

    return render_template('personal/personal_form.html', persona=persona, accion='Editar')


@personal_bp.route('/eliminar/<int:id_personal>', methods=['POST'])
@admin_required
def eliminar(id_personal):
    """Elimina un usuario (Delete), protegiendo contra auto-eliminacion y
    contra dejar el sistema sin ningun administrador."""
    persona = personal_model.get_personal(id_personal)
    if not persona:
        flash('El usuario solicitado no existe.', 'danger')
        return redirect(url_for('personal.index'))

    if id_personal == session.get('id_personal'):
        flash('No puedes eliminar tu propia cuenta mientras tienes la sesion iniciada.', 'danger')
        return redirect(url_for('personal.index'))

    if (
        persona['rol'] == 'Administrador'
        and personal_model.contar_administradores_activos(id_personal_excluir=id_personal) == 0
    ):
        flash('No puedes eliminar al ultimo administrador activo del sistema.', 'danger')
        return redirect(url_for('personal.index'))

    try:
        personal_model.delete_personal(id_personal)
        flash(f"Usuario \"{persona['usuario']}\" eliminado.", 'success')
    except sqlite3.IntegrityError:
        flash(
            f"No se puede eliminar \"{persona['usuario']}\" porque ya tiene ventas u otros "
            "movimientos registrados. Puedes desactivarlo en su lugar.",
            'danger',
        )
    return redirect(url_for('personal.index'))


@personal_bp.route('/estado/<int:id_personal>', methods=['POST'])
@admin_required
def cambiar_estado(id_personal):
    """Alterna el estado Activo/Inactivo de un usuario, con las mismas
    protecciones que la eliminacion."""
    persona = personal_model.get_personal(id_personal)
    if not persona:
        flash('El usuario solicitado no existe.', 'danger')
        return redirect(url_for('personal.index'))

    if id_personal == session.get('id_personal'):
        flash('No puedes desactivar tu propia cuenta mientras tienes la sesion iniciada.', 'danger')
        return redirect(url_for('personal.index'))

    if (
        persona['rol'] == 'Administrador'
        and persona['estado'] == 1
        and personal_model.contar_administradores_activos(id_personal_excluir=id_personal) == 0
    ):
        flash('No puedes desactivar al ultimo administrador activo del sistema.', 'danger')
        return redirect(url_for('personal.index'))

    personal_model.cambiar_estado(id_personal)
    flash('Estado del usuario actualizado.', 'success')
    return redirect(url_for('personal.index'))


def _extraer_datos_formulario(request, requiere_contrasena):
    """Convierte los datos crudos del formulario en un dict listo para
    insertar/actualizar, validando la contrasena en el mismo paso."""
    contrasena = request.form.get('contrasena', '')
    error_contrasena = None
    if requiere_contrasena and not contrasena:
        error_contrasena = 'La contrasena es obligatoria para crear un usuario.'
    elif contrasena and len(contrasena) < 6:
        error_contrasena = 'La contrasena debe tener al menos 6 caracteres.'

    data = {
        'nombres': request.form.get('nombres', '').strip(),
        'apellido_paterno': request.form.get('apellido_paterno', '').strip(),
        'apellido_materno': request.form.get('apellido_materno', '').strip() or None,
        'ci': request.form.get('ci', '').strip(),
        'telefono': request.form.get('telefono', '').strip() or None,
        'usuario': request.form.get('usuario', '').strip().lower(),
        'contrasena': contrasena,
        'rol': request.form.get('rol', 'Cajero'),
        'estado': 1,
    }
    return data, error_contrasena
