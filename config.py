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

    # Historial de archivos Excel importados (pestana Gestion de Archivos)
    IMPORT_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'importaciones')
    ALLOWED_IMPORT_EXTENSIONS = {'xlsx', 'xls'}
