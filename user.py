import pymysql
from werkzeug.security import generate_password_hash
from models.db import get_db_connection


def get_user_by_email(email):
    """Devuelve el usuario (dict) por correo o None si no existe."""
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT id, nombre, correo, password, avatar, telefono, current_streak, longest_streak FROM usuario WHERE correo = %s', (email,))
            return cur.fetchone()
    finally:
        conn.close()



def create_user(nombre, correo, plain_password):
    """Crea un usuario con password hasheada."""
    hashed = generate_password_hash(plain_password)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO usuario (nombre, correo, password) VALUES (%s, %s, %s)', (nombre, correo, hashed))
        conn.commit()
    finally:
        conn.close()


def update_user_password(identifier, new_plain_password):
    """Actualiza la contraseña del usuario identificado por correo o por id.
    Si 'identifier' es int se usa WHERE id = %s; si es str se usa WHERE correo = %s.
    """
    hashed = generate_password_hash(new_plain_password)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if isinstance(identifier, int):
                cur.execute('UPDATE usuario SET password = %s WHERE id = %s', (hashed, identifier))
            else:
                cur.execute('UPDATE usuario SET password = %s WHERE correo = %s', (hashed, identifier))
        conn.commit()
    finally:
        conn.close()


def update_user_email(user_id, new_email):
    """Actualiza el correo del usuario identificado por user_id."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE usuario SET correo = %s WHERE id = %s', (new_email, user_id))
        conn.commit()
    finally:
        conn.close()


def update_user_name(user_id, new_name):
    """Actualiza el nombre del usuario identificado por user_id."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE usuario SET nombre = %s WHERE id = %s', (new_name, user_id))
        conn.commit()
    finally:
        conn.close()


def update_user_avatar(user_id, avatar_filename):
    """Actualiza el avatar del usuario identificado por user_id."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE usuario SET avatar = %s WHERE id = %s', (avatar_filename, user_id))
        conn.commit()
    finally:
        conn.close()


def update_user_phone(user_id, telefono):
    """Actualiza el teléfono del usuario identificado por user_id."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE usuario SET telefono = %s WHERE id = %s', (telefono, user_id))
        conn.commit()
    finally:
        conn.close()


def update_user_streak(user_id, current_streak, longest_streak=None):
    """Actualiza las rachas del usuario."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if longest_streak is not None:
                cur.execute('UPDATE usuario SET current_streak = %s, longest_streak = %s WHERE id = %s', 
                          (current_streak, longest_streak, user_id))
            else:
                cur.execute('UPDATE usuario SET current_streak = %s WHERE id = %s', (current_streak, user_id))
        conn.commit()
    finally:
        conn.close()


def get_user_streak(user_id):
    """Obtiene las rachas del usuario."""
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT current_streak, longest_streak FROM usuario WHERE id = %s', (user_id,))
            return cur.fetchone()
    finally:
        conn.close()
