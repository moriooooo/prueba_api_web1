from datetime import datetime, date, time, timedelta
from models.db import get_db_connection
import pymysql


def ensure_notification_table():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    message TEXT,
                    fecha_programada DATETIME,
                    is_read TINYINT(1) DEFAULT 0,
                    fecha_envio DATETIME NULL,
                    tipo VARCHAR(50) DEFAULT 'recordatorio',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX (user_id),
                    INDEX (is_read),
                    INDEX (fecha_programada)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            ''')
            needed = {
                'fecha_programada': "DATETIME NULL",
                'is_read': "TINYINT(1) DEFAULT 0",
                'fecha_envio': "DATETIME NULL",
                'tipo': "VARCHAR(50) DEFAULT 'recordatorio'",
            }
            for col, col_def in needed.items():
                cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_notifications' AND COLUMN_NAME = %s", (col,))
                exists = cur.fetchone()
                try:
                    count = exists[0] if isinstance(exists, (list, tuple)) else list(exists.values())[0]
                except Exception:
                    count = 1
                if count == 0:
                    try:
                        cur.execute(f"ALTER TABLE user_notifications ADD COLUMN {col} {col_def}")
                        print(f"[DB MIGRATE] Added column {col} to user_notifications")
                    except Exception as e:
                        print(f"[DB MIGRATE] Failed to add column {col}:", e)
        conn.commit()
    finally:
        conn.close()


def create_notifications_for_routine(user_id, rutina_id, nombre, horario_time):
    if isinstance(horario_time, str):
        try:
            hh, mm = horario_time.split(':')[:2]
            horario = time(int(hh), int(mm))
        except Exception:
            horario = time(9, 0)
    else:
        horario = horario_time

    today = date.today()
    scheduled = datetime.combine(today, horario)
    intervals = [-6, -4, -2, 0, 2, 4]

    msgs = []
    for minutes in intervals:
        due = scheduled + timedelta(minutes=minutes)
        title = f"Recordatorio: {nombre}"
        message = f"[RUTINA_ID:{rutina_id}] Recordatorio: Rutina '{nombre}' programada a las {horario.strftime('%H:%M')}"
        msgs.append((user_id, title, message, due))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sql = 'INSERT INTO user_notifications (user_id, title, message, fecha_programada, tipo) VALUES (%s, %s, %s, %s, %s)'
            for u_id, title, msg, due in msgs:
                try:
                    cur.execute(sql, (u_id, title, msg, due, 'recordatorio'))
                    try:
                        inserted_id = cur.lastrowid
                    except Exception:
                        inserted_id = None
                    print(f"Inserted notification id={inserted_id} user={u_id} due={due}")
                except Exception as e:
                    print('Error insert notification:', e, 'params=', (u_id, title, msg, due))
        conn.commit()
    finally:
        conn.close()


def get_due_notifications(limit=20, user_id=None):
    now = datetime.now()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if user_id:
                cur.execute('SELECT id, title, message FROM user_notifications WHERE is_read = 0 AND fecha_programada <= %s AND user_id = %s ORDER BY fecha_programada LIMIT %s', (now, user_id, limit))
            else:
                cur.execute('SELECT id, title, message FROM user_notifications WHERE is_read = 0 AND fecha_programada <= %s ORDER BY fecha_programada LIMIT %s', (now, limit))
            rows = cur.fetchall()
            return rows
    finally:
        conn.close()


def create_notifications_for_date(target_date):
    dias_semana = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    day_name = dias_semana[target_date.strftime('%A')]

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id_rutina, nombre, horario, id_usuario FROM rutina WHERE dias LIKE %s', (f'%{day_name}%',))
            rutinas = cur.fetchall()

            intervals = [-6, -4, -2, 0, 2, 4]
            insert_sql = 'INSERT INTO user_notifications (user_id, title, message, fecha_programada, tipo) VALUES (%s, %s, %s, %s, %s)'

            for r in rutinas:
                if isinstance(r, dict):
                    rut_id = r.get('id_rutina')
                    nombre = r.get('nombre')
                    horario = r.get('horario')
                    user_id = r.get('id_usuario')
                else:
                    try:
                        rut_id, nombre, horario, user_id = r
                    except Exception:
                        continue

                try:
                    parts = str(horario).split(':')
                    hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
                    from datetime import time as _time
                    base_time = _time(hh, mm)
                except Exception:
                    from datetime import time as _time
                    base_time = _time(9,0)

                from datetime import datetime as _dt
                for off in intervals:
                    due = _dt.combine(target_date, base_time) + timedelta(minutes=off)
                    marker = f"[RUTINA_ID:{rut_id}]"
                    cur.execute('SELECT id FROM user_notifications WHERE message LIKE %s AND fecha_programada = %s AND user_id = %s', (f"%{marker}%", due, user_id))
                    if cur.fetchone():
                        continue
                    title = f"Recordatorio: {nombre}"
                    message = f"{marker} Recordatorio: Rutina '{nombre}' programada a las {str(horario)}"
                    cur.execute(insert_sql, (user_id, title, message, due, 'recordatorio'))
        conn.commit()
    finally:
        conn.close()


def mark_delivered(notification_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE user_notifications SET is_read = 1, fecha_envio = %s WHERE id = %s', (datetime.now(), notification_id))
        conn.commit()
    finally:
        conn.close()


def delete_notifications_for_routine(rutina_id):
    marker = f"[RUTINA_ID:{rutina_id}]"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM user_notifications WHERE message LIKE %s', (f"%{marker}%",))
        conn.commit()
    finally:
        conn.close()


def create_email_reminder_for_routine(user_id, rutina_id, nombre, horario_time, minutes_before=30):
    """Crea un único recordatorio por email para la rutina. Se programa 'minutes_before' minutos antes del horario."""
    from datetime import datetime, date
    from datetime import time as _time

    if isinstance(horario_time, str):
        try:
            hh, mm = horario_time.split(':')[:2]
            horario = _time(int(hh), int(mm))
        except Exception:
            horario = _time(9, 0)
    else:
        horario = horario_time

    target_dt = datetime.combine(date.today(), horario) - timedelta(minutes=minutes_before)
    title = f"Recuerda tu rutina: {nombre}"
    marker = f"[EMAIL_RUTINA:{rutina_id}]"
    message = f"{marker} Te recordamos tu rutina '{nombre}' y te animamos a completarla hoy. ¡Tú puedes!"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Evitar duplicados exactos
            cur.execute('SELECT id FROM user_notifications WHERE message LIKE %s AND fecha_programada = %s AND user_id = %s', (f"%{marker}%", target_dt, user_id))
            if cur.fetchone():
                return
            cur.execute('INSERT INTO user_notifications (user_id, title, message, fecha_programada, tipo) VALUES (%s, %s, %s, %s, %s)', (user_id, title, message, target_dt, 'email_once'))
    finally:
        conn.commit()
        conn.close()


def get_pending_email_reminders(limit=100):
    """Devuelve recordatorios por email pendientes (tipo='email_once', no enviados y fecha_programada <= ahora).
    Retorna filas con campos: id, user_id, title, message, fecha_programada, correo
    """
    now = datetime.now()
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT n.id, n.user_id, n.title, n.message, n.fecha_programada, u.correo
                FROM user_notifications n
                JOIN usuario u ON u.id = n.user_id
                WHERE n.tipo = 'email_once' AND n.fecha_envio IS NULL AND n.fecha_programada <= %s
                ORDER BY n.fecha_programada ASC
                LIMIT %s
            """, (now, limit))
            return cur.fetchall()
    finally:
        conn.close()


def mark_notification_sent(notification_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE user_notifications SET fecha_envio = %s, is_read = 1 WHERE id = %s', (datetime.now(), notification_id))
        conn.commit()
    finally:
        conn.close()


try:
    ensure_notification_table()
except Exception:
    pass
