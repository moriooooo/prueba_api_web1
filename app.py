from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from models.db import get_db_connection
from models.user import get_user_by_email, create_user, update_user_password, update_user_email, update_user_name, update_user_avatar, update_user_phone

# importar notificaciones y rachas (copiadas desde el otro proyecto)
try:
    from models.notification import create_notifications_for_routine, get_due_notifications, mark_delivered
    try:
        from models.notification import create_email_reminder_for_routine, get_pending_email_reminders, mark_notification_sent
    except Exception:
        create_email_reminder_for_routine = None
        get_pending_email_reminders = None
        mark_notification_sent = None
except Exception:
    create_notifications_for_routine = None
    get_due_notifications = None
    mark_delivered = None

try:
    from models.streak import mark_task_completed, get_global_streak, evaluate_daily_streak, check_and_reset_missed_streaks, debug_streak_status
except Exception:
    mark_task_completed = None
    get_global_streak = None
    evaluate_daily_streak = None
    check_and_reset_missed_streaks = None
    debug_streak_status = None

# Importar sistema de rachas mejorado
try:
    from sistema_rachas_mejorado import evaluar_racha_inteligente, evaluar_racha_forzar_recalculo, verificar_racha_perdida, obtener_estado_racha_dia
except ImportError:
    # Si no existe el archivo, crear funciones dummy
    def evaluar_racha_inteligente(usuario_id):
        return {'dias_consecutivos': 0, 'racha_activa': False, 'ultimo_dia_evaluado': None}
    
    def verificar_racha_perdida(usuario_id):
        pass
    
    def obtener_estado_racha_dia(usuario_id):
        return False

import os
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import smtplib
from email.message import EmailMessage
import pymysql
import re
from itsdangerous import URLSafeTimedSerializer
from flask import current_app
from datetime import datetime, timedelta
from flask import jsonify
import uuid
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv no está instalada o no se puede cargar: continuar sin ella
    load_dotenv = None

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
except Exception:
    SendGridAPIClient = None
    Mail = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR,'templates')
STATIC_DIR = os.path.join(BASE_DIR,'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = 'clave_secreta_segura'  
app.config['MAIL_FROM'] = os.environ.get('MAIL_FROM', 'no-reply@example.com')
app.config['MAIL_HOST'] = os.environ.get('MAIL_HOST', '')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 0)) if os.environ.get('MAIL_PORT') else None
app.config['MAIL_USER'] = os.environ.get('MAIL_USER', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_USE_CONSOLE'] = os.environ.get('MAIL_USE_CONSOLE', '1') == '1'
app.config['UPLOAD_FOLDER'] = os.path.join(STATIC_DIR, 'img', 'avatars')  # Carpeta para subir avatares (servida desde static)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Admin blueprint removed: admin_dashboard.py was deleted per user request.
# Register admin blueprint from admin_app so admin panel is available on the same port
try:
    from admin_app import admin_bp
    app.register_blueprint(admin_bp)
except Exception as e:
    print('No se pudo registrar admin blueprint from admin_app:', e)

# Inicializar base de datos desde SQL (si existe) - solo en development
try:
    from models.db import init_db_from_file
    sql_path = os.path.join(BASE_DIR, 'focusfit_completo.sql')
    init_db_from_file(sql_path)
    print('DB inicializada (si hacía falta)')
except Exception as e:
    print('No se pudo inicializar DB automáticamente:', e)


# Extensiones permitidas para avatars
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    if not filename:
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def list_admin_content_app(content_type='rutina_destacada', limit=10):
    """Load content added via the admin panel (contenido_admin table).
    Returns a list of dict rows (may be empty)."""
    items = []
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                'SELECT * FROM contenido_admin WHERE tipo_contenido = %s ORDER BY actualizado_en DESC LIMIT %s',
                (content_type, limit)
            )
            items = cur.fetchall() or []
        conn.close()
    except Exception as e:
        print('list_admin_content_app error:', e)
    return items


@app.context_processor
def inject_user_notifications():
    """Inyecta el conteo de notificaciones no leídas del usuario para la UI"""
    unread = 0
    try:
        user_id = session.get('usuario_id')
        if user_id:
            conn = get_db_connection()
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute('SELECT COUNT(*) AS total FROM user_notifications WHERE user_id = %s AND is_read = 0', (user_id,))
                row = cur.fetchone()
                unread = int(row.get('total', 0)) if row else 0
            conn.close()
    except Exception:
        unread = 0
    return dict(user_unread_notifications=unread)


@app.route('/notifications')
def user_notifications_page():
    """Página de notificaciones del usuario. Usa el partial notifications.html para mostrar los toasts y también lista de notificaciones."""
    # Obtener últimas notificaciones (limitadas)
    notes = []
    try:
        user_id = session.get('usuario_id')
        if not user_id:
            flash('Debes iniciar sesión para ver las notificaciones', 'warning')
            return redirect(url_for('login'))
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT id, title, message, fecha_programada, is_read FROM user_notifications WHERE user_id = %s ORDER BY fecha_programada DESC LIMIT 200', (user_id,))
            notes = cur.fetchall() or []
        conn.close()
    except Exception as e:
        print('user_notifications_page error', e)
    return render_template('notifications_list.html', notifications=notes)

@app.route('/')
def inicio():
    # --- Verificar sesión ---
    if 'user_email' not in session:
        # Redirigir al login si no hay usuario logueado
        return redirect(url_for('login'))  # Asegúrate que tu ruta login se llama 'login'

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    # --- SISTEMA MALO DESACTIVADO (línea 109) ---
    # evaluate_daily_streak causa duplicación de rachas - DESACTIVADO
    # try:
    #     if evaluate_daily_streak is not None:
    #         evaluate_daily_streak(usuario['id'])
    # except Exception:
    #     pass

    # --- Días de la semana ---
    dias_semana = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    dia_actual = dias_semana[datetime.today().strftime('%A')]
    hoy = datetime.today().date()

    # --- Inicializar variables ---
    rutinas = []
    lista_diaria = []
    estadisticas = {'rachas': 0, 'cumplimiento_porcentaje': 0}
    progreso_semanal = []
    racha_activa = False

    try:
        # ✅ Sistema de rachas mejorado
        try:
            # Verificar rachas perdidas de días anteriores
            verificar_racha_perdida(usuario['id'])
            # Evaluar estado de racha actual
            estado_racha = evaluar_racha_inteligente(usuario['id'])
        except Exception as e:
            print(f"Error en sistema de rachas: {e}")
            estado_racha = {'racha_actual': 0, 'racha_activa': False, 'dia_completo': False}
            
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Rutinas del usuario
            cur.execute('SELECT id_rutina AS id, nombre, "" AS descripcion FROM rutina WHERE id_usuario = %s LIMIT 5', (usuario['id'],))
            rutinas = cur.fetchall()

            # Lista diaria
            cur.execute("""
                SELECT ri.id_item AS id, r.nombre AS titulo, ri.nombre_item, ri.tiempo, ri.series, ri.repeticiones, 
                       COALESCE(id.completado, FALSE) AS completado, r.horario
                FROM rutina r
                JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                ORDER BY r.horario ASC
            """, (hoy, usuario['id'], usuario['id'], dia_actual))
            lista_diaria = cur.fetchall()

            # Progreso semanal
            dias_orden = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            progreso_semanal = []

            for dia in dias_orden:
                hoy_dt = datetime.today()
                dias_desde_lunes = hoy_dt.weekday()  # 0=Lunes
                indice_dia = dias_orden.index(dia)
                fecha_dia = (hoy_dt - timedelta(days=dias_desde_lunes - indice_dia)).date()

                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM rutina r
                    JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                    WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                """, (usuario['id'], dia))
                total = cur.fetchone()['total'] or 0

                if total == 0:
                    porcentaje = 0
                else:
                    cur.execute("""
                        SELECT COUNT(*) AS completados
                        FROM rutina r
                        JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                        LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                        WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias) AND COALESCE(id.completado, FALSE) = 1
                    """, (fecha_dia, usuario['id'], usuario['id'], dia))
                    completados = cur.fetchone()['completados'] or 0
                    porcentaje = round((completados / total) * 100)

                progreso_semanal.append({'dia': dia[:3], 'porcentaje': porcentaje})

            # Estadísticas y racha usando el nuevo sistema
            cumplimiento_pct = progreso_semanal[dias_orden.index(dia_actual)]['porcentaje']
            
            estadisticas = {
                'rachas': estado_racha['racha_actual'],
                'cumplimiento_porcentaje': cumplimiento_pct
            }
            racha_activa = estado_racha['racha_activa']

        conn.close()
    except Exception as e:
        print("Error en inicio:", e)
        # Datos de respaldo
        rutinas = [{'id': 1, 'nombre': 'Rutina A', 'descripcion': ''}]
        lista_diaria = [{'id': 1, 'titulo': 'Correr', 'horario': '07:00', 'completado': False}]
        estadisticas = {'rachas': 2, 'cumplimiento_porcentaje': 65}
        progreso_semanal = [
            {'dia': 'Lun', 'porcentaje': 50}, {'dia': 'Mar', 'porcentaje': 60},
            {'dia': 'Mie', 'porcentaje': 80}, {'dia': 'Jue', 'porcentaje': 40},
            {'dia': 'Vie', 'porcentaje': 90}, {'dia': 'Sab', 'porcentaje': 70},
            {'dia': 'Dom', 'porcentaje': 20},
        ]
        racha_activa = True

    # Load approved user community posts to show on inicio
    community_posts = []
    try:
        conn2 = get_db_connection()
        with conn2.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT cp.id, cp.user_id, u.nombre as user_name, cp.rutina_id, cp.title, cp.summary, cp.image, cp.is_recommendation, cp.created_at, cp.dias FROM community_posts cp LEFT JOIN usuario u ON cp.user_id = u.id WHERE cp.approved = 1 ORDER BY cp.created_at DESC LIMIT 10')
            community_posts = cur.fetchall() or []
        conn2.close()
    except Exception:
        community_posts = []

    return render_template(
        'inicio.html',
        usuario=usuario,
        rutinas=rutinas,
        lista_diaria=lista_diaria,
        estadisticas=estadisticas,
        progreso_semanal=progreso_semanal,
        dia_actual=dia_actual,
        racha_activa=racha_activa,
        admin_banners=list_admin_content_app('banner', limit=5),
        admin_featured=list_admin_content_app('rutina_destacada', limit=5),
        admin_recommendations=list_admin_content_app('recommendation', limit=5),
        admin_community_posts=list_admin_content_app('community', limit=5),
        community_posts=community_posts
    )




@app.route('/crear_rutina', methods=['GET', 'POST'])
def crear_rutina():
    if 'user_email' not in session:
        flash('Debes iniciar sesión para crear rutinas', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    
    id_usuario = usuario['id']

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        tipo = request.form.get('tipo')
        duracion_horas = request.form.get('duracion_horas', type=int) or 0
        duracion_minutos = request.form.get('duracion_minutos', type=int) or 0
        dias_list = request.form.getlist('diasSeleccionados')
        dias = ','.join(dias_list)
        horario = request.form.get('horario')

        
        duracion_total_min = duracion_horas * 60 + duracion_minutos

       
        nombres = request.form.getlist('item_nombre[]')
        prioridades = request.form.getlist('item_prioridad[]')
        tiempos = request.form.getlist('item_tiempo[]') 

        if not nombres:
            flash('Debes agregar al menos un item a la rutina', 'danger')
            return redirect(url_for('crear_rutina'))

        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                
                cur.execute("""
                    INSERT INTO rutina (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_usuario)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_usuario))
                id_rutina = cur.lastrowid

              
                if tipo == 'ejercicio':
                    series = request.form.getlist('item_series[]')
                    repeticiones = request.form.getlist('item_repeticiones[]')
                    for n, s, r in zip(nombres, series, repeticiones):
                        s_val = int(s) if s else None
                        r_val = int(r) if r else None
                        cur.execute("""
                            INSERT INTO rutina_item (id_rutina, nombre_item, series, repeticiones)
                            VALUES (%s, %s, %s, %s)
                        """, (id_rutina, n, s_val, r_val))
                else:  
                    num_items = len(nombres)

                   
                    if num_items > 1 and all(not t for t in tiempos):
                        tiempo_por_item = duracion_total_min // num_items
                        tiempos = [str(tiempo_por_item)] * num_items
                    elif num_items == 1:
                        tiempos = [str(duracion_total_min)] 

                    for n, t, p in zip(nombres, tiempos, prioridades):
                        t_val = int(t) if t else None
                        p_val = p if p else None
                        cur.execute("""
                            INSERT INTO rutina_item (id_rutina, nombre_item, tiempo, prioridad)
                            VALUES (%s, %s, %s, %s)
                        """, (id_rutina, n, t_val, p_val))

            conn.commit()
            conn.close()

            # Si el usuario pidió publicar en comunidad, guardar un post en community_posts
            try:
                if request.form.get('publish_community'):
                    # guardar imagen si hay
                    image_file = None
                    if 'community_image' in request.files:
                        f = request.files.get('community_image')
                        if f and f.filename and allowed_file(f.filename):
                            # Crear nombre único para evitar conflictos
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            filename = secure_filename(f.filename)
                            name_part, ext = os.path.splitext(filename)
                            unique_filename = f"routine_{timestamp}_{name_part}{ext}"
                            
                            target_dir = os.path.join(STATIC_DIR, 'img', 'community')
                            os.makedirs(target_dir, exist_ok=True)
                            f.save(os.path.join(target_dir, unique_filename))
                            image_file = unique_filename

                    summary = request.form.get('community_summary')
                    visibility = request.form.get('community_visibility')
                    conn2 = get_db_connection()
                    with conn2.cursor() as cur:
                        # Publicar directamente como aprobado (approved=1)
                        cur.execute('''
                            INSERT INTO community_posts (user_id, rutina_id, title, summary, image, is_recommendation, approved, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ''', (id_usuario, id_rutina, nombre, summary, image_file, 1 if visibility == '1' else 0, 1))  # ✅ approved = 1
                        
                        # Si también es recomendación, insertarla en la tabla recommendations
                        if visibility == '1':
                            cur.execute('''
                                INSERT INTO recommendations (title, summary, body, difficulty, tipo, duration_minutes, image, is_public, created_by, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            ''', (nombre, summary, f'Rutina compartida por {usuario["nombre"]}', 'medio', tipo, duracion_total_min, image_file, 1, usuario['correo']))
                    conn2.commit()
                    conn2.close()
                    
                    if visibility == '1':
                        flash('Rutina creada y publicada como recomendación en la comunidad', 'success')
                    else:
                        flash('Rutina creada y publicada en la comunidad', 'success')
            except Exception as e:
                print('Error al publicar en comunidad:', e)

            # 🔄 RE-EVALUAR racha tras crear rutina (puede cambiar estado del día)
            try:
                evaluar_racha_forzar_recalculo(id_usuario)
                print(f"✅ Racha recalculada tras crear rutina para usuario {id_usuario}")
            except Exception as e:
                print(f"⚠️ Error al recalcular racha tras crear rutina: {e}")

            # Crear notificaciones programadas para esta rutina (si la función está disponible)
            try:
                if create_notifications_for_routine is not None:
                    # usar id_usuario (propietario) y id_rutina
                    create_notifications_for_routine(id_usuario, id_rutina, nombre, horario)
                # Crear recordatorio único por email (si está disponible)
                if create_email_reminder_for_routine is not None:
                    create_email_reminder_for_routine(id_usuario, id_rutina, nombre, horario, minutes_before=30)
            except Exception:
                pass
            flash('Rutina creada exitosamente', 'success')
            
            # 🔄 Redirigir según de dónde vino el usuario
            from_page = request.form.get('from', 'inicio')
            if from_page == 'planificador':
                return redirect(url_for('planificador'))
            else:
                return redirect(url_for('inicio'))

        except Exception as e:
            flash(f'Error al crear rutina: {e}', 'danger')
            return redirect(url_for('crear_rutina'))

    # 🔄 Detectar de dónde viene el usuario para navegación correcta
    from_page = request.args.get('from', 'inicio')
    return render_template('crear_rutina.html', usuario=usuario, from_page=from_page)


