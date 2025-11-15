"""
Script de verificación completa del sistema FocusFit
Ejecutar después de la instalación para validar que todo funcione
"""

import sys
import os
import importlib.util

def verificar_dependencias():
    print("🔍 VERIFICANDO DEPENDENCIAS DE PYTHON")
    print("=" * 50)
    
    dependencias = [
        'flask', 'pymysql', 'werkzeug', 'itsdangerous', 'requests'
    ]
    
    faltantes = []
    
    for dep in dependencias:
        try:
            __import__(dep)
            print(f"   ✅ {dep}")
        except ImportError:
            print(f"   ❌ {dep}")
            faltantes.append(dep)
    
    if faltantes:
        print(f"\n⚠️  Dependencias faltantes: {', '.join(faltantes)}")
        print("   Ejecutar: pip install -r requirements.txt")
        return False
    
    print("\n✅ Todas las dependencias están instaladas")
    return True

def verificar_conexion_bd():
    print("\n🗄️  VERIFICANDO CONEXIÓN A BASE DE DATOS")
    print("=" * 50)
    
    try:
        from models.db import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar que la BD existe
        cursor.execute("SELECT DATABASE()")
        bd_actual = cursor.fetchone()[0]
        print(f"   ✅ Conectado a BD: {bd_actual}")
        
        # Verificar tablas principales
        cursor.execute("SHOW TABLES")
        tablas = [tabla[0] for tabla in cursor.fetchall()]
        
    tablas_requeridas = ['usuario', 'rutina', 'rutina_item', 'item_diario', 'user_notifications']
        
        for tabla in tablas_requeridas:
            if tabla in tablas:
                print(f"   ✅ Tabla '{tabla}' existe")
            else:
                print(f"   ❌ Tabla '{tabla}' faltante")
                return False
        
        # Verificar campos agregados en usuario
        cursor.execute("DESCRIBE usuario")
        campos = [campo[0] for campo in cursor.fetchall()]
        
        campos_nuevos = ['last_streak_date', 'racha_base_hoy']
        for campo in campos_nuevos:
            if campo in campos:
                print(f"   ✅ Campo '{campo}' existe en usuario")
            else:
                print(f"   ❌ Campo '{campo}' faltante en usuario")
                print("   💡 Ejecutar: ALTER TABLE usuario ADD COLUMN ...")
                return False
        
        conn.close()
        print("\n✅ Base de datos configurada correctamente")
        return True
        
    except Exception as e:
        print(f"   ❌ Error de conexión: {e}")
        print("   💡 Verificar credenciales en models/db.py")
        return False

def verificar_sistema_rachas():
    print("\n🔥 VERIFICANDO SISTEMA DE RACHAS")
    print("=" * 50)
    
    try:
        from sistema_rachas_mejorado import evaluar_racha_inteligente
        print("   ✅ Módulo de rachas importado correctamente")
        
        # Test básico con usuario inexistente (no debería explotar)
        resultado = evaluar_racha_inteligente(99999)
        print("   ✅ Función de rachas responde correctamente")
        return True
        
    except Exception as e:
        print(f"   ❌ Error en sistema de rachas: {e}")
        return False

def verificar_estadisticas():
    print("\n📊 VERIFICANDO SISTEMA DE ESTADÍSTICAS")
    print("=" * 50)
    
    try:
        from estadisticas_usuario import calcular_estadisticas_usuario
        print("   ✅ Módulo de estadísticas importado correctamente")
        
        # Test básico
        stats = calcular_estadisticas_usuario(99999)
        print("   ✅ Función de estadísticas responde correctamente")
        return True
        
    except Exception as e:
        print(f"   ❌ Error en sistema de estadísticas: {e}")
        return False

def verificar_app_principal():
    print("\n🚀 VERIFICANDO APLICACIÓN PRINCIPAL")
    print("=" * 50)
    
    try:
        import app
        print("   ✅ App principal importada correctamente")
        
        # Verificar que Flask app existe
        if hasattr(app, 'app'):
            print("   ✅ Flask app configurada")
            return True
        else:
            print("   ❌ Flask app no encontrada")
            return False
            
    except Exception as e:
        print(f"   ❌ Error importando app: {e}")
        return False

def main():
    print("🎯 VERIFICACIÓN COMPLETA - FOCUSFIT")
    print("=" * 60)
    
    verificaciones = [
        verificar_dependencias(),
        verificar_conexion_bd(),
        verificar_sistema_rachas(),
        verificar_estadisticas(),
        verificar_app_principal()
    ]
    
    exitosos = sum(verificaciones)
    total = len(verificaciones)
    
    print(f"\n📋 RESUMEN DE VERIFICACIÓN")
    print("=" * 40)
    print(f"   Verificaciones exitosas: {exitosos}/{total}")
    
    if exitosos == total:
        print("   🎉 ¡TODO CONFIGURADO CORRECTAMENTE!")
        print("   🚀 Ejecutar: python app.py")
        print("   🌐 Acceder a: http://127.0.0.1:5000")
    else:
        print("   ⚠️  Hay problemas que resolver antes de continuar")
        print("   📖 Consultar README.md para más información")

if __name__ == "__main__":
    main()