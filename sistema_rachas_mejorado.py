"""
Sistema de rachas DEFINITIVAMENTE CORREGIDO
Versión con manejo robusto de conexiones y lógica simplificada
"""

from models.db import get_db_connection
from datetime import datetime, timedelta, date
import pymysql.cursors

def evaluar_racha_inteligente(user_id):
    """
    Evalúa las rachas de forma inteligente evitando duplicaciones.
    VERSIÓN CORREGIDA - Sin duplicaciones garantizadas
    """
    return _evaluar_racha_interna(user_id, forzar_recalculo=False)

def evaluar_racha_forzar_recalculo(user_id):
    """
    Fuerza el recálculo de racha aunque ya se haya evaluado hoy.
    Para usar cuando se marcan/desmarcan tareas.
    """
    return _evaluar_racha_interna(user_id, forzar_recalculo=True)

def _evaluar_racha_interna(user_id, forzar_recalculo=False):
    """
    Función interna que maneja ambos casos: normal y forzado
    """
    
    hoy = date.today()
    dias_semana = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    dia_actual = dias_semana[hoy.strftime('%A')]
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 1. Obtener estado actual de racha
        cursor.execute('SELECT current_streak, longest_streak, last_streak_date, racha_base_hoy FROM usuario WHERE id = %s', (user_id,))
        usuario_data = cursor.fetchone()
        
        if not usuario_data:
            conn.close()
            return {'racha_actual': 0, 'racha_activa': False, 'dia_completo': False}
        
        racha_actual = usuario_data.get('current_streak', 0) or 0
        racha_maxima = usuario_data.get('longest_streak', 0) or 0
        ultimo_dia_racha = usuario_data.get('last_streak_date')
        racha_base_guardada = usuario_data.get('racha_base_hoy', 0) or 0
        
        print(f"🔍 DEBUG Racha - Usuario {user_id}: Racha={racha_actual}, Último día={ultimo_dia_racha}, Hoy={hoy}")
        
        # 🔥 VERIFICAR SI ÚLTIMO DÍA EVALUADO ESTABA INCOMPLETO
        if ultimo_dia_racha and ultimo_dia_racha != hoy and not forzar_recalculo:
            # Verificar si el último día evaluado estaba completo
            progreso_ultimo_dia = obtener_estado_racha_dia(user_id, ultimo_dia_racha)
            dias_diferencia = (hoy - ultimo_dia_racha).days
            
            print(f"🔍 Verificando último día evaluado ({ultimo_dia_racha}): {progreso_ultimo_dia['completadas']}/{progreso_ultimo_dia['total_tareas']} = {'Completo' if progreso_ultimo_dia['completo'] else 'INCOMPLETO'}")
            
            if not progreso_ultimo_dia['completo']:
                # El último día evaluado estaba incompleto, romper la racha
                cursor.execute('UPDATE usuario SET current_streak = 0, last_streak_date = NULL, racha_base_hoy = 0 WHERE id = %s', (user_id,))
                conn.commit()
                racha_actual = 0
                ultimo_dia_racha = None
                print(f"💥 RACHA ROTA: El último día evaluado estaba incompleto. Reset a 0.")
            elif dias_diferencia > 1:
                # Día completo pero han pasado más de 1 día, romper racha por discontinuidad  
                cursor.execute('UPDATE usuario SET current_streak = 0, last_streak_date = NULL, racha_base_hoy = 0 WHERE id = %s', (user_id,))
                conn.commit()
                racha_actual = 0
                ultimo_dia_racha = None
                print(f"💥 RACHA ROTA: Más de 1 día sin evaluar ({dias_diferencia} días). Reset a 0.")
        
        # ⚠️ CONTROL ANTI-DUPLICACIÓN: Si ya evaluamos hoy Y no es recálculo forzado
        if ultimo_dia_racha == hoy and not forzar_recalculo:
            print(f"✅ Ya evaluado hoy. Racha se mantiene en: {racha_actual}")
            # Solo verificar estado actual sin modificar nada
            progreso_hoy = obtener_estado_racha_dia(user_id, hoy)
            conn.close()
            return {
                'racha_actual': racha_actual,
                'racha_activa': progreso_hoy['completo'],
                'dia_completo': progreso_hoy['completo'],
                'total_tareas': progreso_hoy['total_tareas'],
                'tareas_completadas': progreso_hoy['completadas']
            }
        
        # RECÁLCULO FORZADO - Usar racha base correcta
        if forzar_recalculo and ultimo_dia_racha == hoy:
            print(f"🔄 RECÁLCULO FORZADO - Racha actual: {racha_actual}, Base guardada: {racha_base_guardada}")
            
            # Si la racha actual es 0 (se rompió), NO usar la base guardada
            # Si la racha actual > 0, usar la base guardada
            if racha_actual == 0:
                racha_base_para_reset = 0
                print(f"   Racha rota (0) - usando base = 0")
            else:
                racha_base_para_reset = racha_base_guardada
                print(f"   Racha activa - usando base guardada = {racha_base_guardada}")
            
            # Reset al estado de ayer
            ayer = hoy - timedelta(days=1)
            
            cursor.execute("""
                UPDATE usuario 
                SET current_streak = %s, last_streak_date = %s
                WHERE id = %s
            """, (racha_base_para_reset, ayer, user_id))
            conn.commit()
            
            print(f"   Reset: racha {racha_actual} → {racha_base_para_reset}, fecha → {ayer}")
            
            # Actualizar variables para que siga el flujo normal
            racha_actual = racha_base_para_reset
            ultimo_dia_racha = ayer
        
        # 2. Verificar el progreso del día (tanto para primera vez como recálculo)
        progreso_hoy = obtener_estado_racha_dia(user_id, hoy)
        dia_completo = progreso_hoy['completo']
        tiene_rutinas = progreso_hoy['total_tareas'] > 0
        
        print(f"📊 Progreso hoy: {progreso_hoy['completadas']}/{progreso_hoy['total_tareas']} = {dia_completo}")
        
        # 🔥 NUEVA LÓGICA: Si no hay rutinas programadas, no evaluar racha
        if not tiene_rutinas:
            print(f"📅 Sin rutinas programadas para hoy. Racha no se evalúa (mantiene: {racha_actual})")
            # Marcar que ya se evaluó hoy pero SIN cambiar la racha
            cursor.execute("""
                UPDATE usuario 
                SET last_streak_date = %s, racha_base_hoy = %s
                WHERE id = %s
            """, (hoy, racha_actual, user_id))
            conn.commit()
            
            conn.close()
            return {
                'racha_actual': racha_actual,
                'racha_activa': False,  # No activa porque no hay rutinas
                'dia_completo': False,
                'total_tareas': 0,
                'tareas_completadas': 0,
                'sin_rutinas': True
            }
        
        # 3. Lógica de evaluación (primera vez o después de reset) - SOLO SI HAY RUTINAS
        if True:  # Siempre usar lógica de primera vez ahora
            # PRIMERA VEZ DEL DÍA: Lógica normal + guardar racha base
            # Guardar la racha actual como "base" para futuros recálculos
            racha_base_para_hoy = racha_actual
            
            if dia_completo:
                # Si la racha era 0, empezar en 1; si no, incrementar
                if racha_actual == 0:
                    racha_actual = 1
                else:
                    racha_actual += 1
                
                if racha_actual > racha_maxima:
                    racha_maxima = racha_actual
                
                # Actualizar en BD MARCANDO QUE YA SE EVALUÓ HOY + guardar racha base
                cursor.execute("""
                    UPDATE usuario 
                    SET current_streak = %s, longest_streak = %s, last_streak_date = %s, racha_base_hoy = %s
                    WHERE id = %s
                """, (racha_actual, racha_maxima, hoy, racha_base_para_hoy, user_id))
                conn.commit()
                
                print(f"🎉 Día completo! Racha incrementada a: {racha_actual} (base guardada: {racha_base_para_hoy})")
                racha_activa = True
            else:
                # Día incompleto - MANTENER racha base (sin incluir hoy)
                racha_actual = racha_base_para_hoy
                cursor.execute("""
                    UPDATE usuario 
                    SET current_streak = %s, racha_base_hoy = %s, last_streak_date = %s
                    WHERE id = %s
                """, (racha_actual, racha_base_para_hoy, hoy, user_id))
                conn.commit()
                
                racha_activa = False
                print(f"⏳ Día incompleto. Racha mantenida en: {racha_actual} (base guardada: {racha_base_para_hoy})")
        
        conn.close()
        
        return {
            'racha_actual': racha_actual,
            'racha_activa': racha_activa,
            'dia_completo': dia_completo,
            'total_tareas': progreso_hoy['total_tareas'],
            'tareas_completadas': progreso_hoy['completadas'],
            'tiene_rutinas': progreso_hoy['total_tareas'] > 0
        }
        
    except Exception as e:
        print(f"❌ Error en evaluar_racha_inteligente: {e}")
        conn.close()
        return {'racha_actual': 0, 'racha_activa': False, 'dia_completo': False}