@app.route('/recommendations')
def recommendations_list():
    # public list of recommendations
    items = []
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT id, title, summary, difficulty, duration_minutes, image, tipo, created_at FROM recommendations WHERE is_public = 1 ORDER BY created_at DESC')
            items = cur.fetchall() or []
            
            # Generar tokens seguros para cada recomendación
            import hashlib
            for item in items:
                if item and item.get('id'):
                    secure_token = hashlib.md5(f"focusfit_rec_{item['id']}_{item['tipo']}_{item['created_at']}".encode()).hexdigest()[:16]
                    item['secure_token'] = secure_token
                    
        conn.close()
    except Exception as e:
        print('recommendations_list error', e)
    return render_template('recommendations.html', recommendations=items)


@app.route('/community/rutina/<int:post_id>')
@app.route('/community/rutina/<int:post_id>/<token>')
def community_rutina_details(post_id, token=None):
    """Ver detalles completos de una rutina publicada en la comunidad"""
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Obtener información del post y rutina
            cur.execute('''
                SELECT cp.id, cp.user_id, u.nombre as user_name, cp.rutina_id, 
                       cp.title, cp.summary, cp.image, cp.is_recommendation, cp.created_at,
                       r.nombre as rutina_nombre, r.tipo as rutina_tipo, 
                       r.duracion_horas, r.duracion_minutos, r.dias as rutina_dias, r.horario
                FROM community_posts cp 
                LEFT JOIN usuario u ON cp.user_id = u.id 
                LEFT JOIN rutina r ON cp.rutina_id = r.id_rutina
                WHERE cp.id = %s AND cp.approved = 1
            ''', (post_id,))
            post = cur.fetchone()
            
            if not post:
                flash('Rutina no encontrada', 'danger')
                return redirect(url_for('community_public'))
            
            # Verificación de seguridad adicional
            current_user_id = session.get('usuario_id')
            
            # Generar token esperado basado en el post
            import hashlib
            expected_token = hashlib.md5(f"focusfit_secure_{post_id}_{post['user_id']}_{post['created_at']}".encode()).hexdigest()[:16]
            
            # Si se proporciona token, verificarlo
            if token:
                if token != expected_token:
                    print(f"⚠️ SECURITY: Invalid token attempt for post {post_id} by user {current_user_id}")
                    flash('Acceso no autorizado', 'danger')
                    return redirect(url_for('community_public'))
            else:
                # Sin token, solo permitir si es público Y aprobado, o si es el dueño
                if not (post['approved'] == 1 or (current_user_id and current_user_id == post['user_id'])):
                    print(f"⚠️ SECURITY: Unauthorized access attempt to post {post_id} by user {current_user_id}")
                    flash('No tienes permisos para ver esta rutina', 'danger')
                    return redirect(url_for('community_public'))
            
            # Log de acceso para auditoría
            print(f"✅ ACCESS: User {current_user_id} accessed post {post_id} (token: {'yes' if token else 'no'})")
            
            # Obtener items de la rutina si existe
            items = []
            if post['rutina_id']:
                cur.execute('''
                    SELECT nombre_item, series, repeticiones, tiempo, prioridad
                    FROM rutina_item 
                    WHERE id_rutina = %s 
                    ORDER BY 
                        CASE prioridad 
                            WHEN 'alta' THEN 1 
                            WHEN 'media' THEN 2 
                            WHEN 'baja' THEN 3 
                        END
                ''', (post['rutina_id'],))
                items = cur.fetchall() or []
        
        conn.close()
        
        # Generar token seguro para enlaces
        secure_token = expected_token
        
        return render_template('community_rutina_details.html', 
                             post=post, 
                             items=items, 
                             secure_token=secure_token)
        
    except Exception as e:
        print(f'community_rutina_details error: {e}')
        flash('Error al cargar los detalles de la rutina', 'danger')
        return redirect(url_for('community_public'))


@app.route('/community')
def community_public():
    """Public community page showing admin-managed community posts."""
    posts = []
    try:
        posts = list_admin_content_app('community', limit=50) or []
        # load user-submitted community posts with routine details
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('''
                SELECT cp.id, cp.user_id, u.nombre as user_name, cp.rutina_id, 
                       cp.title, cp.summary, cp.image, cp.is_recommendation, cp.created_at,
                       r.nombre as rutina_nombre, r.tipo as rutina_tipo, 
                       r.duracion_horas, r.duracion_minutos, r.dias as rutina_dias
                FROM community_posts cp 
                LEFT JOIN usuario u ON cp.user_id = u.id 
                LEFT JOIN rutina r ON cp.rutina_id = r.id_rutina
                WHERE cp.approved = 1 
                ORDER BY cp.created_at DESC LIMIT 100
            ''')
            user_posts = cur.fetchall() or []
            
            # Generar tokens seguros para cada post
            import hashlib
            for post in user_posts:
                if post and post.get('id'):
                    secure_token = hashlib.md5(f"focusfit_secure_{post['id']}_{post['user_id']}_{post['created_at']}".encode()).hexdigest()[:16]
                    post['secure_token'] = secure_token
                    
        conn.close()
        # normalize combined list: admin content first then user posts
        posts = posts + user_posts
    except Exception as e:
        print('community_public error', e)
        posts = []
    return render_template('community.html', posts=posts)


