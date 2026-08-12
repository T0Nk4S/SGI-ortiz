"""
app.py
Punto de entrada de la aplicacion. Usa el patron Application Factory
y registra un Blueprint por cada pestana del sistema (modularidad por pestana).
"""
import os

from flask import Flask, flash, jsonify, redirect, request, session, url_for

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
from controllers.api_controller import api_bp
from models import productos_model, ventas_model
from utilities.utilities import ROL_EMPLEADO, ROL_SUPER_ADMIN, ROLES_GESTION, ROLES_TODOS, ROLES_VENTAS

# Endpoints accesibles sin sesion iniciada. 'api.login' es el login que usa
# la app movil (Flutter) -> equivalente a 'auth.login' para el panel web.
ENDPOINTS_PUBLICOS = {'auth.login', 'api.login', 'api.ping', 'static'}


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
    app.register_blueprint(api_bp)
    # A futuro: roles_bp, sucursales_bp, traspasos_bp, clientes_bp...

    # Constantes de rol disponibles en los templates (sidebar, botones),
    # para no repetir listas de roles literales en Jinja.
    app.jinja_env.globals.update(
        ROL_SUPER_ADMIN=ROL_SUPER_ADMIN,
        ROLES_GESTION=ROLES_GESTION,
        ROLES_VENTAS=ROLES_VENTAS,
        ROLES_TODOS=ROLES_TODOS,
    )

    # Inicializa las tablas de la BD si todavia no existen, y asegura que
    # el usuario admin semilla tenga una contrasena hasheada utilizable
    with app.app_context():
        database.init_db()
        database.asegurar_password_admin_por_defecto()

    @app.errorhandler(404)
    @app.errorhandler(500)
    def manejar_errores_api(error):
        """Bajo /api/* (la app movil) nunca hay que devolver una pagina
        HTML de error: el cliente Dart intenta parsear la respuesta como
        JSON siempre, y si recibe HTML el parseo revienta con una
        excepcion generica -la app termina mostrando "no se pudo conectar
        con el servidor" aunque el problema haya sido, por ejemplo, una
        ruta que no matcheo (ver producto_por_codigo y el conversor
        <path:codigo>). request.path (no request.blueprint) porque un 404
        de ruta no encontrada no llega a resolver ningun blueprint."""
        if request.path.startswith('/api/'):
            codigo = getattr(error, 'code', 500) or 500
            return jsonify({'error': 'Recurso no encontrado.' if codigo == 404 else 'Error interno del servidor.'}), codigo
        return error

    @app.before_request
    def requerir_sesion():
        """Exige login para todas las rutas, excepto login y estaticos.
        Para el blueprint 'api' (consumido por la app movil, no por un
        navegador) no tiene sentido un redirect HTML: responde 401 JSON."""
        if request.endpoint in ENDPOINTS_PUBLICOS or request.endpoint is None:
            return
        if 'id_personal' not in session:
            if request.blueprint == 'api':
                return jsonify({'error': 'No autenticado'}), 401
            flash('Debes iniciar sesion para continuar.', 'warning')
            return redirect(url_for('auth.login'))

    def _contadores_sidebar():
        """Empleado ve solo sus propias ventas pendientes en el contador;
        los demas roles con acceso a Ventas ven el total. Compartido entre
        el context_processor (primer render de cada pagina) y el endpoint
        JSON de abajo (sondeo periodico para actualizar sin recargar)."""
        filtro_personal = session.get('id_personal') if session.get('rol') == ROL_EMPLEADO else None
        return {
            'total_productos': productos_model.contar_productos(),
            'ventas_pendientes': ventas_model.contar_pendientes(id_personal_filtro=filtro_personal),
            'faltantes': productos_model.contar_faltantes(),
        }

    @app.context_processor
    def inyectar_contadores_sidebar():
        """Contadores livianos que se muestran como badges en el sidebar
        (cantidad de productos, ventas pendientes, faltantes por reponer)."""
        if 'id_personal' not in session:
            return {}
        contadores = _contadores_sidebar()
        return {
            'sidebar_total_productos': contadores['total_productos'],
            'sidebar_ventas_pendientes': contadores['ventas_pendientes'],
            'sidebar_faltantes': contadores['faltantes'],
        }

    @app.route('/contadores-sidebar')
    def contadores_sidebar_json():
        """Version JSON de _contadores_sidebar, para que el sidebar y las
        paginas de Ventas/Inicio se actualicen solos por sondeo (ver el
        script al final de templates/shared/base.html) sin que el usuario
        tenga que refrescar a mano -por ejemplo, cuando una venta se
        registra desde la app movil mientras el panel web esta abierto."""
        return jsonify(_contadores_sidebar())

    return app


app = create_app()

if __name__ == '__main__':
    # El modo debug (consola interactiva de Werkzeug) solo se activa si se
    # pide explicitamente por variable de entorno: dejarlo prendido por
    # defecto expondria un debugger capaz de ejecutar codigo arbitrario.
    modo_debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    # host 0.0.0.0: la app movil (Flutter) se conecta por la IP de LAN de
    # esta PC, no por localhost -> tiene que escuchar en todas las interfaces.
    # threaded=True: sin esto, el servidor de desarrollo atiende un solo
    # request a la vez -> con el sondeo automatico cada 3s del panel web
    # (base.html) y de la app movil (Inicio/Ventas) sumado a un escaneo de
    # QR, las requests se encolaban y el celular podia agotar su timeout
    # (10s) esperando turno, mostrando "no se pudo conectar" aunque si
    # habia conexion. Con threaded=True cada request se atiende en su
    # propio hilo y dejan de pisarse.
    app.run(debug=modo_debug, host='0.0.0.0', port=5000, threaded=True)