def verificar_racha_perdida(user_id):
    """
    Verifica si se perdió la racha por no completar días anteriores.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        hoy = date.today()
        ayer = hoy - timedelta(days=1)
        
        # Obtener racha actual
        cursor.execute('SELECT current_streak, last_streak_date FROM usuario WHERE id = %s', (user_id,))
        usuario_data = cursor.fetchone()
        
        if not usuario_data:
            conn.close()
            return
        
        racha_actual = usuario_data.get('current_streak', 0) or 0
        ultimo_dia_racha = usuario_data.get('last_streak_date')
        
        # Si no hay racha activa, no hay nada que verificar
        if racha_actual == 0:
            conn.close()
            return
        
        # Si ya evaluamos hoy, no volver a verificar
        if ultimo_dia_racha == hoy:
            conn.close()
            return
        
        # Si la última evaluación no fue ayer NI anteayer, verificar si se rompió la racha
        # Permitir hasta 1 día de diferencia (ayer o anteayer está bien)
        anteayer = ayer - timedelta(days=1)
        
        if ultimo_dia_racha and ultimo_dia_racha < anteayer:
            dias_diferencia = (hoy - ultimo_dia_racha).days
            print(f"🔍 Verificando racha perdida. Último día: {ultimo_dia_racha}, Hoy: {hoy}, Diferencia: {dias_diferencia} días")
            
            if dias_diferencia > 2:  # Más de 2 días sin evaluar = racha perdida
                cursor.execute('UPDATE usuario SET current_streak = 0, last_streak_date = NULL WHERE id = %s', (user_id,))
                conn.commit()
                print(f"💥 Racha perdida por {dias_diferencia} días sin completar. Reseteo a 0.")
            else:
                print(f"✅ Racha mantenida. Solo {dias_diferencia} días de diferencia (aceptable).")
        
        conn.close()
    
    except Exception as e:
        print(f"❌ Error en verificar_racha_perdida: {e}")

def obtener_estado_racha_dia(user_id, fecha=None):
    """
    Obtiene el estado de la racha para una fecha específica.
    """
    if fecha is None:
        fecha = date.today()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        dias_semana = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
        }
        dia_nombre = dias_semana[fecha.strftime('%A')]
        
        # Verificar si hay rutinas para ese día
        cursor.execute("""
            SELECT COUNT(*) as total_tareas
            FROM rutina r
            JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
            WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
        """, (user_id, dia_nombre))
        
        total_tareas = cursor.fetchone()['total_tareas'] or 0
        
        if total_tareas == 0:
            conn.close()
            return {
                'total_tareas': 0,
                'completadas': 0,
                'porcentaje': 0,  # Sin rutinas = 0% (no cuenta para racha)
                'completo': False  # No debe contar para la racha
            }
        
        # Contar completadas
        cursor.execute("""
            SELECT COUNT(*) as completadas
            FROM rutina r
            JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
            JOIN item_diario id ON ri.id_item = id.id_item
            WHERE r.id_usuario = %s 
            AND FIND_IN_SET(%s, r.dias)
            AND id.fecha = %s 
            AND id.completado = 1
            AND id.id_usuario = %s
        """, (user_id, dia_nombre, fecha, user_id))
        
        completadas = cursor.fetchone()['completadas'] or 0
        porcentaje = round((completadas / total_tareas) * 100) if total_tareas > 0 else 0
        
        conn.close()
        
        return {
            'total_tareas': total_tareas,
            'completadas': completadas,
            'porcentaje': porcentaje,
            'completo': completadas >= total_tareas
        }
    
    except Exception as e:
        print(f"❌ Error en obtener_estado_racha_dia: {e}")
        return {'total_tareas': 0, 'completadas': 0, 'porcentaje': 0, 'completo': False}

def debug_racha_sistema(user_id):
    """
    Función de debug para revisar el estado de las rachas
    """
    print(f"\n=== 🔍 DEBUG RACHA SISTEMA - Usuario {user_id} ===")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # Info de BD
        cursor.execute("SELECT current_streak, longest_streak, last_streak_date FROM usuario WHERE id = %s", (user_id,))
        info = cursor.fetchone()
        print(f"🗄️ BD - Current: {info.get('current_streak')}, Longest: {info.get('longest_streak')}, Last date: {info.get('last_streak_date')}")
        
        conn.close()
    except Exception as e:
        print(f"❌ Error en debug BD: {e}")
    
    hoy = date.today()
    print(f"📅 Fecha hoy: {hoy}")
    
    # Estado de hoy
    try:
        estado_hoy = obtener_estado_racha_dia(user_id, hoy)
        print(f"📊 Estado hoy: {estado_hoy}")
        
        # Evaluar racha
        estado_racha = evaluar_racha_inteligente(user_id)
        print(f"🏆 Estado racha: {estado_racha}")
    except Exception as e:
        print(f"❌ Error en evaluación: {e}")
    
    print("=== 🔚 FIN DEBUG ===\n")

def calcular_racha_hasta_fecha(user_id, fecha_limite, cursor):
    """
    Calcula cuál debería ser la racha del usuario hasta una fecha específica (sin incluirla).
    Recorre desde hace tiempo atrás hasta encontrar la racha correcta.
    """
    from datetime import timedelta
    
    dias_semana = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    
    # Empezar desde hace 30 días y contar hacia adelante hasta fecha_limite
    fecha_inicio = fecha_limite - timedelta(days=30)
    fecha_actual = fecha_inicio
    racha_consecutiva = 0
    
    while fecha_actual <= fecha_limite:
        dia_nombre = dias_semana[fecha_actual.strftime('%A')]
        
        # ¿Tenía rutinas este día?
        cursor.execute("""
            SELECT COUNT(*) as total_rutinas
            FROM rutina r
            WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
        """, (user_id, dia_nombre))
        
        tiene_rutinas = (cursor.fetchone()['total_rutinas'] or 0) > 0
        
        if not tiene_rutinas:
            # Sin rutinas = día automáticamente completo
            racha_consecutiva += 1
        else:
            # Con rutinas - verificar si completó todas
            cursor.execute("""
                SELECT COUNT(ri.id_item) as total_items
                FROM rutina r
                JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
            """, (user_id, dia_nombre))
            
            total_items = cursor.fetchone()['total_items'] or 0
            
            cursor.execute("""
                SELECT COUNT(DISTINCT id.id_item) as completados
                FROM rutina r
                JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                LEFT JOIN item_diario id ON ri.id_item = id.id_item 
                WHERE r.id_usuario = %s 
                AND FIND_IN_SET(%s, r.dias)
                AND id.fecha = %s 
                AND id.completado = 1
                AND id.id_usuario = %s
            """, (user_id, dia_nombre, fecha_actual, user_id))
            
            completados = cursor.fetchone()['completados'] or 0
            
            if total_items > 0 and completados >= total_items:
                # Día completo
                racha_consecutiva += 1
            else:
                # Día incompleto - racha se rompe
                racha_consecutiva = 0
        
        fecha_actual += timedelta(days=1)
    
    return racha_consecutiva

def obtener_racha_base_hasta_ayer(user_id, cursor):
    """
    Obtiene cuál debería ser la racha base (sin incluir hoy).
    Busca en la BD el último valor válido antes de hoy.
    """
    from datetime import timedelta
    
    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    
    # La estrategia más simple: si last_streak_date es hoy, 
    # entonces current_streak ya incluye hoy, así que racha_base = current_streak - 1
    cursor.execute('SELECT current_streak, last_streak_date FROM usuario WHERE id = %s', (user_id,))
    data = cursor.fetchone()
    
    if data and data['last_streak_date'] == hoy:
        # La racha actual incluye hoy, así que la base es actual - 1
        return max(0, (data['current_streak'] or 0) - 1)
    else:
        # La racha actual NO incluye hoy, así que es la base
        return data['current_streak'] or 0 if data else 0
    
    # Si no hay info previa, calcular manualmente los últimos días
    # Esto es un fallback - en casos normales no debería llegar aquí
    return calcular_racha_hasta_fecha(user_id, ayer, cursor)