@app.route('/community/post', methods=['POST'])
def community_post():
    if 'user_email' not in session:
        flash('Debes iniciar sesión para publicar en la comunidad', 'warning')
        return redirect(url_for('login'))
    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    title = request.form.get('title') or f'Rutina de {usuario["nombre"]}'
    summary = request.form.get('summary')
    dias_list = request.form.getlist('diasSeleccionados') or []
    # support 'Todos' option
    if 'Todos' in dias_list:
        dias_list = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    dias = ','.join(dias_list) if dias_list else None
    make_reco = request.form.get('is_recommendation') == '1'
    
    # Mejorar manejo de imágenes
    image_name = None
    try:
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                # Crear nombre único para evitar conflictos
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                image_name = f"community_{timestamp}_{name}{ext}"
                
                # Asegurar que existe la carpeta community
                community_dir = os.path.join(STATIC_DIR, 'img', 'community')
                os.makedirs(community_dir, exist_ok=True)
                
                # Guardar archivo
                file_path = os.path.join(community_dir, image_name)
                file.save(file_path)
                print(f'✅ Imagen guardada: {file_path}')

        # optionally create a rutina for the user if dias provided
        rutina_id = None
        if dias:
            conn = get_db_connection()
            with conn.cursor() as cur:
                # Use neutral tipo 'compartida' for community-created rutinas (requires enum migration)
                cur.execute('INSERT INTO rutina (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_usuario) VALUES (%s, %s, %s, %s, %s, %s, %s)', (
                    title, 'compartida', 0, 0, dias, None, usuario['id']
                ))
                rutina_id = cur.lastrowid
            conn.commit()
            if conn:
                conn.close()

        # insert into community_posts
        conn2 = get_db_connection()
        with conn2.cursor() as cur:
            cur.execute('INSERT INTO community_posts (user_id, rutina_id, title, summary, image, is_recommendation, approved, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())', (
                usuario['id'], rutina_id, title, summary, image_name, 1 if make_reco else 0, 1
            ))
        conn2.commit()
        conn2.close()
        flash('Publicación enviada a la comunidad', 'success')
    except Exception as e:
        print('community_post error', e)
        flash('Error al publicar en la comunidad', 'danger')

    return redirect(url_for('community_public'))


