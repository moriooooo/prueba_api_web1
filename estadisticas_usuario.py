"""
Módulo para calcular estadísticas del usuario
"""

from models.db import get_db_connection
import pymysql
from datetime import date, timedelta, datetime
from collections import Counter

def calcular_estadisticas_usuario(user_id):
    """
    Calcula estadísticas completas del usuario:
    - Racha actual y máxima
    - Porcentaje de cumplimiento general
    - Días consecutivos de constancia
    - Tiempo total invertido (estimado)
    - Estadísticas por período
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 1. ESTADÍSTICAS DE RACHAS
        cursor.execute('SELECT current_streak, longest_streak FROM usuario WHERE id = %s', (user_id,))
        usuario_data = cursor.fetchone()
        
        racha_actual = usuario_data.get('current_streak', 0) if usuario_data else 0
        racha_maxima = usuario_data.get('longest_streak', 0) if usuario_data else 0
        
        # 2. ESTADÍSTICAS DE CUMPLIMIENTO (últimos 30 días)
        fecha_inicio = date.today() - timedelta(days=30)
        
        # Obtener días con rutinas programadas
        cursor.execute("""
            SELECT DISTINCT DATE(fecha) as fecha_dia
            FROM (
                SELECT CURDATE() - INTERVAL (a.a + (10 * b.a) + (100 * c.a)) DAY as fecha
                FROM (SELECT 0 AS a UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS a
                CROSS JOIN (SELECT 0 AS a UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS b
                CROSS JOIN (SELECT 0 AS a UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS c
            ) fechas
            WHERE fecha >= %s AND fecha <= CURDATE()
            AND EXISTS (
                SELECT 1 FROM rutina r 
                WHERE r.id_usuario = %s 
                AND FIND_IN_SET(
                    CASE WEEKDAY(fecha)
                        WHEN 0 THEN 'Lunes'
                        WHEN 1 THEN 'Martes' 
                        WHEN 2 THEN 'Miércoles'
                        WHEN 3 THEN 'Jueves'
                        WHEN 4 THEN 'Viernes'
                        WHEN 5 THEN 'Sábado'
                        WHEN 6 THEN 'Domingo'
                    END, 
                    r.dias
                ) > 0
            )
        """, (fecha_inicio, user_id))
        
        dias_programados = cursor.fetchall()
        total_dias_programados = len(dias_programados)
        
        # Obtener días completados
        dias_completados = 0
        if total_dias_programados > 0:
            for dia_info in dias_programados:
                fecha_dia = dia_info['fecha_dia']
                
                # Contar tareas del día
                cursor.execute("""
                    SELECT COUNT(*) as total_tareas
                    FROM rutina r
                    JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                    WHERE r.id_usuario = %s 
                    AND FIND_IN_SET(
                        CASE WEEKDAY(%s)
                            WHEN 0 THEN 'Lunes'
                            WHEN 1 THEN 'Martes'
                            WHEN 2 THEN 'Miércoles' 
                            WHEN 3 THEN 'Jueves'
                            WHEN 4 THEN 'Viernes'
                            WHEN 5 THEN 'Sábado'
                            WHEN 6 THEN 'Domingo'
                        END, 
                        r.dias
                    ) > 0
                """, (user_id, fecha_dia))
                
                total_tareas = cursor.fetchone()['total_tareas']
                
                if total_tareas > 0:
                    # Contar tareas completadas
                    cursor.execute("""
                        SELECT COUNT(*) as completadas
                        FROM item_diario id
                        JOIN rutina_item ri ON id.id_item = ri.id_item
                        JOIN rutina r ON ri.id_rutina = r.id_rutina
                        WHERE id.id_usuario = %s 
                        AND id.fecha = %s 
                        AND id.completado = 1
                        AND FIND_IN_SET(
                            CASE WEEKDAY(%s)
                                WHEN 0 THEN 'Lunes'
                                WHEN 1 THEN 'Martes'
                                WHEN 2 THEN 'Miércoles'
                                WHEN 3 THEN 'Jueves'
                                WHEN 4 THEN 'Viernes'
                                WHEN 5 THEN 'Sábado'
                                WHEN 6 THEN 'Domingo'
                            END,
                            r.dias
                        ) > 0
                    """, (user_id, fecha_dia, fecha_dia))
                    
                    completadas = cursor.fetchone()['completadas']
                    
                    if completadas == total_tareas:
                        dias_completados += 1
        
        # Calcular porcentaje de cumplimiento
        porcentaje_cumplimiento = round((dias_completados / total_dias_programados * 100) if total_dias_programados > 0 else 0)
        
        # 3. TIEMPO TOTAL ESTIMADO (basado en rutinas)
        cursor.execute("""
            SELECT SUM(ri.tiempo) as tiempo_total_minutos
            FROM rutina r
            JOIN rutina_item ri ON r.id_rutina = ri.id_rutina  
            WHERE r.id_usuario = %s AND ri.tiempo IS NOT NULL
        """, (user_id,))
        
        tiempo_result = cursor.fetchone()
        tiempo_por_dia_minutos = tiempo_result['tiempo_total_minutos'] if tiempo_result['tiempo_total_minutos'] else 0
        
        # Estimar tiempo total basado en días completados
        tiempo_total_horas = round((tiempo_por_dia_minutos * dias_completados) / 60, 1) if tiempo_por_dia_minutos > 0 else 0
        
        # 4. ESTADÍSTICAS ADICIONALES
        cursor.execute("""
            SELECT COUNT(DISTINCT fecha) as dias_activos
            FROM item_diario 
            WHERE id_usuario = %s AND completado = 1
            AND fecha >= %s
        """, (user_id, fecha_inicio))
        
        dias_activos = cursor.fetchone()['dias_activos']
        
        # 5. RUTINAS TOTALES
        cursor.execute('SELECT COUNT(*) as total_rutinas FROM rutina WHERE id_usuario = %s', (user_id,))
        total_rutinas = cursor.fetchone()['total_rutinas']
        
        # 6. TAREAS COMPLETADAS TOTAL
        cursor.execute("""
            SELECT COUNT(*) as tareas_completadas_total
            FROM item_diario 
            WHERE id_usuario = %s AND completado = 1
        """, (user_id,))
        
        tareas_completadas_total = cursor.fetchone()['tareas_completadas_total']
        
        conn.close()
        
        return {
            'racha_actual': racha_actual,
            'racha_maxima': racha_maxima,
            'porcentaje_cumplimiento': porcentaje_cumplimiento,
            'tiempo_total_horas': tiempo_total_horas,
            'dias_completados': dias_completados,
            'dias_programados': total_dias_programados,
            'dias_activos': dias_activos,
            'total_rutinas': total_rutinas,
            'tareas_completadas_total': tareas_completadas_total,
            'periodo_dias': 30
        }
        
    except Exception as e:
        print(f"❌ Error calculando estadísticas: {e}")
        return {
            'racha_actual': 0,
            'racha_maxima': 0, 
            'porcentaje_cumplimiento': 0,
            'tiempo_total_horas': 0,
            'dias_completados': 0,
            'dias_programados': 0,
            'dias_activos': 0,
            'total_rutinas': 0,
            'tareas_completadas_total': 0,
            'periodo_dias': 30
        }

def obtener_estadisticas_racha_historica(user_id, dias=90):
    """
    Obtiene el historial de rachas para análisis de tendencias
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        fecha_inicio = date.today() - timedelta(days=dias)
        
        # Obtener historial de actividad diaria
        cursor.execute("""
            SELECT 
                fecha,
                COUNT(*) as tareas_completadas,
                (SELECT COUNT(*) FROM rutina_item ri 
                 JOIN rutina r ON ri.id_rutina = r.id_rutina 
                 WHERE r.id_usuario = %s 
                 AND FIND_IN_SET(
                    CASE WEEKDAY(id.fecha)
                        WHEN 0 THEN 'Lunes'
                        WHEN 1 THEN 'Martes'
                        WHEN 2 THEN 'Miércoles'
                        WHEN 3 THEN 'Jueves' 
                        WHEN 4 THEN 'Viernes'
                        WHEN 5 THEN 'Sábado'
                        WHEN 6 THEN 'Domingo'
                    END,
                    r.dias
                 ) > 0) as tareas_programadas
            FROM item_diario id
            WHERE id.id_usuario = %s 
            AND id.completado = 1
            AND id.fecha >= %s
            GROUP BY fecha
            ORDER BY fecha
        """, (user_id, user_id, fecha_inicio))
        
        historial = cursor.fetchall()
        conn.close()
        
        return historial
        
    except Exception as e:
        print(f"❌ Error obteniendo historial de rachas: {e}")
        return []