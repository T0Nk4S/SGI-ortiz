"""
utilities.py
Funciones reutilizables por CUALQUIER pestana del sistema
(no logica exclusiva de productos, usuarios, ventas, etc).
"""
import os
import re
import unicodedata
import uuid
from functools import wraps

from flask import flash, redirect, session, url_for


def allowed_file(filename, allowed_extensions):
    """Verifica que la extension del archivo este permitida."""
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in allowed_extensions
    )


def slugify(texto):
    """Convierte un texto (ej. nombre de producto) en un nombre de archivo
    seguro: sin acentos, minusculas, espacios y simbolos reemplazados por '_'.
    Ej: 'Muñeca Frozen (Grande)' -> 'muneca_frozen_grande'"""
    texto = str(texto or '').strip().lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'[^a-z0-9]+', '_', texto)
    texto = texto.strip('_')
    return texto or 'producto'


def guardar_imagen(file, upload_folder, allowed_extensions, nombre_base=None):
    """Guarda un archivo de imagen subido. Si se entrega `nombre_base`
    (normalmente el nombre del producto), el archivo se guarda con ese
    nombre; si ya existe un archivo con ese nombre, se le agrega un
    sufijo numerico para no sobrescribirlo. Si no se entrega `nombre_base`,
    se usa un identificador unico como respaldo.
    Devuelve el nombre del archivo guardado o None si no se subio nada
    o la extension no es valida."""
    if file and file.filename and allowed_file(file.filename, allowed_extensions):
        extension = file.filename.rsplit('.', 1)[1].lower()
        base = slugify(nombre_base) if nombre_base else uuid.uuid4().hex

        os.makedirs(upload_folder, exist_ok=True)

        nombre_final = f"{base}.{extension}"
        ruta = os.path.join(upload_folder, nombre_final)
        contador = 1
        while os.path.exists(ruta):
            nombre_final = f"{base}_{contador}.{extension}"
            ruta = os.path.join(upload_folder, nombre_final)
            contador += 1

        file.save(ruta)
        return nombre_final
    return None


def guardar_archivo_importado(file, carpeta_destino):
    """Guarda una copia fisica de un archivo importado (ej. Excel de
    Productos), con un sufijo unico para no sobrescribir importaciones
    anteriores y conservar el orden real de llegada.
    Devuelve el nombre del archivo guardado."""
    os.makedirs(carpeta_destino, exist_ok=True)

    nombre_base, extension = os.path.splitext(file.filename)
    extension = extension.lower()
    nombre_final = f"{slugify(nombre_base)}_{uuid.uuid4().hex[:8]}{extension}"

    file.save(os.path.join(carpeta_destino, nombre_final))
    return nombre_final


def eliminar_imagen(upload_folder, filename):
    """Elimina un archivo de imagen del disco si existe."""
    if filename:
        filepath = os.path.join(upload_folder, filename)
        if os.path.exists(filepath):
            os.remove(filepath)


def parse_float(value, default=0.0):
    """Convierte de forma segura un valor de formulario a float."""
    try:
        return float(value) if value not in (None, '') else default
    except (ValueError, TypeError):
        return default


def parse_int(value, default=0):
    """Convierte de forma segura un valor de formulario a int."""
    try:
        return int(value) if value not in (None, '') else default
    except (ValueError, TypeError):
        return default


def login_required(vista):
    """Exige una sesion iniciada para acceder a la vista decorada.
    El guard global de app.py ya cubre todas las rutas, pero se deja
    disponible para usarlo de forma explicita en rutas puntuales."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if 'id_personal' not in session:
            return redirect(url_for('auth.login'))
        return vista(*args, **kwargs)
    return envoltura


def admin_required(vista):
    """Exige que el usuario en sesion tenga rol Administrador.
    Usado en las rutas de administracion de Personal (Usuarios)."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if 'id_personal' not in session:
            return redirect(url_for('auth.login'))
        if session.get('rol') != 'Administrador':
            flash('No tienes permisos para acceder a esa seccion.', 'danger')
            return redirect(url_for('inicio.index'))
        return vista(*args, **kwargs)
    return envoltura


def formato_moneda(valor):
    """Formatea un numero como moneda para mostrarlo en las vistas.
    Ej: 1500.5 -> 'Bs. 1,500.50'"""
    try:
        return f"Bs. {float(valor):,.2f}"
    except (ValueError, TypeError):
        return "Bs. 0.00"