@app.route('/community/delete/<int:post_id>', methods=['POST'])
def community_delete(post_id):
    if 'user_email' not in session:
        flash('Debes iniciar sesión para eliminar publicaciones', 'warning')
        return redirect(url_for('login'))
    
    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Verificar si el post existe y obtener información
            cur.execute('SELECT user_id, title FROM community_posts WHERE id = %s', (post_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                flash('La publicación no existe o ya fue eliminada', 'warning')
                return redirect(url_for('community_public'))
            
            owner_id = row.get('user_id')
            post_title = row.get('title', 'publicación')
            
            # Verificar permisos (propietario o admin)
            is_admin = session.get('user_email') in (os.environ.get('ADMIN_EMAIL', ''), )
            if owner_id != usuario['id'] and not is_admin:
                conn.close()
                flash('No tienes permisos para eliminar esta publicación', 'danger')
                return redirect(url_for('community_public'))

            # Eliminar la publicación
            cur.execute('DELETE FROM community_posts WHERE id = %s', (post_id,))
            
        conn.commit()
        conn.close()
        
        # Mensaje de éxito
        flash(f'✅ La publicación "{post_title}" ha sido eliminada exitosamente', 'success')
        return redirect(url_for('community_public'))
        
    except Exception as e:
        print(f'❌ Error al eliminar publicación {post_id}:', e)
        flash('⚠️ Ocurrió un error al eliminar la publicación. Inténtalo de nuevo', 'danger')
        return redirect(url_for('community_public'))


@app.route('/community/save/<int:post_id>', methods=['POST'])
def community_save(post_id):
    # Save a community post into the current user's rutinas with selected days
    if 'user_email' not in session:
        flash('Debes iniciar sesión para guardar una publicación', 'warning')
        return redirect(url_for('login'))
    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    # Obtener datos del formulario
    dias_list = request.form.getlist('diasSeleccionados') or []
    
    # Si seleccionaron "Todos", reemplazar por todos los días
    if 'Todos' in dias_list:
        dias_list = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    
    dias = ','.join(dias_list) if dias_list else None
    
    # Obtener duración de horas y minutos por separado
    duracion_horas = request.form.get('duracion_horas', type=int) or 0
    duracion_minutos = request.form.get('duracion_minutos', type=int) or 0
    
    # Si viene el campo legacy duration_minutes, usarlo para compatibilidad
    if 'duration_minutes' in request.form and not duracion_horas and not duracion_minutos:
        total_minutes = request.form.get('duration_minutes', type=int) or 30
        duracion_horas = total_minutes // 60
        duracion_minutos = total_minutes % 60
    
    # Asegurar que hay al menos algo de duración
    if duracion_horas == 0 and duracion_minutos == 0:
        duracion_minutos = 30

    print(f'🔍 DEBUG community_save: post_id={post_id}, user_id={usuario["id"]}, dias_list={dias_list}, duracion={duracion_horas}h {duracion_minutos}m')

    def is_ajax(req):
        # Flask 2 removed is_xhr; detect common AJAX headers or JSON accept
        return req.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in req.accept_mimetypes

    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Load post from user-submitted community_posts (must be approved)
            cur.execute('SELECT id, title, summary, rutina_id FROM community_posts WHERE id = %s AND approved = 1', (post_id,))
            post = cur.fetchone()
            if not post:
                conn.close()
                msg = 'Publicación no encontrada o no aprobada'
                print(f'❌ community_save: {msg} - post_id={post_id}')
                flash(msg, 'danger')
                return redirect(url_for('community_public'))

            print(f'✅ DEBUG: Post encontrado: {post}')

            # Validar que se seleccionó al menos un día
            if not dias:
                msg = 'Debes seleccionar al menos un día para guardar la rutina'
                print(f'❌ community_save: {msg}')
                flash(msg, 'warning')
                return redirect(request.referrer or url_for('community_public'))

            # Crear rutina para el usuario
            titulo_rutina = post.get('title') or post.get('summary') or 'Rutina compartida'
            
            # Obtener horario original de la rutina si existe
            horario_original = None
            origin_rutina_id = post.get('rutina_id')
            if origin_rutina_id:
                cur.execute('SELECT horario FROM rutina WHERE id_rutina = %s', (origin_rutina_id,))
                rutina_original = cur.fetchone()
                if rutina_original:
                    horario_original = rutina_original.get('horario')
                    print(f'🕐 DEBUG: Horario original encontrado: {horario_original}')
            
            cur.execute('''
                INSERT INTO rutina (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_usuario, fecha_creacion) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ''', (titulo_rutina, 'compartida', duracion_horas, duracion_minutos, dias, horario_original, usuario['id']))
            new_rutina_id = cur.lastrowid
            print(f'✅ DEBUG: Nueva rutina creada con ID: {new_rutina_id}, horario: {horario_original}')

            # Si el post tiene una rutina original, copiar sus items
            origin_rutina_id = post.get('rutina_id')
            if origin_rutina_id:
                print(f'🔄 DEBUG: Copiando items de rutina original {origin_rutina_id}')
                cur.execute('SELECT nombre_item, series, repeticiones, tiempo, prioridad FROM rutina_item WHERE id_rutina = %s', (origin_rutina_id,))
                origin_items = cur.fetchall() or []
                for oi in origin_items:
                    cur.execute('''
                        INSERT INTO rutina_item (id_rutina, nombre_item, series, repeticiones, tiempo, prioridad) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    ''', (
                        new_rutina_id, 
                        oi.get('nombre_item') or 'Ejercicio',
                        oi.get('series'), 
                        oi.get('repeticiones'), 
                        oi.get('tiempo'), 
                        oi.get('prioridad') or 'media'
                    ))
                print(f'✅ DEBUG: {len(origin_items)} items copiados')
            else:
                # Crear un item genérico basado en el resumen
                print('📝 DEBUG: Creando item genérico')
                item_nombre = post.get('summary') or post.get('title') or 'Actividad'
                # Convertir a minutos totales para el item
                total_minutos_item = (duracion_horas * 60) + duracion_minutos
                cur.execute('''
                    INSERT INTO rutina_item (id_rutina, nombre_item, tiempo, prioridad) 
                    VALUES (%s, %s, %s, %s)
                ''', (new_rutina_id, item_nombre, total_minutos_item, 'media'))

        conn.commit()
        conn.close()
        
        msg = f'Rutina guardada exitosamente'
        print(f'✅ community_save: success - post_id={post_id}, user_id={usuario["id"]}, new_rutina_id={new_rutina_id}')
        
        flash(msg, 'success')
        return redirect(url_for('mis_rutinas'))
        
    except Exception as e:
        print(f'❌ community_save error: {e}')
        import traceback
        traceback.print_exc()
        flash('Error al guardar la rutina', 'danger')
        return redirect(url_for('community_public'))


@app.route('/recommendations/<int:rid>/save', methods=['POST'])
def save_recommendation(rid):
    if 'user_email' not in session:
        flash('Debes iniciar sesión para guardar recomendaciones', 'warning')
        return redirect(url_for('login'))
    
    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    
    try:
        # Verificación de token de seguridad
        provided_token = request.form.get('secure_token')
        if provided_token:
            conn = get_db_connection()
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute('SELECT tipo, created_at FROM recommendations WHERE id = %s', (rid,))
                rec_data = cur.fetchone()
                if rec_data:
                    import hashlib
                    expected_token = hashlib.md5(f"focusfit_rec_{rid}_{rec_data['tipo']}_{rec_data['created_at']}".encode()).hexdigest()[:16]
                    if provided_token != expected_token:
                        print(f"⚠️ SECURITY: Invalid token in save_recommendation for rec {rid} by user {usuario['id']}")
                        flash('Token de seguridad inválido', 'danger')
                        return redirect(url_for('recommendations_list'))
            conn.close()
        
        # recoger días seleccionados (multi-select)
        dias_list = request.form.getlist('diasSeleccionados') or []
        if 'Todos' in dias_list:
            dias_list = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
        dias = ','.join(dias_list) if dias_list else None
        
        # Validar que se seleccionó al menos un día
        if not dias:
            flash('Debes seleccionar al menos un día para guardar la recomendación', 'warning')
            return redirect(request.referrer or url_for('recommendations_list'))
        
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Load recommendation basic info first
            cur.execute('SELECT title, summary, tipo, duration_minutes FROM recommendations WHERE id = %s', (rid,))
            rec = cur.fetchone()
            print(f'🔍 DEBUG save_recommendation: rec data = {rec}')
            
            if not rec:
                conn.close()
                flash('Recomendación no encontrada', 'danger')
                return redirect(url_for('recommendations_list'))
            
            # Save the user_recommendation link
            cur.execute('INSERT IGNORE INTO user_recommendations (user_id, recommendation_id) VALUES (%s, %s)', (usuario['id'], rid))

            # Create a personal rutina based on the recommendation
            nombre = rec['title'] if rec['title'] else f'Recomendación {rid}'
            tipo = rec['tipo'] if rec['tipo'] else 'ejercicio'
            duration_minutes = rec['duration_minutes'] if rec['duration_minutes'] is not None and rec['duration_minutes'] > 0 else 30
            
            # Convertir minutos totales a horas y minutos
            duracion_horas = duration_minutes // 60
            duracion_minutos = duration_minutes % 60
            
            print(f'✅ DEBUG: Creating rutina - nombre={nombre}, tipo={tipo}, duracion={duracion_horas}h {duracion_minutos}m, dias={dias}')

            # insert rutina for this user
            cur.execute('INSERT INTO rutina (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_usuario) VALUES (%s, %s, %s, %s, %s, %s, %s)', (
                nombre, tipo, duracion_horas, duracion_minutos, dias, None, usuario['id']
            ))
            new_rutina_id = cur.lastrowid
            print(f'✅ DEBUG: Nueva rutina creada con ID: {new_rutina_id}')
            
            # create a single rutina_item summarizing the recommendation
            item_name = rec['summary'] if rec['summary'] else nombre
            cur.execute('INSERT INTO rutina_item (id_rutina, nombre_item, tiempo) VALUES (%s, %s, %s)', 
                       (new_rutina_id, item_name, duration_minutes))
            print(f'✅ DEBUG: Item creado para rutina {new_rutina_id}')

        conn.commit()
        conn.close()
        print(f'✅ save_recommendation: success - rid={rid}, user_id={usuario["id"]}, new_rutina_id={new_rutina_id}')

        flash('Rutina guardada exitosamente', 'success')
        return redirect(url_for('mis_rutinas'))

    except Exception as e:
        print(f'❌ save_recommendation error: {e}')
        import traceback
        traceback.print_exc()
        flash('Error al guardar la recomendación', 'danger')
        return redirect(url_for('recommendations_list'))


@app.route('/recommendations/<int:rec_id>')
@app.route('/recommendations/<int:rec_id>/<token>')
def recommendation_details(rec_id, token=None):
    # Show detailed view of a specific recommendation
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Get recommendation details
            cur.execute('''
                SELECT id, title, summary, body, tipo, difficulty, duration_minutes, image, created_at
                FROM recommendations WHERE id = %s
            ''', (rec_id,))
            recommendation = cur.fetchone()
            
            if not recommendation:
                conn.close()
                flash('Recomendación no encontrada', 'danger')
                return redirect(url_for('recommendations_list'))
            
            # Verificación de seguridad adicional
            current_user_id = session.get('usuario_id')
            
            # Generar token esperado basado en la recomendación
            import hashlib
            expected_token = hashlib.md5(f"focusfit_rec_{rec_id}_{recommendation['tipo']}_{recommendation['created_at']}".encode()).hexdigest()[:16]
            
            # Si se proporciona token, verificarlo
            if token:
                if token != expected_token:
                    print(f"⚠️ SECURITY: Invalid token attempt for recommendation {rec_id} by user {current_user_id}")
                    flash('Acceso no autorizado', 'danger')
                    return redirect(url_for('recommendations_list'))
            
            # Log de acceso para auditoría
            print(f"✅ ACCESS: User {current_user_id} accessed recommendation {rec_id} (token: {'yes' if token else 'no'})")
        
        conn.close()
        
        # Generar token seguro para enlaces
        secure_token = expected_token
        
        return render_template('recommendation_details.html', 
                             recommendation=recommendation,
                             secure_token=secure_token)
    
    except Exception as e:
        print(f'Error loading recommendation details: {e}')
        flash('Error al cargar los detalles de la recomendación', 'danger')
        return redirect(url_for('recommendations_list'))

@app.route('/mis_rutinas')
def mis_rutinas():
    if 'user_email' not in session:
        flash('Debes iniciar sesión', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id_rutina AS id, nombre, tipo, duracion_horas, duracion_minutos, dias, horario
                FROM rutina WHERE id_usuario = %s
            """, (usuario['id'],))
            rutinas = cur.fetchall()
        conn.close()
    except Exception as e:
        flash(f'Error al obtener rutinas: {e}', 'danger')
        rutinas = []

    return render_template('mis_rutinas.html', rutinas=rutinas, usuario=usuario)
    
@app.route('/rutina/<int:id_rutina>')
def ver_rutina(id_rutina):
    if 'user_email' not in session:
        flash('Debes iniciar sesión para ver esta rutina', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    id_usuario = usuario['id']
    hoy = datetime.today().date()

    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id_rutina, nombre, tipo, duracion_horas, duracion_minutos, dias, horario
                FROM rutina
                WHERE id_rutina = %s AND id_usuario = %s
            """, (id_rutina, id_usuario))
            rutina = cur.fetchone()

            if not rutina:
                flash('Rutina no encontrada', 'danger')
                return redirect(url_for('planificador'))

            cur.execute("""
                SELECT ri.id_item AS id, ri.nombre_item, ri.series, ri.repeticiones, 
                       ri.tiempo, ri.prioridad, COALESCE(id.completado, FALSE) AS completado
                FROM rutina_item ri
                LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                WHERE ri.id_rutina = %s
                ORDER BY FIELD(ri.prioridad, 'alta', 'media', 'baja'), ri.nombre_item
            """, (hoy, id_usuario, id_rutina))
            items = cur.fetchall()

        conn.close()

    except Exception as e:
        print("⚠️ Error al cargar rutina:", e)
        flash('Error al cargar la rutina', 'danger')
        return redirect(url_for('planificador'))

    return render_template('ver_rutina.html', rutina=rutina, items=items, usuario=usuario)

@app.route('/editar_rutina_completa/<int:id_rutina>', methods=['GET', 'POST'])
def editar_rutina_completa(id_rutina):
    if 'user_email' not in session:
        flash('Debes iniciar sesión para editar rutinas', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    
    id_usuario = usuario['id']

    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Verificar que la rutina pertenece al usuario
            cur.execute("""
                SELECT id_rutina, nombre, tipo, duracion_horas, duracion_minutos, dias, horario
                FROM rutina
                WHERE id_rutina = %s AND id_usuario = %s
            """, (id_rutina, id_usuario))
            rutina = cur.fetchone()

            if not rutina:
                flash('Rutina no encontrada', 'danger')
                return redirect(url_for('mis_rutinas'))

            # Obtener items de la rutina
            cur.execute("""
                SELECT id_item as id, nombre_item as nombre, series, repeticiones, tiempo as tiempo_estimado, prioridad
                FROM rutina_item
                WHERE id_rutina = %s
                ORDER BY FIELD(prioridad, 'alta', 'media', 'baja'), nombre_item
            """, (id_rutina,))
            items = cur.fetchall()

        conn.close()

        if request.method == 'POST':
            # Actualizar datos básicos de la rutina
            nombre = request.form.get('nombre')
            tipo = request.form.get('tipo')
            duracion_horas = request.form.get('duracion_horas', type=int) or 0
            duracion_minutos = request.form.get('duracion_minutos', type=int) or 0
            dias = request.form.get('diasSeleccionados')
            horario = request.form.get('horario')

            # Datos de items
            nombres_items = request.form.getlist('item_nombre[]')
            prioridades = request.form.getlist('item_prioridad[]')
            tiempos = request.form.getlist('item_tiempo[]')
            series = request.form.getlist('item_series[]')
            repeticiones = request.form.getlist('item_repeticiones[]')
            item_ids = request.form.getlist('item_id[]')  # Para saber cuáles son existentes

            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    # Actualizar rutina
                    cur.execute("""
                        UPDATE rutina
                        SET nombre=%s, tipo=%s, duracion_horas=%s, duracion_minutos=%s, dias=%s, horario=%s
                        WHERE id_rutina=%s AND id_usuario=%s
                    """, (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_rutina, id_usuario))

                    # Eliminar items existentes
                    cur.execute("DELETE FROM rutina_item WHERE id_rutina = %s", (id_rutina,))

                    # Insertar nuevos items
                    if tipo == 'ejercicio':
                        for i, n in enumerate(nombres_items):
                            if n and i < len(series) and i < len(repeticiones):  # Solo insertar si hay nombre
                                s_val = int(series[i]) if series[i] else None
                                r_val = int(repeticiones[i]) if repeticiones[i] else None
                                cur.execute("""
                                    INSERT INTO rutina_item (id_rutina, nombre_item, series, repeticiones)
                                    VALUES (%s, %s, %s, %s)
                                """, (id_rutina, n, s_val, r_val))
                    else:  # estudio
                        for i, n in enumerate(nombres_items):
                            if n and i < len(tiempos) and i < len(prioridades):  # Solo insertar si hay nombre
                                t_val = int(tiempos[i]) if tiempos[i] else None
                                p_val = prioridades[i] if prioridades[i] else None
                                cur.execute("""
                                    INSERT INTO rutina_item (id_rutina, nombre_item, tiempo, prioridad)
                                    VALUES (%s, %s, %s, %s)
                                """, (id_rutina, n, t_val, p_val))

                conn.commit()
                conn.close()

                # 🔄 RE-EVALUAR racha tras editar rutina 
                try:
                    evaluar_racha_forzar_recalculo(id_usuario)
                    print(f"✅ Racha recalculada tras editar rutina para usuario {id_usuario}")
                except Exception as e:
                    print(f"⚠️ Error al recalcular racha tras editar rutina: {e}")

                flash('Rutina actualizada exitosamente', 'success')
                return redirect(url_for('mis_rutinas'))

            except Exception as e:
                flash(f'Error al actualizar rutina: {e}', 'danger')

        return render_template('editar_rutina.html', rutina=rutina, items=items, usuario=usuario)

    except Exception as e:
        flash(f'Error al cargar rutina: {e}', 'danger')
        return redirect(url_for('mis_rutinas'))

@app.route('/editar_rutina/<int:id_rutina>', methods=['POST'])
def editar_rutina(id_rutina):
    if 'user_email' not in session:
        flash('Debes iniciar sesión', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    # Obtener datos del formulario
    nombre = request.form.get('nombre')
    tipo = request.form.get('tipo')
    duracion_horas = request.form.get('duracion_horas') or 0
    duracion_minutos = request.form.get('duracion_minutos') or 0
    dias = request.form.get('dias')
    horario = request.form.get('horario')

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE rutina
                SET nombre=%s, tipo=%s, duracion_horas=%s, duracion_minutos=%s, dias=%s, horario=%s
                WHERE id_rutina=%s AND id_usuario=%s
            """, (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_rutina, usuario['id']))
            conn.commit()
        conn.close()
        flash('Rutina actualizada correctamente', 'success')
    except Exception as e:
        flash(f'Error al actualizar rutina: {e}', 'danger')

    return redirect(url_for('mis_rutinas'))


@app.route('/eliminar_rutina/<int:id_rutina>')
def eliminar_rutina(id_rutina):
    if 'user_email' not in session:
        flash('Debes iniciar sesión', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Solo elimina la rutina si pertenece al usuario
            cur.execute("DELETE FROM rutina WHERE id_rutina=%s AND id_usuario=%s", (id_rutina, usuario['id']))
            conn.commit()
        conn.close()

        # 🔄 RE-EVALUAR racha tras eliminar rutina
        try:
            evaluar_racha_forzar_recalculo(usuario['id'])
            print(f"✅ Racha recalculada tras eliminar rutina para usuario {usuario['id']}")
        except Exception as e:
            print(f"⚠️ Error al recalcular racha tras eliminar rutina: {e}")

        flash('Rutina eliminada correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar rutina: {e}', 'danger')

    return redirect(url_for('mis_rutinas'))




def send_email(to_email, subject, body):
    """Envía un correo usando SendGrid (funciona en producción)"""
    try:
        # Obtener la API Key de las variables de entorno
        sg_api_key = os.environ.get('SENDGRID_API_KEY')
        from_email = os.environ.get('MAIL_FROM', 'no-reply@focusfit.com')
        
        if not sg_api_key:
            # Modo desarrollo: imprimir en consola
            print('--- EMAIL (modo desarrollo) ---')
            print(f'To: {to_email}')
            print(f'Subject: {subject}')
            print(body)
            print('--- FIN EMAIL ---')
            return

        # Crear el email
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body
        )
        
        # Enviar con SendGrid
        sg = SendGridAPIClient(sg_api_key)
        response = sg.send(message)
        print(f'Email enviado a {to_email}, status: {response.status_code}')
        
    except Exception as e:
        print(f'Error al enviar email: {str(e)}')


@app.route('/api/notifications/due')
def api_notifications_due():
    # Devuelve notificaciones pendientes para el usuario autenticado
    if 'user_email' not in session:
        return jsonify([])
    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        return jsonify([])
    try:
        if get_due_notifications is None:
            return jsonify([])
        rows = get_due_notifications(limit=10, user_id=usuario['id'])
        # asegurar formato JSON serializable
        out = []
        for r in rows:
            if isinstance(r, dict):
                out.append({'id': r.get('id'), 'title': r.get('title'), 'message': r.get('message')})
            else:
                try:
                    out.append({'id': r[0], 'title': r[1], 'message': r[2]})
                except Exception:
                    pass
        return jsonify(out)
    except Exception as e:
        print('api_notifications_due error', e)
        return jsonify([])


@app.route('/api/notifications/mark_delivered', methods=['POST'])
def api_notifications_mark_delivered():
    data = request.get_json(silent=True) or {}
    nid = data.get('id')
    if not nid:
        return jsonify({'ok': False}), 400
    try:
        if mark_delivered is None:
            return jsonify({'ok': False}), 501
        mark_delivered(nid)
        return jsonify({'ok': True})
    except Exception as e:
        print('mark_delivered error', e)
        return jsonify({'ok': False}), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        correo = request.form.get('correo')
        nombre = request.form.get('nombre')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # 1. Campos vacíos
        if not correo or not nombre or not password or not confirm_password:
            flash('Todos los campos son obligatorios.', 'warning')
            return redirect(url_for('register'))

        # 2. Email válido (backend)
        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, correo):
            flash('Correo inválido.', 'danger')
            return redirect(url_for('register'))

        # 3. Contraseña y confirmación
        if password != confirm_password:
            flash('Las contraseñas no coinciden.', 'danger')
            return redirect(url_for('register'))

        # 4. Complejidad de contraseña
        pwd_regex = r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>\/?]).+$'
        if not re.match(pwd_regex, password):
            flash('La contraseña debe contener letras, números y al menos un carácter especial.', 'danger')
            return redirect(url_for('register'))

        # 5. Correo ya existe
        existing = get_user_by_email(correo)
        if existing:
            flash('El correo ya está registrado.', 'danger')
            return redirect(url_for('register'))

        # 6. Crear usuario
        try:
            create_user(nombre, correo, password)
            flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error al crear usuario: {e}', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo')
        password = request.form.get('password')

        # 1. Validar campos vacíos
        if not correo or not password:
            flash('Completa todos los campos.', 'warning')
            return redirect(url_for('login'))

        # 2. Validar formato de email
        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, correo):
            flash('Correo inválido.', 'danger')
            return redirect(url_for('login'))

        # 3. Verificar usuario
        user = get_user_by_email(correo)
        if not user:
            flash('Usuario no encontrado.', 'danger')
            return redirect(url_for('login'))

        # 4. Verificar contraseña
        stored = user.get('password')
        if not check_password_hash(stored, password):
            flash('Contraseña incorrecta.', 'danger')
            return redirect(url_for('login'))

        # 5. Inicio de sesión exitoso
        session['user_email'] = correo
        session['usuario_id'] = user['id']  # Agregar ID del usuario a la sesión
        print(f"✅ Login exitoso - Usuario ID: {user['id']}, Email: {correo}")
        # Enviar recordatorio por email al hacer login (una vez al día)
        try:
            conn2 = get_db_connection()
            from datetime import date
            today = date.today()
            with conn2.cursor() as cur2:
                marker = "[LOGIN_REMINDER]"
                cur2.execute(
                    "SELECT 1 FROM user_notifications WHERE user_id = (SELECT id FROM usuario WHERE correo = %s) AND message LIKE %s AND DATE(fecha_programada) = %s",
                    (correo, f"%{marker}%", today)
                )
                already = cur2.fetchone()

            if not already:
                # crear el cuerpo con rutinas de hoy
                items = []
                try:
                    conn3 = get_db_connection()
                    from datetime import datetime
                    dias_semana = {
                        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
                    }
                    dia_actual = dias_semana[datetime.today().strftime('%A')]
                    with conn3.cursor(pymysql.cursors.DictCursor) as cur3:
                        cur3.execute(
                            """
                            SELECT r.nombre AS rutina, ri.nombre_item
                            FROM rutina r
                            JOIN rutina_item ri ON ri.id_rutina = r.id_rutina
                            WHERE r.id_usuario = (SELECT id FROM usuario WHERE correo = %s)
                              AND FIND_IN_SET(%s, r.dias)
                            ORDER BY r.horario ASC
                            """,
                            (correo, dia_actual)
                        )
                        items = cur3.fetchall()
                except Exception:
                    items = []
                finally:
                    try:
                        conn3.close()
                    except Exception:
                        pass

                # construir mensaje
                if items:
                    lines = [f"Rutinas para hoy ({dia_actual}):"]
                    last_r = None
                    for it in items:
                        rn = it.get('rutina')
                        ni = it.get('nombre_item')
                        if rn != last_r:
                            lines.append(f"- {rn}:")
                            last_r = rn
                        lines.append(f"   • {ni}")
                    body = "\n".join(lines) + "\n\n¡Ánimo! Completa tus actividades y mejora tu racha."
                else:
                    body = "Tienes rutinas en la app. Hoy no tienes items programados, pero puedes revisar y programar nuevas rutinas en FocusFit."

                # enviar email (no bloquear si falla)
                try:
                    send_email(correo, 'Recordatorio diario - FocusFit', body)
                except Exception as e:
                    print('Error enviando login reminder:', e)

                # registrar en user_notifications para evitar duplicados (fecha_programada = ahora)
                try:
                    with conn2.cursor() as cur4:
                        cur4.execute(
                            'INSERT INTO user_notifications (user_id, title, message, fecha_programada, tipo, fecha_envio, is_read) VALUES ((SELECT id FROM usuario WHERE correo = %s), %s, %s, %s, %s, %s, %s)',
                            (correo, 'Recordatorio diario', f"[LOGIN_REMINDER] Recordatorio enviado al iniciar sesión", datetime.now(), 'email_once', datetime.now(), 1)
                        )
                        conn2.commit()
                except Exception as e:
                    print('Error registrando login reminder:', e)
        except Exception:
            pass
        flash('Has iniciado sesión.', 'success')
        return redirect(url_for('inicio'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_email', None)
    session.pop('usuario_id', None)
    print("🚪 Logout - Sesión limpiada")
    flash('Sesión cerrada', 'info')
    return redirect(url_for('inicio'))

# Serializador seguro
def generate_token(email):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(email, salt='password-recover-salt')

def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        email = serializer.loads(token, salt='password-recover-salt', max_age=expiration)
    except Exception:
        return False
    return email

@app.route('/recover', methods=['GET', 'POST'])
def recover():
    if request.method == 'POST':
        correo = request.form.get('correo')
        usuario = get_user_by_email(correo)
        if not usuario:
            flash('Correo no registrado', 'danger')
            return redirect(url_for('recover'))

        token = generate_token(correo)
        link = url_for('reset_password', token=token, _external=True)
        send_email(correo, 'Recuperación de contraseña', f'Haz clic aquí para restablecer tu contraseña: {link}')

        flash('Se ha enviado un enlace de recuperación a tu correo', 'success')
        return redirect(url_for('login'))

    return render_template('recover.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = confirm_token(token)
    if not email:
        flash('Enlace inválido o expirado', 'danger')
        return redirect(url_for('recover'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        pwd_regex = r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>\/?]).+$'

        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'danger')
        elif not re.match(pwd_regex, password):
            flash('La contraseña debe tener letras, números y un carácter especial', 'danger')
        else:
            update_user_password(email, password)
            flash('Contraseña restablecida exitosamente', 'success')
            return redirect(url_for('login'))

    return render_template('reset_password.html')


@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'user_email' not in session:
        flash('Debes iniciar sesión para acceder al perfil.', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        correo = request.form.get('correo')
        nombre = request.form.get('nombre')
        telefono = request.form.get('telefono')
        password = request.form.get('password')

        # actualizar correo y nombre
        try:
            if correo and correo != usuario.get('correo'):
                update_user_email(usuario['id'], correo)
                # actualizar sesión para futuras consultas
                session['user_email'] = correo
        except Exception:
            pass
        try:
            if nombre and nombre != usuario.get('nombre'):
                update_user_name(usuario['id'], nombre)
        except Exception:
            pass

        # actualizar contraseña si se proporcionó
        try:
            if password:
                update_user_password(usuario['id'], password)
        except Exception:
            pass

        # actualizar telefono si se proporcionó y cambió
        try:
            if telefono is not None:
                telefono_val = telefono.strip()
                if telefono_val != (usuario.get('telefono') or ''):
                    update_user_phone(usuario['id'], telefono_val)
        except Exception:
            pass

        # manejo de avatar
        avatar = request.files.get('avatar')
        if avatar and allowed_file(avatar.filename):
            try:
                # generar nombre único para evitar colisiones y cache
                ext = os.path.splitext(secure_filename(avatar.filename))[1].lower()
                unique_name = f"{uuid.uuid4().hex}{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                avatar.save(save_path)
                print(f"[DEBUG] Avatar guardado en: {save_path}")
                update_user_avatar(usuario['id'], unique_name)
                print(f"[DEBUG] update_user_avatar llamado con: {unique_name}")
            except Exception:
                pass

        flash('Perfil actualizado correctamente.', 'success')
        return redirect(url_for('perfil'))

    return render_template('perfil.html', usuario=usuario)


@app.route('/planificador')
def planificador():
    if 'user_email' not in session:
        flash('Debes iniciar sesión para acceder al planificador', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    
    id_usuario = usuario['id']
    hoy = datetime.today().date()

    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id_rutina AS id, nombre
                FROM rutina
                WHERE id_usuario = %s
                ORDER BY nombre ASC
            """, (id_usuario,))
            rutinas = cur.fetchall()

            cur.execute("""
                SELECT 
                    ri.id_item AS id,
                    r.id_rutina,
                    r.nombre AS titulo,
                    r.dias,
                    ri.nombre_item,
                    ri.series,
                    ri.repeticiones,
                    ri.tiempo,
                    ri.prioridad,
                    COALESCE(id.completado, FALSE) AS completado
                FROM rutina_item ri
                JOIN rutina r ON ri.id_rutina = r.id_rutina
                LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                WHERE r.id_usuario = %s
                ORDER BY r.nombre ASC,
                         FIELD(ri.prioridad, 'alta', 'media', 'baja')
            """, (hoy, id_usuario, id_usuario))
            lista_diaria = cur.fetchall()

        conn.close()

    except Exception as e:
        print("⚠️ Error al cargar planificador:", e)
        flash('Error al cargar el planificador', 'danger')
        rutinas = []
        lista_diaria = []

    return render_template('planificador.html', rutinas=rutinas, lista_diaria=lista_diaria, usuario=usuario)

@app.route('/lista_diaria', methods=['GET', 'POST'])
def lista_diaria():
    if 'user_email' not in session:
        flash('Debes iniciar sesión para ver tu lista diaria', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    
    # Generar items diarios automáticamente
    generar_items_diarios(usuario['id'])
    
    # ⚠️ SISTEMA MALO DESACTIVADO (línea 1025)
    # evaluate_daily_streak causa duplicación - DESACTIVADO
    # try:
    #     if evaluate_daily_streak is not None:
    #         evaluate_daily_streak(usuario['id'])
    # except Exception:
    #     pass
    
    hoy_dt = datetime.today()
    dias_traduccion = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    dia_actual = dias_traduccion[hoy_dt.strftime('%A')]
    hoy = hoy_dt.date()

    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT * FROM rutina
            WHERE id_usuario = %s AND dias LIKE %s
        """, (usuario['id'], f"%{dia_actual}%"))
        rutinas = cur.fetchall()

        for r in rutinas:
            cur.execute("""
                SELECT ri.id_item AS id, ri.nombre_item, ri.series, ri.repeticiones,
                        ri.tiempo, ri.prioridad, COALESCE(id.completado, FALSE) AS completado
                FROM rutina_item ri
                LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                WHERE ri.id_rutina = %s
            """, (hoy, usuario['id'], r['id_rutina']))
            r['items'] = cur.fetchall()

    conn.close()

    return render_template('lista_diaria.html', rutinas=rutinas, dia_actual=dia_actual)


def generar_items_diarios(id_usuario, fecha=None):
    """
    Genera automáticamente los registros en item_diario para las rutinas del día.
    Esta función se ejecuta automáticamente cuando un usuario accede a su lista diaria.
    """
    if fecha is None:
        fecha = datetime.today().date()
    
    # Obtener día de la semana en español
    dias_traduccion = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    dia_actual = dias_traduccion[fecha.strftime('%A')]
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Buscar rutinas activas para el día actual
            cur.execute("""
                SELECT r.id_rutina, r.nombre, r.tipo
                FROM rutina r
                WHERE r.id_usuario = %s AND r.dias LIKE %s
            """, (id_usuario, f"%{dia_actual}%"))
            rutinas_del_dia = cur.fetchall()
            
            items_creados = 0
            
            for rutina in rutinas_del_dia:
                # Obtener items de esta rutina
                cur.execute("""
                    SELECT id_item FROM rutina_item 
                    WHERE id_rutina = %s
                """, (rutina['id_rutina'],))
                items_rutina = cur.fetchall()
                
                for item in items_rutina:
                    # Verificar si ya existe un registro para este item en esta fecha
                    cur.execute("""
                        SELECT id FROM item_diario 
                        WHERE id_item = %s AND id_usuario = %s AND fecha = %s
                    """, (item['id_item'], id_usuario, fecha))
                    
                    if not cur.fetchone():
                        # Crear registro si no existe
                        cur.execute("""
                            INSERT INTO item_diario (id_item, id_usuario, fecha, completado)
                            VALUES (%s, %s, %s, FALSE)
                        """, (item['id_item'], id_usuario, fecha))
                        items_creados += 1
            
            conn.commit()
            conn.close()
            
            if items_creados > 0:
                print(f"✅ Generados {items_creados} items diarios para usuario {id_usuario} en {fecha}")
            
            return items_creados
            
    except Exception as e:
        print(f"❌ Error generando items diarios: {e}")
        return 0


@app.route('/api/marcar_completado/<int:id_item>', methods=['POST'])
def api_marcar_completado(id_item):
    if 'user_email' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    try:
        usuario = get_user_by_email(session['user_email'])
        if not usuario:
            return jsonify({'error': 'Sesión inválida'}), 401

        id_usuario = usuario['id']
        hoy = datetime.today().strftime('%Y-%m-%d')

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Verificar que el item pertenece al usuario
                cur.execute("""
                    SELECT r.id_usuario
                    FROM rutina_item ri
                    JOIN rutina r ON ri.id_rutina = r.id_rutina
                    WHERE ri.id_item = %s
                """, (id_item,))
                result = cur.fetchone()
                
                # ✅ ACCESO POR NOMBRE DE COLUMNA (porque usas DictCursor)
                if not result or result['id_usuario'] != id_usuario:
                    return jsonify({'error': 'Item no encontrado'}), 404

                # Verificar si ya existe un registro para hoy
                cur.execute("""
                    SELECT completado FROM item_diario
                    WHERE id_usuario = %s AND id_item = %s AND fecha = %s
                """, (id_usuario, id_item, hoy))
                log_existente = cur.fetchone()

                if log_existente:
                    nuevo_estado = not bool(log_existente['completado'])
                    cur.execute("""
                        UPDATE item_diario
                        SET completado = %s
                        WHERE id_usuario = %s AND id_item = %s AND fecha = %s
                    """, (nuevo_estado, id_usuario, id_item, hoy))
                else:
                    cur.execute("""
                        INSERT INTO item_diario (id_usuario, id_item, fecha, completado)
                        VALUES (%s, %s, %s, %s)
                    """, (id_usuario, id_item, hoy, True))
                    nuevo_estado = True

                conn.commit()

                # Evaluar racha FORZANDO RECÁLCULO (para marcar/desmarcar)
                try:
                    estado_racha = evaluar_racha_forzar_recalculo(id_usuario)
                    streak_days = estado_racha['racha_actual']
                    racha_activa_api = estado_racha['racha_activa']
                except Exception:
                    streak_days = 0
                    racha_activa_api = False

                # Calcular porcentaje de cumplimiento de hoy
                dias_semana = {
                    'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
                }
                dia_actual = dias_semana[datetime.today().strftime('%A')]
                
                # Calcular total de items programados para hoy
                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM rutina r
                    JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                    WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                """, (id_usuario, dia_actual))
                total = cur.fetchone()['total'] or 0

                cumplimiento_porcentaje = 0
                if total > 0:
                    # Calcular completados hoy
                    cur.execute("""
                        SELECT COUNT(*) AS completados
                        FROM rutina r
                        JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                        LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                        WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias) AND COALESCE(id.completado, FALSE) = 1
                    """, (hoy, id_usuario, id_usuario, dia_actual))
                    completados = cur.fetchone()['completados'] or 0
                    cumplimiento_porcentaje = round((completados / total) * 100)

                return jsonify({
                    'success': True,
                    'completado': nuevo_estado,
                    'streak_days': streak_days,
                    'racha_activa': racha_activa_api,
                    'cumplimiento_porcentaje': cumplimiento_porcentaje
                })

        finally:
            conn.close()

    except Exception as e:
        import traceback
        print("🚨 ERROR EN api_marcar_completado:")
        traceback.print_exc()
        return jsonify({'error': 'Error interno'}), 500


# Nueva ruta para el frontend mejorado
@app.route('/marcar_item', methods=['POST'])
def marcar_item():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401

    try:
        data = request.get_json()
        id_item = data.get('id')
        completado = data.get('completado', False)
        
        usuario = get_user_by_email(session['user_email'])
        if not usuario:
            return jsonify({'success': False, 'message': 'Sesión inválida'}), 401

        id_usuario = usuario['id']
        hoy = datetime.today().strftime('%Y-%m-%d')

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Verificar que el item pertenece al usuario
                cur.execute("""
                    SELECT r.id_usuario
                    FROM rutina_item ri
                    JOIN rutina r ON ri.id_rutina = r.id_rutina
                    WHERE ri.id_item = %s
                """, (id_item,))
                result = cur.fetchone()
                
                if not result or result['id_usuario'] != id_usuario:
                    return jsonify({'success': False, 'message': 'Item no encontrado'}), 404

                # Verificar si ya existe un registro para hoy
                cur.execute("""
                    SELECT completado FROM item_diario
                    WHERE id_usuario = %s AND id_item = %s AND fecha = %s
                """, (id_usuario, id_item, hoy))
                log_existente = cur.fetchone()

                if log_existente:
                    cur.execute("""
                        UPDATE item_diario
                        SET completado = %s
                        WHERE id_usuario = %s AND id_item = %s AND fecha = %s
                    """, (completado, id_usuario, id_item, hoy))
                else:
                    cur.execute("""
                        INSERT INTO item_diario (id_usuario, id_item, fecha, completado)
                        VALUES (%s, %s, %s, %s)
                    """, (id_usuario, id_item, hoy, completado))

                conn.commit()

                # Evaluar racha FORZANDO RECÁLCULO
                try:
                    estado_racha = evaluar_racha_forzar_recalculo(id_usuario)
                    streak_days = estado_racha['racha_actual']
                    racha_activa_api = estado_racha['racha_activa']
                except Exception:
                    streak_days = 0
                    racha_activa_api = False

                return jsonify({
                    'success': True,
                    'completado': completado,
                    'streak_days': streak_days,
                    'racha_activa': racha_activa_api
                })

        finally:
            conn.close()

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error del servidor: {str(e)}'}), 500


# Ruta para obtener estadísticas actualizadas
@app.route('/api/estadisticas_actuales')
def api_estadisticas_actuales():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401

    try:
        usuario = get_user_by_email(session['user_email'])
        if not usuario:
            return jsonify({'success': False, 'message': 'Sesión inválida'}), 401

        id_usuario = usuario['id']
        
        # Evaluar racha actual
        try:
            estado_racha = evaluar_racha_inteligente(id_usuario)
            rachas = estado_racha['racha_actual']
            racha_activa = estado_racha['racha_activa']
        except Exception:
            rachas = 0
            racha_activa = False

        # Calcular porcentaje de cumplimiento actual
        dias_semana = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
        }
        dia_actual = dias_semana[datetime.today().strftime('%A')]
        hoy = datetime.today().strftime('%Y-%m-%d')
        
        conn = get_db_connection()
        cumplimiento_porcentaje = 0
        progreso_semanal = []
        
        try:
            with conn.cursor() as cur:
                # Calcular cumplimiento de hoy
                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM rutina r
                    JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                    WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                """, (id_usuario, dia_actual))
                total = cur.fetchone()['total'] or 0

                if total > 0:
                    cur.execute("""
                        SELECT COUNT(*) AS completados
                        FROM rutina r
                        JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                        LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                        WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias) AND COALESCE(id.completado, FALSE) = 1
                    """, (hoy, id_usuario, id_usuario, dia_actual))
                    completados = cur.fetchone()['completados'] or 0
                    cumplimiento_porcentaje = round((completados / total) * 100)

                # Calcular progreso semanal
                dias_semana_ordenados = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                hoy_dt = datetime.today()
                
                for i, dia in enumerate(dias_semana_ordenados):
                    # Calcular la fecha correspondiente al día de la semana
                    dias_desde_lunes = i
                    lunes_esta_semana = hoy_dt - timedelta(days=hoy_dt.weekday())
                    fecha_dia = lunes_esta_semana + timedelta(days=dias_desde_lunes)
                    fecha_str = fecha_dia.strftime('%Y-%m-%d')
                    
                    # Total de items para este día
                    cur.execute("""
                        SELECT COUNT(*) AS total
                        FROM rutina r
                        JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                        WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                    """, (id_usuario, dia))
                    total_dia = cur.fetchone()['total'] or 0
                    
                    porcentaje_dia = 0
                    if total_dia > 0:
                        # Completados para este día
                        cur.execute("""
                            SELECT COUNT(*) AS completados
                            FROM rutina r
                            JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                            LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                            WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias) AND COALESCE(id.completado, FALSE) = 1
                        """, (fecha_str, id_usuario, id_usuario, dia))
                        completados_dia = cur.fetchone()['completados'] or 0
                        porcentaje_dia = round((completados_dia / total_dia) * 100)
                    
                    progreso_semanal.append({
                        'dia': dia[:3],  # Abreviatura del día
                        'porcentaje': porcentaje_dia
                    })

        finally:
            conn.close()

        return jsonify({
            'success': True,
            'rachas': rachas,
            'racha_activa': racha_activa,
            'cumplimiento_porcentaje': cumplimiento_porcentaje,
            'progreso_semanal': progreso_semanal
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error del servidor: {str(e)}'}), 500


@app.route('/api/progreso_semanal')
def api_progreso_semanal():
    """API para obtener progreso semanal actualizado en tiempo real"""
    if 'user_email' not in session:
        return jsonify({'error': 'No autorizado'}), 401

    try:
        usuario = get_user_by_email(session['user_email'])
        if not usuario:
            return jsonify({'error': 'Sesión inválida'}), 401

        id_usuario = usuario['id']
        
        # Días de la semana
        dias_semana = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
        }
        dia_actual = dias_semana[datetime.today().strftime('%A')]
        hoy = datetime.today().date()

        conn = get_db_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                # Progreso semanal
                dias_orden = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                progreso_semanal = []

                for dia in dias_orden:
                    hoy_dt = datetime.today()
                    dias_desde_lunes = hoy_dt.weekday()  # 0=Lunes
                    indice_dia = dias_orden.index(dia)
                    fecha_dia = (hoy_dt - timedelta(days=dias_desde_lunes - indice_dia)).date()

                    # Total de tareas para este día
                    cur.execute("""
                        SELECT COUNT(*) AS total
                        FROM rutina r
                        JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                        WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias)
                    """, (id_usuario, dia))
                    total = cur.fetchone()['total'] or 0

                    if total == 0:
                        porcentaje = 0
                    else:
                        # Tareas completadas para este día
                        cur.execute("""
                            SELECT COUNT(*) AS completados
                            FROM rutina r
                            JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                            LEFT JOIN item_diario id ON ri.id_item = id.id_item AND id.fecha = %s AND id.id_usuario = %s
                            WHERE r.id_usuario = %s AND FIND_IN_SET(%s, r.dias) AND COALESCE(id.completado, FALSE) = 1
                        """, (fecha_dia, id_usuario, id_usuario, dia))
                        completados = cur.fetchone()['completados'] or 0
                        porcentaje = round((completados / total) * 100)

                    progreso_semanal.append({
                        'dia': dia[:3], 
                        'porcentaje': porcentaje,
                        'total_tareas': total,
                        'tareas_completadas': completados if total > 0 else 0
                    })

                return jsonify({
                    'success': True,
                    'progreso_semanal': progreso_semanal,
                    'dia_actual': dia_actual
                })

        finally:
            conn.close()

    except Exception as e:
        import traceback
        print("🚨 ERROR EN api_progreso_semanal:")
        traceback.print_exc()
        return jsonify({'error': 'Error interno'}), 500


@app.route('/estadisticas')
def ver_estadisticas():
    print(f"🔍 DEBUG - Estadísticas: sesión = {dict(session)}")
    
    if 'usuario_id' not in session:
        print("❌ No hay usuario_id en sesión, redirigiendo al login")
        return redirect('/login')
    
    try:
        from estadisticas_usuario import calcular_estadisticas_usuario
        
        user_id = session['usuario_id']
        print(f"✅ Usuario en sesión: {user_id}")
        estadisticas_completas = calcular_estadisticas_usuario(user_id)
        
        # Formatear para el template (mantener compatibilidad)
        estadisticas = {
            'rachas': estadisticas_completas['racha_actual'],
            'racha_maxima': estadisticas_completas['racha_maxima'],
            'cumplimiento_porcentaje': estadisticas_completas['porcentaje_cumplimiento'],
            'tiempo_total': estadisticas_completas['tiempo_total_horas'],
            'dias_completados': estadisticas_completas['dias_completados'],
            'dias_programados': estadisticas_completas['dias_programados'],
            'dias_activos': estadisticas_completas['dias_activos'],
            'total_rutinas': estadisticas_completas['total_rutinas'],
            'tareas_completadas_total': estadisticas_completas['tareas_completadas_total'],
            'periodo_dias': estadisticas_completas['periodo_dias']
        }
        
    except Exception as e:
        print(f"❌ Error obteniendo estadísticas: {e}")
        estadisticas = {
            'rachas': 0, 
            'racha_maxima': 0,
            'cumplimiento_porcentaje': 0, 
            'tiempo_total': 0,
            'dias_completados': 0,
            'dias_programados': 0,
            'dias_activos': 0,
            'total_rutinas': 0,
            'tareas_completadas_total': 0,
            'periodo_dias': 30
        }
    
    return render_template('estadisticas.html', estadisticas=estadisticas)



# admin send_email_reminders removed: admin functionality lives in admin_app/admin_dashboard



@app.route('/progreso')
def progreso():
    if 'user_email' not in session:
        # Login temporal para pruebas
        session['user_email'] = 'admin@focusfit.com'
        print("🔧 LOGIN TEMPORAL PARA PRUEBAS")
    
    if 'user_email' not in session:
        flash('Debes iniciar sesión para ver tu progreso', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    
    id_usuario = usuario['id']
    hoy = datetime.today().date()
    
    # Generar items diarios automáticamente
    generar_items_diarios(id_usuario)
    
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            
            # Calcular progreso de la semana actual (lunes a domingo)
            progreso_dias = []
            
            # Obtener el lunes de esta semana
            dias_desde_lunes = hoy.weekday()  # 0 = lunes, 6 = domingo
            inicio_semana = hoy - timedelta(days=dias_desde_lunes)
            
            # Generar los 7 días de la semana actual
            for i in range(7):
                fecha_dia = inicio_semana + timedelta(days=i)
                
                # Nombre del día
                dias_nombres = {
                    'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
                }
                nombre_dia = dias_nombres[fecha_dia.strftime('%A')]
                
                # Si es día pasado o presente, usar item_diario
                if fecha_dia <= hoy:
                    # Obtener tareas totales del día
                    cur.execute("""
                        SELECT COUNT(*) as total_tareas
                        FROM item_diario 
                        WHERE id_usuario = %s AND fecha = %s
                    """, (id_usuario, fecha_dia))
                    
                    total_result = cur.fetchone()
                    total_tareas = total_result['total_tareas'] if total_result else 0
                    
                    # Obtener tareas completadas del día
                    cur.execute("""
                        SELECT COUNT(*) as tareas_completadas
                        FROM item_diario 
                        WHERE id_usuario = %s AND fecha = %s AND completado = TRUE
                    """, (id_usuario, fecha_dia))
                    
                    completadas_result = cur.fetchone()
                    tareas_completadas = completadas_result['tareas_completadas'] if completadas_result else 0
                    
                else:
                    # Si es día futuro, calcular basado en rutinas programadas
                    # Buscar rutinas que tienen este día programado
                    cur.execute("""
                        SELECT COUNT(ri.id_item) as total_tareas
                        FROM rutina r
                        JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                        WHERE r.id_usuario = %s AND r.dias LIKE %s
                    """, (id_usuario, f"%{nombre_dia}%"))
                    
                    total_result = cur.fetchone()
                    total_tareas = total_result['total_tareas'] if total_result else 0
                    tareas_completadas = 0  # Día futuro, nada completado aún
                
                # Calcular porcentaje
                if total_tareas > 0:
                    porcentaje = round((tareas_completadas / total_tareas) * 100)
                else:
                    porcentaje = 0
                
                progreso_dias.append({
                    'fecha': fecha_dia.strftime('%d/%m'),
                    'fecha_completa': fecha_dia.strftime('%Y-%m-%d'),
                    'nombre_dia': nombre_dia,
                    'total_tareas': total_tareas,
                    'tareas_completadas': tareas_completadas,
                    'porcentaje': porcentaje,
                    'es_hoy': fecha_dia == hoy,
                    'es_futuro': fecha_dia > hoy
                })
            
            # Los días ya están en orden correcto (lunes a domingo)
            
            # Calcular progreso promedio de la semana
            porcentajes_validos = [dia['porcentaje'] for dia in progreso_dias if dia['total_tareas'] > 0]
            promedio_semana = round(sum(porcentajes_validos) / len(porcentajes_validos)) if porcentajes_validos else 0
            
            # Progreso de hoy
            progreso_hoy = next((dia for dia in progreso_dias if dia['es_hoy']), None)
            
            # Calcular estadísticas adicionales
            mejor_dia_datos = max(progreso_dias, key=lambda x: x['porcentaje']) if progreso_dias else {'porcentaje': 0, 'nombre_dia': 'N/A'}
            dias_100 = len([dia for dia in progreso_dias if dia['porcentaje'] == 100])
            
            # Calcular días consecutivos (desde hoy hacia atrás)
            dias_consecutivos = 0
            for dia in reversed(progreso_dias):
                if dia['es_futuro']:
                    continue
                if dia['porcentaje'] == 100:
                    dias_consecutivos += 1
                else:
                    break
            
            estadisticas_extra = {
                'mejor_dia': mejor_dia_datos,
                'dias_100': dias_100,
                'dias_consecutivos': dias_consecutivos
            }
            
            # Datos para la gráfica de columnas (solo tareas completadas)
            grafica_datos = []
            max_completadas = 0
            for dia in progreso_dias:
                completadas = dia['tareas_completadas']
                if completadas > max_completadas:
                    max_completadas = completadas
                
                grafica_datos.append({
                    'dia': dia['nombre_dia'][:3],  # Lun, Mar, Mie, etc.
                    'completadas': completadas,
                    'fecha': dia['fecha'],
                    'es_hoy': dia['es_hoy'],
                    'es_futuro': dia['es_futuro']
                })
            
            # Calcular altura máxima para normalizar las columnas (mínimo 5 para que se vea bien)
            altura_maxima = max(max_completadas, 5) if max_completadas > 0 else 5
        
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Error en /progreso: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error al cargar el progreso', 'danger')
        progreso_dias = []
        promedio_semana = 0
        progreso_hoy = None
        grafica_datos = []
        altura_maxima = 5
        estadisticas_extra = {
            'mejor_dia': {'porcentaje': 0, 'nombre_dia': 'N/A'},
            'dias_100': 0,
            'dias_consecutivos': 0
        }

    return render_template('progreso.html', 
                         progreso_dias=progreso_dias,
                         promedio_semana=promedio_semana,
                         progreso_hoy=progreso_hoy,
                         grafica_datos=grafica_datos,
                         altura_maxima=altura_maxima,
                         estadisticas_extra=estadisticas_extra,
                         usuario=usuario)


@app.route('/registros_actividades')
def registros_actividades():
    """Página para ver registros de actividades de semanas anteriores"""
    if 'user_email' not in session:
        # Login temporal para pruebas
        session['user_email'] = 'admin@focusfit.com'
        print("🔧 LOGIN TEMPORAL PARA PRUEBAS - REGISTROS")
    
    if 'user_email' not in session:
        flash('Debes iniciar sesión para ver tus registros', 'warning')
        return redirect(url_for('login'))

    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('login'))
    
    id_usuario = usuario['id']
    
    # Primero, encontrar la primera semana con rutinas del usuario
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Encontrar la primera rutina creada por el usuario
            cur.execute("""
                SELECT MIN(DATE(fecha_creacion)) as primera_rutina
                FROM rutina 
                WHERE id_usuario = %s
            """, (id_usuario,))
            
            result = cur.fetchone()
            primera_rutina_fecha = result['primera_rutina'] if result and result['primera_rutina'] else None
        conn.close()
    except Exception as e:
        print(f"Error al buscar primera rutina: {e}")
        primera_rutina_fecha = None
    
    # Si no hay rutinas, redirigir con mensaje
    if not primera_rutina_fecha:
        flash('Aún no tienes rutinas creadas. ¡Crea tu primera rutina!', 'info')
        return redirect(url_for('planificador'))
    
    # Calcular fechas
    hoy = datetime.today().date()
    inicio_semana_actual = hoy - timedelta(days=hoy.weekday())  # Lunes de esta semana
    inicio_primera_semana = primera_rutina_fecha - timedelta(days=primera_rutina_fecha.weekday())
    
    # Calcular máximo offset permitido (semanas desde la primera rutina hasta ahora)
    max_offset = (inicio_semana_actual - inicio_primera_semana).days // 7
    
    # Obtener offset de semana de la URL (por defecto 0 = semana actual)
    semana_offset = request.args.get('semana_offset', 0, type=int)
    # Limitar al rango válido
    semana_offset = max(0, min(semana_offset, max_offset))
    
    # Calcular fechas de la semana seleccionada
    inicio_semana_seleccionada = inicio_semana_actual - timedelta(weeks=semana_offset)
    fin_semana_seleccionada = inicio_semana_seleccionada + timedelta(days=6)
    
    # Generar items diarios automáticamente
    generar_items_diarios(id_usuario)
    
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            
            # Calcular progreso de los 7 días de la semana seleccionada
            progreso_dias = []
            total_tareas_semana = 0
            tareas_completadas_semana = 0
            dias_con_actividad = 0
            dias_perfectos = 0
            mejor_dia = {'porcentaje': 0, 'nombre': ''}
            racha_actual = 0
            racha_maxima = 0
            
            for i in range(7):
                fecha_dia = inicio_semana_seleccionada + timedelta(days=i)
                
                # Nombre del día
                dias_nombres = {
                    'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
                }
                nombre_dia = dias_nombres[fecha_dia.strftime('%A')]
                
                # Si es día pasado o presente, usar item_diario
                if fecha_dia <= hoy:
                    # Obtener tareas totales del día
                    cur.execute("""
                        SELECT COUNT(*) as total_tareas
                        FROM item_diario 
                        WHERE id_usuario = %s AND fecha = %s
                    """, (id_usuario, fecha_dia))
                    
                    total_result = cur.fetchone()
                    total_tareas = total_result['total_tareas'] if total_result else 0
                    
                    # Obtener tareas completadas del día
                    cur.execute("""
                        SELECT COUNT(*) as tareas_completadas
                        FROM item_diario 
                        WHERE id_usuario = %s AND fecha = %s AND completado = TRUE
                    """, (id_usuario, fecha_dia))
                    
                    completadas_result = cur.fetchone()
                    tareas_completadas = completadas_result['tareas_completadas'] if completadas_result else 0
                    
                else:
                    # Si es día futuro, calcular basado en rutinas programadas
                    # Buscar rutinas que tienen este día programado
                    cur.execute("""
                        SELECT COUNT(ri.id_item) as total_tareas
                        FROM rutina r
                        JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                        WHERE r.id_usuario = %s AND r.dias LIKE %s
                    """, (id_usuario, f"%{nombre_dia}%"))
                    
                    total_result = cur.fetchone()
                    total_tareas = total_result['total_tareas'] if total_result else 0
                    tareas_completadas = 0  # Día futuro, nada completado aún
                
                # Calcular porcentaje
                if total_tareas > 0:
                    porcentaje = round((tareas_completadas / total_tareas) * 100)
                    # Solo contar para estadísticas si no es día futuro
                    if fecha_dia <= hoy:
                        dias_con_actividad += 1
                        if porcentaje == 100:
                            dias_perfectos += 1
                            racha_actual += 1
                            racha_maxima = max(racha_maxima, racha_actual)
                        else:
                            racha_actual = 0
                else:
                    porcentaje = 0
                
                # Estadísticas semanales (solo días pasados/presente)
                if fecha_dia <= hoy:
                    total_tareas_semana += total_tareas
                    tareas_completadas_semana += tareas_completadas
                
                # Mejor día (solo días pasados/presente)
                if fecha_dia <= hoy and porcentaje > mejor_dia['porcentaje']:
                    mejor_dia['porcentaje'] = porcentaje
                    mejor_dia['nombre'] = fecha_dia.strftime('%A')
                
                progreso_dias.append({
                    'fecha': fecha_dia.strftime('%d/%m'),
                    'fecha_completa': fecha_dia.strftime('%Y-%m-%d'),
                    'nombre_dia': nombre_dia,
                    'total_tareas': total_tareas,
                    'tareas_completadas': tareas_completadas,
                    'porcentaje': porcentaje,
                    'es_hoy': fecha_dia == hoy,
                    'es_futuro': fecha_dia > hoy
                })
            
            # Calcular porcentaje semanal
            if total_tareas_semana > 0:
                porcentaje_semanal = round((tareas_completadas_semana / total_tareas_semana) * 100)
            else:
                porcentaje_semanal = 0
            
            # Calcular promedio diario (solo días no futuros con tareas)
            porcentajes_validos = [dia['porcentaje'] for dia in progreso_dias if dia['total_tareas'] > 0 and not dia['es_futuro']]
            promedio_diario = round(sum(porcentajes_validos) / len(porcentajes_validos)) if porcentajes_validos else 0
            
            # Traducir nombre del mejor día
            dias_nombres_es = {
                'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
            }
            mejor_dia['nombre'] = dias_nombres_es.get(mejor_dia['nombre'], mejor_dia['nombre'])
            
            # Información de la semana actual
            semana_actual = {
                'offset': semana_offset,
                'max_offset': max_offset,
                'es_actual': semana_offset == 0,
                'fecha_inicio': inicio_semana_seleccionada.strftime('%d/%m/%Y'),
                'fecha_fin': fin_semana_seleccionada.strftime('%d/%m/%Y'),
                'total_tareas': total_tareas_semana,
                'tareas_completadas': tareas_completadas_semana,
                'porcentaje_semanal': porcentaje_semanal,
                'dias_con_actividad': dias_con_actividad,
                'dias_perfectos': dias_perfectos,
                'mejor_dia': mejor_dia,
                'racha_dias': racha_maxima,
                'promedio_diario': promedio_diario
            }
            
            # Datos para la gráfica de columnas (solo tareas completadas)
            grafica_datos = []
            max_completadas = 0
            for dia in progreso_dias:
                completadas = dia['tareas_completadas']
                if completadas > max_completadas:
                    max_completadas = completadas
                
                grafica_datos.append({
                    'dia': dia['nombre_dia'][:3],  # Lun, Mar, Mie, etc.
                    'completadas': completadas,
                    'fecha': dia['fecha'],
                    'es_hoy': dia['es_hoy'],
                    'es_futuro': False  # En registros históricos no hay días futuros
                })
            
            # Calcular altura máxima para normalizar las columnas (mínimo 5 para que se vea bien)
            altura_maxima = max(max_completadas, 5) if max_completadas > 0 else 5
        
        conn.close()
        
    except Exception as e:
        print("⚠️ Error en /registros_actividades:", e)
        flash('Error al cargar los registros', 'danger')
        progreso_dias = []
        grafica_datos = []
        altura_maxima = 5
        max_offset = 0  # Si hay error, no permitir navegación
        semana_actual = {
            'offset': semana_offset,
            'max_offset': max_offset,
            'es_actual': semana_offset == 0,
            'fecha_inicio': 'N/A',
            'fecha_fin': 'N/A',
            'total_tareas': 0,
            'tareas_completadas': 0,
            'porcentaje_semanal': 0,
            'dias_con_actividad': 0,
            'dias_perfectos': 0,
            'mejor_dia': {'porcentaje': 0, 'nombre': 'N/A'},
            'racha_dias': 0,
            'promedio_diario': 0
        }

    return render_template('registros_actividades.html', 
                         progreso_dias=progreso_dias,
                         semana_actual=semana_actual,
                         grafica_datos=grafica_datos,
                         altura_maxima=altura_maxima,
                         usuario=usuario)


@app.route('/debug/streak')
def debug_streak():
    """Ruta de debug para verificar el estado de las rachas"""
    if 'user_email' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    usuario = get_user_by_email(session['user_email'])
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    try:
        if debug_streak_status is not None:
            status = debug_streak_status(usuario['id'])
            return jsonify(status)
        else:
            return jsonify({'error': 'Función de debug no disponible'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
