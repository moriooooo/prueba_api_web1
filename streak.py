from datetime import datetime, date, timedelta
from models.db import get_db_connection

__all__ = ['mark_task_completed', 'get_global_streak', 'evaluate_daily_streak', 'check_and_reset_missed_streaks', 'debug_streak_status']


def ensure_streak_tables():
    """Asegura que las tablas necesarias existan. Ahora solo verifica item_diario."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Verificar que item_diario existe
            cur.execute("""
                CREATE TABLE IF NOT EXISTS item_diario (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    id_item INT NOT NULL,
                    id_usuario INT NOT NULL,
                    fecha DATE NOT NULL,
                    completado BOOLEAN DEFAULT FALSE,
                    completado_en DATETIME NULL,
                    FOREIGN KEY (id_item) REFERENCES rutina_item(id_item) ON DELETE CASCADE,
                    FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_item_fecha (id_item, fecha)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            
            # Asegurar que usuario tiene las columnas de racha
            cur.execute("SHOW COLUMNS FROM usuario LIKE 'current_streak'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE usuario ADD COLUMN current_streak INT DEFAULT 0")
            
            cur.execute("SHOW COLUMNS FROM usuario LIKE 'longest_streak'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE usuario ADD COLUMN longest_streak INT DEFAULT 0")
                
        conn.commit()
    finally:
        conn.close()


def mark_task_completed(user_id, tarea_id):
    """Marca una tarea como completada y actualiza la racha."""
    today = date.today()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Insertar o actualizar en item_diario
            cur.execute('''
                INSERT INTO item_diario (id_usuario, id_item, fecha, completado, completado_en)
                VALUES (%s, %s, %s, 1, %s)
                ON DUPLICATE KEY UPDATE 
                completado = 1, completado_en = %s
            ''', (user_id, tarea_id, today, datetime.now(), datetime.now()))
        
        conn.commit()
        
        # Evaluar racha después de completar tarea
        evaluate_daily_streak(user_id)
        
    finally:
        conn.close()


def get_global_streak(user_id):
    """Obtiene la racha actual del usuario."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT current_streak FROM usuario WHERE id = %s', (user_id,))
            row = cur.fetchone()
            if not row:
                return 0
            if isinstance(row, dict):
                return row.get('current_streak', 0) or 0
            try:
                return row[0] or 0
            except Exception:
                return 0
    finally:
        conn.close()


def check_and_reset_missed_streaks(user_id):
    """Verifica si el usuario perdió su racha por no completar tareas en días anteriores."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    # Mapeo de días
    dias_semana = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Obtener la racha actual
            cur.execute('SELECT current_streak FROM usuario WHERE id = %s', (user_id,))
            row = cur.fetchone()
            
            if not row:
                return
            
            if isinstance(row, dict):
                current_streak = row.get('current_streak', 0) or 0
            else:
                try:
                    current_streak = row[0] or 0
                except Exception:
                    return
            
            # Si no hay racha activa, no hay nada que hacer
            if current_streak == 0:
                return
            
            # Verificar ayer si tenía rutinas y las completó
            day_name = dias_semana[yesterday.strftime('%A')]
            
            # ¿Había rutinas programadas para ayer?
            cur.execute('SELECT COUNT(*) AS cnt FROM rutina WHERE id_usuario = %s AND dias LIKE %s', 
                       (user_id, f'%{day_name}%'))
            r = cur.fetchone()
            has_rutinas = False
            if r:
                if isinstance(r, dict):
                    has_rutinas = (r.get('cnt', 0) or 0) > 0
                else:
                    try:
                        has_rutinas = (r[0] or 0) > 0
                    except Exception:
                        has_rutinas = False
            
            if has_rutinas:
                # Verificar si completó todas las tareas de ayer
                cur.execute("""
                    SELECT COUNT(ri.id_item) AS total
                    FROM rutina r
                    JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                    WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                """, (user_id, day_name))
                t = cur.fetchone()
                total_items = 0
                if t:
                    if isinstance(t, dict):
                        total_items = t.get('total', 0) or 0
                    else:
                        try:
                            total_items = t[0] or 0
                        except Exception:
                            total_items = 0

                # Contar completados de ayer
                cur.execute("""
                    SELECT COUNT(DISTINCT id.id_item) AS completados
                    FROM item_diario id
                    JOIN rutina_item ri ON id.id_item = ri.id_item
                    JOIN rutina r ON ri.id_rutina = r.id_rutina
                    WHERE id.id_usuario = %s AND id.fecha = %s AND id.completado = 1
                    AND FIND_IN_SET(%s, r.dias)
                """, (user_id, yesterday, day_name))
                c = cur.fetchone()
                completados = 0
                if c:
                    if isinstance(c, dict):
                        completados = c.get('completados', 0) or 0
                    else:
                        try:
                            completados = c[0] or 0
                        except Exception:
                            completados = 0

                # Si no completó todas las tareas ayer, resetear racha
                if total_items > 0 and completados < total_items:
                    cur.execute('UPDATE usuario SET current_streak = 0 WHERE id = %s', (user_id,))
                    conn.commit()
        
    finally:
        conn.close()


def evaluate_daily_streak(user_id):
    """Evalúa y actualiza la racha diaria del usuario."""
    today = date.today()
    dias_semana = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    hoy_spanish = dias_semana[today.strftime('%A')]
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Obtener racha actual
            cur.execute('SELECT current_streak, longest_streak FROM usuario WHERE id = %s', (user_id,))
            existing_streak = cur.fetchone()
            
            current_streak = 0
            longest_streak = 0
            
            if existing_streak:
                if isinstance(existing_streak, dict):
                    current_streak = existing_streak.get('current_streak', 0) or 0
                    longest_streak = existing_streak.get('longest_streak', 0) or 0
                else:
                    try:
                        current_streak, longest_streak = existing_streak
                        current_streak = current_streak or 0
                        longest_streak = longest_streak or 0
                    except Exception:
                        current_streak = 0
                        longest_streak = 0
            
            # ¿Hay rutinas programadas para hoy?
            cur.execute('SELECT COUNT(*) AS cnt FROM rutina WHERE id_usuario = %s AND dias LIKE %s', 
                       (user_id, f'%{hoy_spanish}%'))
            r = cur.fetchone()
            has_rutinas = False
            if r:
                if isinstance(r, dict):
                    has_rutinas = (r.get('cnt', 0) or 0) > 0
                else:
                    try:
                        has_rutinas = (r[0] or 0) > 0
                    except Exception:
                        has_rutinas = False
            
            if not has_rutinas:
                # Sin rutinas hoy = día automáticamente completado
                if current_streak == 0:
                    current_streak = 1
                else:
                    current_streak += 1
            else:
                # Tiene rutinas - verificar completación
                cur.execute("""
                    SELECT COUNT(ri.id_item) AS total
                    FROM rutina r
                    JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                    WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                """, (user_id, hoy_spanish))
                t = cur.fetchone()
                total_items = 0
                if t:
                    if isinstance(t, dict):
                        total_items = t.get('total', 0) or 0
                    else:
                        try:
                            total_items = t[0] or 0
                        except Exception:
                            total_items = 0
                
                # Contar completados hoy
                cur.execute("""
                    SELECT COUNT(DISTINCT id.id_item) AS completados
                    FROM item_diario id
                    JOIN rutina_item ri ON id.id_item = ri.id_item
                    JOIN rutina r ON ri.id_rutina = r.id_rutina
                    WHERE id.id_usuario = %s AND id.fecha = %s AND id.completado = 1
                    AND FIND_IN_SET(%s, r.dias)
                """, (user_id, today, hoy_spanish))
                c = cur.fetchone()
                completados = 0
                if c:
                    if isinstance(c, dict):
                        completados = c.get('completados', 0) or 0
                    else:
                        try:
                            completados = c[0] or 0
                        except Exception:
                            completados = 0
                
                # Evaluar completación del día
                if total_items > 0 and completados >= total_items:
                    # Día completado exitosamente
                    if current_streak == 0:
                        current_streak = 1
                    else:
                        current_streak += 1
                else:
                    # Día no completado - no incrementar racha
                    pass
            
            # Actualizar longest_streak si es necesario
            if current_streak > longest_streak:
                longest_streak = current_streak
            
            # Actualizar la base de datos
            cur.execute('UPDATE usuario SET current_streak = %s, longest_streak = %s WHERE id = %s', 
                      (current_streak, longest_streak, user_id))
            
        conn.commit()
    finally:
        conn.close()


def debug_streak_status(user_id):
    """Función de debug para verificar el estado actual de las rachas."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Obtener estado actual
            cur.execute('SELECT current_streak, longest_streak FROM usuario WHERE id = %s', (user_id,))
            row = cur.fetchone()
            
            if row:
                if isinstance(row, dict):
                    current_streak = row.get('current_streak', 0) or 0
                    longest_streak = row.get('longest_streak', 0) or 0
                else:
                    current_streak, longest_streak = row
                    current_streak = current_streak or 0
                    longest_streak = longest_streak or 0
            else:
                current_streak = 0
                longest_streak = 0
            
            print(f"=== DEBUG RACHA USUARIO {user_id} ===")
            print(f"Hoy: {today}")
            print(f"Ayer: {yesterday}")
            print(f"Racha actual: {current_streak}")
            print(f"Racha más larga: {longest_streak}")
            
            return {
                'user_id': user_id,
                'current_streak': current_streak,
                'longest_streak': longest_streak,
                'today': today,
                'yesterday': yesterday
            }
    finally:
        conn.close()


try:
    ensure_streak_tables()
except Exception:
    pass
