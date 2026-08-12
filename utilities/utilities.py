"""
utilities.py
Funciones reutilizables por CUALQUIER pestana del sistema
(no logica exclusiva de productos, usuarios, ventas, etc).
"""
import io
import os
import re
import socket
import unicodedata
import uuid
from functools import wraps

import qrcode
from flask import flash, jsonify, redirect, session, url_for


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


# Roles del sistema (ver database/schema.sql: personal.rol). Se agrupan
# aca para reusarlos tanto en decoradores de rutas como en los templates
# (expuestos a Jinja en app.py) sin repetir listas literales por todos lados.
ROL_SUPER_ADMIN = 'Super Admin'
ROL_ADMIN = 'Admin'
ROL_EMPLEADO = 'Empleado'
ROL_BODEGA = 'Bodega'

# CRUD de productos, importar/exportar Excel, Gestion de Archivos.
ROLES_GESTION = (ROL_SUPER_ADMIN, ROL_ADMIN)
# Todo lo de Ventas + Movimientos + reponer stock desde la alerta de Inicio.
ROLES_VENTAS = (ROL_SUPER_ADMIN, ROL_ADMIN, ROL_EMPLEADO)
# Inicio y ver el catalogo de Productos: los 4 roles.
ROLES_TODOS = (ROL_SUPER_ADMIN, ROL_ADMIN, ROL_EMPLEADO, ROL_BODEGA)


def roles_required(*roles_permitidos):
    """Exige que el usuario en sesion tenga uno de los roles indicados.
    Uso: @roles_required(ROL_SUPER_ADMIN) o @roles_required(*ROLES_GESTION)."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if 'id_personal' not in session:
                return redirect(url_for('auth.login'))
            if session.get('rol') not in roles_permitidos:
                flash('No tienes permisos para acceder a esa seccion.', 'danger')
                return redirect(url_for('inicio.index'))
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def api_roles_required(*roles_permitidos):
    """Igual que roles_required, pero para endpoints JSON (blueprint api):
    en vez de flash+redirect (que una app nativa no puede seguir), responde
    401/403 en JSON. La sesion la exige antes que nada requerir_sesion en
    app.py; esto solo agrega el filtro por rol."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if 'id_personal' not in session:
                return jsonify({'error': 'No autenticado'}), 401
            if session.get('rol') not in roles_permitidos:
                return jsonify({'error': 'No tienes permisos para acceder a esa seccion.'}), 403
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def generar_imagen_qr(texto):
    """Genera un codigo QR en memoria (PNG) a partir de un texto plano.
    Devuelve un BytesIO listo para usar con send_file. Generico a
    proposito: no sabe nada de productos ni de ninguna otra entidad,
    solo convierte texto en imagen de QR."""
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(texto)
    qr.make(fit=True)
    imagen = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def resolver_orden_sql(orden, opciones, default):
    """Resuelve un ORDER BY dinamico de forma segura: `opciones` es un dict
    {valor_de_formulario: 'fragmento SQL de confianza'} definido a mano en
    cada modelo (whitelist), nunca generado a partir de texto libre del
    usuario. Si `orden` no es una clave conocida, se usa `opciones[default]`.
    Asi el select de "Ordenar por" de cada pestana no puede inyectar SQL:
    en el peor caso, cae al orden por defecto."""
    return opciones.get(orden, opciones[default])


def obtener_ip_local():
    """IP local (LAN) de esta PC dentro de la red del negocio. Se muestra
    en Inicio como guia rapida: si el router reasigna la IP del servidor
    (ej. tras reiniciarlo), el dueno/encargado sabe al toque cual es la
    IP nueva que hay que cargar en la app movil de cada celular.

    Truco estandar: 'conectar' un socket UDP a una IP externa no envia
    ningun dato de verdad (UDP no arma conexion), pero obliga al sistema
    operativo a resolver por que interfaz de red saldria ese trafico -asi
    se obtiene la IP LAN real sin necesitar internet de verdad ni depender
    del nombre de host (que puede resolver mal si hay varios adaptadores,
    ej. una VPN)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def formato_moneda(valor):
    """Formatea un numero como moneda para mostrarlo en las vistas.
    Ej: 1500.5 -> 'Bs. 1,500.50'"""
    try:
        return f"Bs. {float(valor):,.2f}"
    except (ValueError, TypeError):
        return "Bs. 0.00"
