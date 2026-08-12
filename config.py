import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuracion general de la aplicacion.
    Mas adelante se puede separar en DevelopmentConfig / ProductionConfig."""

    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-cambiar-en-produccion')

    # Seguridad de la cookie de sesion (login)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Base de datos SQLite
    DATABASE = os.path.join(BASE_DIR, 'database', 'jugueteria.db')
    SCHEMA = os.path.join(BASE_DIR, 'database', 'schema.sql')

    # Carga de archivos (fotos de productos)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB maximo por archivo

    # Historial de archivos Excel importados (pestana Gestion de Archivos).
    # Fuera de static/ a proposito: contienen precios/costos del inventario
    # completo y static/ se sirve sin exigir sesion (ver ENDPOINTS_PUBLICOS
    # en app.py). Se descargan por una ruta autenticada (ver
    # archivos_controller.descargar_importacion), igual que los respaldos.
    IMPORT_FOLDER = os.path.join(BASE_DIR, 'uploads', 'importaciones')
    ALLOWED_IMPORT_EXTENSIONS = {'xlsx', 'xls'}

    # Fotos de facturas escritas a mano, capturadas por la app movil de
    # ventas por QR (ver controllers/api_controller.py). Fuera de static/
    # por el mismo motivo que IMPORT_FOLDER: son fotos de facturas reales
    # con datos del cliente (nombre, CI/NIT). Se sirven por una ruta
    # autenticada (ver ventas_controller.factura_imagen).
    FACTURAS_FOLDER = os.path.join(BASE_DIR, 'uploads', 'facturas')

    # Respaldos manuales de la base de datos (boton "Hacer respaldo" en
    # Gestion de Archivos). Fuera de static/ a proposito: static/ se sirve
    # sin exigir sesion (ver ENDPOINTS_PUBLICOS en app.py) y el .db tiene
    # datos sensibles (hashes de contrasena).
    RESPALDOS_FOLDER = os.path.join(BASE_DIR, 'database', 'respaldos')
