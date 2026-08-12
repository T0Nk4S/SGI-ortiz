"""
auth_controller.py
Rutas (Controller) de autenticacion: inicio y cierre de sesion.
No pertenece a ninguna pestana de negocio, por eso vive fuera de los
blueprints de dominio (productos, ventas, movimientos, etc).
"""
import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import personal_model

auth_bp = Blueprint('auth', __name__)

# Bloqueo simple contra fuerza bruta: tras varios intentos fallidos
# seguidos, se obliga a esperar antes de volver a intentar. En memoria
# porque la app corre en un unico proceso local (no en un servidor web).
MAX_INTENTOS_FALLIDOS = 5
VENTANA_BLOQUEO_SEGUNDOS = 300
_intentos_fallidos = {}


def _usuario_bloqueado(usuario):
    ahora = time.time()
    intentos = [t for t in _intentos_fallidos.get(usuario, []) if ahora - t < VENTANA_BLOQUEO_SEGUNDOS]
    _intentos_fallidos[usuario] = intentos
    return len(intentos) >= MAX_INTENTOS_FALLIDOS


def _registrar_intento_fallido(usuario):
    _intentos_fallidos.setdefault(usuario, []).append(time.time())


def _limpiar_intentos(usuario):
    _intentos_fallidos.pop(usuario, None)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Formulario de inicio de sesion. Si ya hay sesion activa, redirige
    directo al dashboard."""
    if 'id_personal' in session:
        return redirect(url_for('inicio.index'))

    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip().lower()
        contrasena = request.form.get('contrasena', '')

        if _usuario_bloqueado(usuario):
            flash('Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.', 'danger')
            return render_template('auth/login_view.html', usuario=usuario)

        personal = personal_model.verificar_credenciales(usuario, contrasena)
        if personal:
            _limpiar_intentos(usuario)
            session.clear()
            session.permanent = True
            session['id_personal'] = personal['id_personal']
            session['usuario'] = personal['usuario']
            session['rol'] = personal['rol']
            session['nombre_completo'] = f"{personal['nombres']} {personal['apellido_paterno']}"
            if usuario == 'admin' and contrasena == 'admin123':
                flash(
                    'Estas usando la cuenta admin con la contrasena de fabrica (admin123). '
                    'Cambiala desde Personal cuanto antes.', 'warning',
                )
            return redirect(url_for('inicio.index'))

        _registrar_intento_fallido(usuario)
        flash('Usuario o contrasena incorrectos.', 'danger')
        return render_template('auth/login_view.html', usuario=usuario)

    return render_template('auth/login_view.html', usuario='')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Cierra la sesion actual. Se expone solo por POST para que no se
    pueda cerrar sesion desde un simple enlace o precarga del navegador."""
    session.clear()
    flash('Sesion cerrada correctamente.', 'success')
    return redirect(url_for('auth.login'))
