"""
app.py
Punto de entrada de la aplicacion. Usa el patron Application Factory
y registra un Blueprint por cada pestana del sistema (modularidad por pestana).
"""
import os

from flask import Flask, flash, redirect, request, session, url_for

from config import Config
from models import database
from models.database import inicializar_base_de_datos
from controllers.auth_controller import auth_bp
from controllers.inicio_controller import inicio_bp
from controllers.productos_controller import productos_bp
from controllers.ventas_controller import ventas_bp
from controllers.movimientos_controller import movimientos_bp
from controllers.im_ex_controller import im_ex_bp
from controllers.personal_controller import personal_bp
from controllers.archivos_controller import archivos_bp
from models import productos_model, ventas_model

# Endpoints accesibles sin sesion iniciada
ENDPOINTS_PUBLICOS = {'auth.login', 'static'}


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

    if Config.SECRET_KEY == 'dev-secret-key-cambiar-en-produccion':
        print(
            "🟡 Aviso: se esta usando la SECRET_KEY de desarrollo por defecto. "
            "Define la variable de entorno SECRET_KEY con un valor propio para mayor seguridad."
        )

    # 1. Inicializar la base de datos al arrancar
    inicializar_base_de_datos()

    # Registro de la gestion de conexion a la BD (cierre automatico por request)
    database.init_app(app)

    # Registro de Blueprints -> un modulo por pestana
    app.register_blueprint(auth_bp)
    app.register_blueprint(inicio_bp)
    app.register_blueprint(productos_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(movimientos_bp)
    app.register_blueprint(im_ex_bp)
    app.register_blueprint(personal_bp)
    app.register_blueprint(archivos_bp)
    # A futuro: roles_bp, sucursales_bp, traspasos_bp, clientes_bp...

    # Inicializa las tablas de la BD si todavia no existen, y asegura que
    # el usuario admin semilla tenga una contrasena hasheada utilizable
    with app.app_context():
        database.init_db()
        database.asegurar_password_admin_por_defecto()

    @app.before_request
    def requerir_sesion():
        """Exige login para todas las rutas, excepto login y estaticos."""
        if request.endpoint in ENDPOINTS_PUBLICOS or request.endpoint is None:
            return
        if 'id_personal' not in session:
            flash('Debes iniciar sesion para continuar.', 'warning')
            return redirect(url_for('auth.login'))

    @app.context_processor
    def inyectar_contadores_sidebar():
        """Contadores livianos que se muestran como badges en el sidebar
        (cantidad de productos, items en el carrito de la sesion actual)."""
        if 'id_personal' not in session:
            return {}
        return {
            'sidebar_total_productos': productos_model.contar_productos(),
            'sidebar_ventas_pendientes': ventas_model.contar_pendientes(),
        }

    return app


app = create_app()

if __name__ == '__main__':
    # El modo debug (consola interactiva de Werkzeug) solo se activa si se
    # pide explicitamente por variable de entorno: dejarlo prendido por
    # defecto expondria un debugger capaz de ejecutar codigo arbitrario.
    modo_debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=modo_debug, port=5000)
