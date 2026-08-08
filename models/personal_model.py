"""
personal_model.py
Capa de acceso a datos (Model) de Personal (usuarios del sistema:
Administrador, Empleado, Cajero). Incluye el CRUD completo usado por la
pestana "Usuarios" y la verificacion de credenciales usada por el login.
"""
from werkzeug.security import check_password_hash, generate_password_hash

from models.database import get_db


def get_personal_activo():
    """Lista de personal activo, para usar en selects (ej. Ventas)."""
    db = get_db()
    return db.execute(
        "SELECT * FROM personal WHERE estado = 1 ORDER BY nombres ASC"
    ).fetchall()


def get_personal(id_personal):
    """Obtiene un registro de personal por id."""
    db = get_db()
    return db.execute(
        "SELECT * FROM personal WHERE id_personal = ?", (id_personal,)
    ).fetchone()


def get_all_personal(estado=None, busqueda=None):
    """Lista de personal para la pantalla de administracion, con filtro
    opcional por estado (0/1) y por texto (nombre, apellidos, ci o usuario)."""
    db = get_db()
    query = "SELECT * FROM personal WHERE 1 = 1"
    params = []

    if estado is not None:
        query += " AND estado = ?"
        params.append(estado)

    if busqueda:
        query += """ AND (
            nombres LIKE ? OR apellido_paterno LIKE ? OR apellido_materno LIKE ?
            OR ci LIKE ? OR usuario LIKE ?
        )"""
        like = f"%{busqueda}%"
        params.extend([like, like, like, like, like])

    query += " ORDER BY nombres ASC"
    return db.execute(query, params).fetchall()


def get_personal_por_usuario(usuario):
    """Busca un registro de personal por su nombre de usuario (login)."""
    db = get_db()
    return db.execute(
        "SELECT * FROM personal WHERE usuario = ?", (usuario,)
    ).fetchone()


def usuario_disponible(usuario, id_personal_excluir=None):
    """True si nadie mas (aparte de id_personal_excluir) tiene ese usuario."""
    db = get_db()
    if id_personal_excluir:
        fila = db.execute(
            "SELECT id_personal FROM personal WHERE usuario = ? AND id_personal != ?",
            (usuario, id_personal_excluir),
        ).fetchone()
    else:
        fila = db.execute(
            "SELECT id_personal FROM personal WHERE usuario = ?", (usuario,)
        ).fetchone()
    return fila is None


def contar_administradores_activos(id_personal_excluir=None):
    """Cuenta administradores activos, para evitar dejar el sistema sin
    ningun administrador al eliminar, desactivar o cambiar el rol de uno."""
    db = get_db()
    query = "SELECT COUNT(*) AS c FROM personal WHERE rol = 'Administrador' AND estado = 1"
    params = []
    if id_personal_excluir:
        query += " AND id_personal != ?"
        params.append(id_personal_excluir)
    return db.execute(query, params).fetchone()['c']


def verificar_credenciales(usuario, contrasena):
    """Valida usuario/contrasena contra la BD (hash con werkzeug).
    Devuelve la fila de personal si son correctos y la cuenta esta activa;
    None en cualquier otro caso (usuario inexistente, inactivo o clave
    incorrecta), sin distinguir el motivo para no facilitar enumeracion
    de usuarios validos."""
    personal = get_personal_por_usuario(usuario)
    if not personal or personal['estado'] != 1:
        return None
    if not check_password_hash(personal['contrasena_hash'], contrasena):
        return None
    return personal


def create_personal(data):
    """Inserta un nuevo usuario. `data` incluye la clave 'contrasena' en
    texto plano, que se convierte a hash antes de guardarla."""
    db = get_db()
    data = dict(data)
    data['contrasena_hash'] = generate_password_hash(data.pop('contrasena'))
    cursor = db.execute(
        """
        INSERT INTO personal (
            nombres, apellido_paterno, apellido_materno, ci, telefono,
            usuario, contrasena_hash, rol, estado
        ) VALUES (
            :nombres, :apellido_paterno, :apellido_materno, :ci, :telefono,
            :usuario, :contrasena_hash, :rol, :estado
        )
        """,
        data,
    )
    db.commit()
    return cursor.lastrowid


def update_personal(id_personal, data):
    """Actualiza los datos de un usuario existente. Si `data['contrasena']`
    viene vacio, la contrasena actual se conserva sin cambios."""
    db = get_db()
    data = dict(data)
    data['id_personal'] = id_personal
    nueva_contrasena = data.pop('contrasena', '')

    if nueva_contrasena:
        data['contrasena_hash'] = generate_password_hash(nueva_contrasena)
        db.execute(
            """
            UPDATE personal SET
                nombres = :nombres,
                apellido_paterno = :apellido_paterno,
                apellido_materno = :apellido_materno,
                ci = :ci,
                telefono = :telefono,
                usuario = :usuario,
                rol = :rol,
                contrasena_hash = :contrasena_hash
            WHERE id_personal = :id_personal
            """,
            data,
        )
    else:
        db.execute(
            """
            UPDATE personal SET
                nombres = :nombres,
                apellido_paterno = :apellido_paterno,
                apellido_materno = :apellido_materno,
                ci = :ci,
                telefono = :telefono,
                usuario = :usuario,
                rol = :rol
            WHERE id_personal = :id_personal
            """,
            data,
        )
    db.commit()


def delete_personal(id_personal):
    """Elimina definitivamente a un usuario.
    NOTA: si ya tiene ventas o movimientos asociados, esto fallara por
    restriccion de llave foranea (a proposito, para proteger el
    historial). En ese caso, usar cambiar_estado() para desactivarlo."""
    db = get_db()
    db.execute("DELETE FROM personal WHERE id_personal = ?", (id_personal,))
    db.commit()


def cambiar_estado(id_personal):
    """Alterna el estado de un usuario entre Activo (1) <-> Inactivo (0)."""
    db = get_db()
    fila = db.execute(
        "SELECT estado FROM personal WHERE id_personal = ?", (id_personal,)
    ).fetchone()
    if fila:
        nuevo_estado = 0 if fila['estado'] == 1 else 1
        db.execute(
            "UPDATE personal SET estado = ? WHERE id_personal = ?",
            (nuevo_estado, id_personal),
        )
        db.commit()
