from flask import Flask, Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
import os
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
import pymysql
from models.db import get_db_connection

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'evinava8@gmail.com')
# WARNING: default password below is for local/dev use only. Override via ADMIN_PASSWORD env var.
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin123!')

def create_admin_app():
    app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), static_folder=os.path.join(BASE_DIR, 'static'))
    app.secret_key = os.environ.get('FLASK_ADMIN_SECRET', 'admin-secret-dev')

    # admin upload folder
    app.config['ADMIN_UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'img', 'admin_avatars')
    os.makedirs(app.config['ADMIN_UPLOAD_FOLDER'], exist_ok=True)

    # register local admin blueprint implemented below
    try:
        app.register_blueprint(admin_bp)
    except Exception as e:
        print('Error registering admin blueprint (internal):', e)

    # Convenience root route when running admin_app standalone
    @app.route('/')
    def _admin_root_redirect():
        # Redirect to dashboard if already logged in, otherwise to login
        if 'admin_email' in session:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('admin.login'))

    # initialize DB for admin app (safe schema initialization only)
    try:
        from models.db import init_db_schema_only
        init_db_schema_only()
    except Exception as e:
        print('Admin app DB schema init warning:', e)

    return app


# --- Admin blueprint implementation ---
admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder=os.path.join(BASE_DIR, 'templates', 'admin'))


def generate_token(email):
    s = URLSafeTimedSerializer(os.environ.get('FLASK_ADMIN_SECRET', 'admin-secret-dev'))
    return s.dumps(email, salt='admin-password-salt')


def confirm_token(token, expiration=3600):
    s = URLSafeTimedSerializer(os.environ.get('FLASK_ADMIN_SECRET', 'admin-secret-dev'))
    try:
        email = s.loads(token, salt='admin-password-salt', max_age=expiration)
        return email
    except Exception:
        return None


def send_email(to_email, subject, body):
    # Dev email: print to console
    try:
        print('--- ADMIN SEND EMAIL ---')
        print('To:', to_email)
        print('Subject:', subject)
        print(body)
        print('------------------------')
        return True
    except Exception as e:
        print('send_email error:', e)
        return False


def admin_login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'admin_email' not in session:
            flash('Debes iniciar sesión como administrador', 'warning')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return wrapper


def get_global_statistics(filtro_tipo=None, periodo='mes'):
    """Obtiene estadísticas globales detalladas de la aplicación"""
    from datetime import datetime, timedelta
    import calendar
    
    stats = {
        'usuarios_activos': 0,
        'usuarios_totales': 0,
        'rutinas_creadas': 0,
        'rutinas_ejercicio': 0,
        'rutinas_estudio': 0,
        'actividades_completadas': 0,
        'actividades_ejercicio': 0,
        'actividades_estudio': 0,
        'uso_por_periodo': [],
        'actividades_por_tipo': [],
        'crecimiento_usuarios': [],
        'rutinas_mas_populares': [],
        'usuarios_mas_activos': []
    }
    
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Definir el filtro de período
            if periodo == 'semana':
                fecha_filtro = 'DATE_SUB(NOW(), INTERVAL 7 DAY)'
                grupo_fecha = 'DATE(fecha)'
                grupo_fecha_usuarios = 'DATE(fecha_creacion)'
            elif periodo == 'mes':
                fecha_filtro = 'DATE_SUB(NOW(), INTERVAL 30 DAY)'
                grupo_fecha = 'DATE(fecha)'
                grupo_fecha_usuarios = 'DATE(fecha_creacion)'
            else:  # año
                fecha_filtro = 'DATE_SUB(NOW(), INTERVAL 365 DAY)'
                grupo_fecha = 'DATE_FORMAT(fecha, "%Y-%m")'
                grupo_fecha_usuarios = 'DATE_FORMAT(fecha_creacion, "%Y-%m")'
            
            # Usuarios totales y activos
            try:
                cur.execute('SELECT COUNT(*) AS total FROM usuario')
                stats['usuarios_totales'] = cur.fetchone().get('total', 0)
                
                cur.execute(f'SELECT COUNT(*) AS total FROM usuario WHERE fecha_creacion >= {fecha_filtro}')
                stats['usuarios_activos'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error usuarios: {e}')
            
            # Rutinas creadas (filtradas por tipo si se especifica)
            try:
                if filtro_tipo == 'ejercicio':
                    cur.execute('SELECT COUNT(*) AS total FROM rutina WHERE tipo = "ejercicio"')
                    stats['rutinas_creadas'] = cur.fetchone().get('total', 0)
                elif filtro_tipo == 'estudio':
                    cur.execute('SELECT COUNT(*) AS total FROM rutina WHERE tipo = "estudio"')
                    stats['rutinas_creadas'] = cur.fetchone().get('total', 0)
                else:
                    cur.execute('SELECT COUNT(*) AS total FROM rutina')
                    stats['rutinas_creadas'] = cur.fetchone().get('total', 0)
                
                # Rutinas por tipo
                cur.execute('SELECT COUNT(*) AS total FROM rutina WHERE tipo = "ejercicio"')
                stats['rutinas_ejercicio'] = cur.fetchone().get('total', 0)
                
                cur.execute('SELECT COUNT(*) AS total FROM rutina WHERE tipo = "estudio"')
                stats['rutinas_estudio'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error rutinas: {e}')
            
            # Actividades completadas (usando item_diario)
            try:
                if filtro_tipo == 'ejercicio':
                    cur.execute('''
                        SELECT COUNT(*) AS total 
                        FROM item_diario id 
                        JOIN rutina_item ri ON id.id_item = ri.id_item 
                        JOIN rutina r ON ri.id_rutina = r.id_rutina 
                        WHERE r.tipo = "ejercicio" AND id.completado = 1
                    ''')
                    stats['actividades_completadas'] = cur.fetchone().get('total', 0)
                elif filtro_tipo == 'estudio':
                    cur.execute('''
                        SELECT COUNT(*) AS total 
                        FROM item_diario id 
                        JOIN rutina_item ri ON id.id_item = ri.id_item 
                        JOIN rutina r ON ri.id_rutina = r.id_rutina 
                        WHERE r.tipo = "estudio" AND id.completado = 1
                    ''')
                    stats['actividades_completadas'] = cur.fetchone().get('total', 0)
                else:
                    cur.execute('SELECT COUNT(*) AS total FROM item_diario WHERE completado = 1')
                    stats['actividades_completadas'] = cur.fetchone().get('total', 0)
                
                # Actividades por tipo
                cur.execute('''
                    SELECT COUNT(*) AS total 
                    FROM item_diario id 
                    JOIN rutina_item ri ON id.id_item = ri.id_item 
                    JOIN rutina r ON ri.id_rutina = r.id_rutina 
                    WHERE r.tipo = "ejercicio" AND id.completado = 1
                ''')
                stats['actividades_ejercicio'] = cur.fetchone().get('total', 0)
                
                cur.execute('''
                    SELECT COUNT(*) AS total 
                    FROM item_diario id 
                    JOIN rutina_item ri ON id.id_item = ri.id_item 
                    JOIN rutina r ON ri.id_rutina = r.id_rutina 
                    WHERE r.tipo = "estudio" AND id.completado = 1
                ''')
                stats['actividades_estudio'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error actividades: {e}')
            
            # Uso por período
            try:
                query = f'''
                SELECT {grupo_fecha} as fecha, COUNT(*) as actividades
                FROM item_diario 
                WHERE fecha >= {fecha_filtro} AND completado = 1
                GROUP BY {grupo_fecha}
                ORDER BY fecha
                '''
                cur.execute(query)
                uso_data = cur.fetchall() or []
                stats['uso_por_periodo'] = uso_data
            except Exception as e:
                print(f'Error uso por período: {e}')
                stats['uso_por_periodo'] = []
            
            # Actividades por tipo para gráfico
            try:
                cur.execute('''
                SELECT r.tipo, COUNT(*) as total
                FROM item_diario id
                JOIN rutina_item ri ON id.id_item = ri.id_item 
                JOIN rutina r ON ri.id_rutina = r.id_rutina 
                WHERE id.completado = 1
                GROUP BY r.tipo
                ''')
                tipo_data = cur.fetchall() or []
                
                if tipo_data:
                    # Convertir a formato esperado por el frontend
                    tipo_data = [{'tipo_actividad': row.get('tipo', 'sin_tipo'), 'total': row.get('total', 0)} for row in tipo_data]
                else:
                    tipo_data = []
                
                stats['actividades_por_tipo'] = tipo_data
                print(f'Actividades por tipo: {tipo_data}')
            except Exception as e:
                print(f'Error actividades por tipo: {e}')
                stats['actividades_por_tipo'] = []
            
            # Crecimiento de usuarios por período
            try:
                query = f'''
                SELECT {grupo_fecha_usuarios} as fecha, COUNT(*) as nuevos_usuarios
                FROM usuario 
                WHERE fecha_creacion >= {fecha_filtro}
                GROUP BY {grupo_fecha_usuarios}
                ORDER BY fecha
                '''
                cur.execute(query)
                crecimiento_data = cur.fetchall() or []
                stats['crecimiento_usuarios'] = crecimiento_data
            except Exception as e:
                print(f'Error crecimiento usuarios: {e}')
                stats['crecimiento_usuarios'] = []
            
            # Rutinas más populares
            try:
                cur.execute('''
                SELECT r.nombre, r.tipo, COUNT(id.id) as usos
                FROM rutina r
                LEFT JOIN rutina_item ri ON r.id_rutina = ri.id_rutina
                LEFT JOIN item_diario id ON ri.id_item = id.id_item
                WHERE id.completado = 1
                GROUP BY r.id_rutina, r.nombre, r.tipo
                ORDER BY usos DESC
                LIMIT 10
                ''')
                stats['rutinas_mas_populares'] = cur.fetchall() or []
            except Exception as e:
                print(f'Error rutinas populares: {e}')
            
            # Usuarios más activos
            try:
                cur.execute('''
                SELECT u.nombre, COUNT(id.id) as actividades_completadas
                FROM usuario u
                LEFT JOIN item_diario id ON u.id = id.id_usuario
                WHERE id.completado = 1
                GROUP BY u.id, u.nombre
                ORDER BY actividades_completadas DESC
                LIMIT 10
                ''')
                stats['usuarios_mas_activos'] = cur.fetchall() or []
            except Exception as e:
                print(f'Error usuarios activos: {e}')
        
        conn.close()
    except Exception as e:
        print('get_global_statistics error:', e)
    
    return stats


def get_admin_stats():
    stats = {
        'usuarios': 0, 
        'rutinas_publicas': 0, 
        'notificaciones': 0, 
        'publicaciones_pendientes': 0, 
        'recomendaciones_publicas': 0,
        'total_rutinas': 0,
        'total_recomendaciones': 0,
        'publicaciones_aprobadas': 0,
        'usuarios_activos_mes': 0,
        'contenido_admin': 0
    }
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Usuarios totales
            cur.execute('SELECT COUNT(*) AS total FROM usuario')
            stats['usuarios'] = cur.fetchone().get('total', 0)
            
            # Rutinas públicas (tipo 'compartida') y totales
            try:
                cur.execute("SELECT COUNT(*) AS total FROM rutina WHERE tipo = 'compartida'")
                stats['rutinas_publicas'] = cur.fetchone().get('total', 0)
                cur.execute('SELECT COUNT(*) AS total FROM rutina')
                stats['total_rutinas'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error rutinas: {e}')
                stats['rutinas_publicas'] = 0
                stats['total_rutinas'] = 0
            
            # Notificaciones no leídas
            try:
                cur.execute('SELECT COUNT(*) AS total FROM user_notifications WHERE is_read = 0')
                stats['notificaciones'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error notificaciones: {e}')
                stats['notificaciones'] = 0
            
            # Publicaciones de comunidad (posts de usuarios)
            try:
                cur.execute('SELECT COUNT(*) AS total FROM community_posts WHERE approved = 0')
                stats['publicaciones_pendientes'] = cur.fetchone().get('total', 0)
                cur.execute('SELECT COUNT(*) AS total FROM community_posts WHERE approved = 1')
                stats['publicaciones_aprobadas'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error community_posts: {e}')
                stats['publicaciones_pendientes'] = 0
                stats['publicaciones_aprobadas'] = 0
            
            # Recomendaciones
            try:
                cur.execute('SELECT COUNT(*) AS total FROM recommendations WHERE is_public = 1')
                stats['recomendaciones_publicas'] = cur.fetchone().get('total', 0)
                cur.execute('SELECT COUNT(*) AS total FROM recommendations')
                stats['total_recomendaciones'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error recommendations: {e}')
                stats['recomendaciones_publicas'] = 0
                stats['total_recomendaciones'] = 0
            
            # Contenido administrativo
            try:
                cur.execute('SELECT COUNT(*) AS total FROM contenido_admin')
                stats['contenido_admin'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error contenido_admin: {e}')
                stats['contenido_admin'] = 0
            
            # Usuarios activos en el último mes (aproximado)
            try:
                cur.execute('SELECT COUNT(*) AS total FROM usuario WHERE fecha_creacion >= DATE_SUB(NOW(), INTERVAL 30 DAY)')
                stats['usuarios_activos_mes'] = cur.fetchone().get('total', 0)
            except Exception as e:
                print(f'Error usuarios activos: {e}')
                stats['usuarios_activos_mes'] = 0
                
        conn.close()
    except Exception as e:
        print('get_admin_stats error:', e)
    return stats


def list_admin_content(content_type='rutina_destacada'):
    items = []
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT * FROM contenido_admin WHERE tipo_contenido = %s ORDER BY actualizado_en DESC', (content_type,))
            items = cur.fetchall() or []
        conn.close()
    except Exception as e:
        print('list_admin_content error:', e)
    return items


def get_notifications(limit=200):
    notes = []
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT id, title, message, fecha_programada, is_read FROM user_notifications ORDER BY fecha_programada DESC LIMIT %s', (limit,))
            notes = cur.fetchall() or []
        conn.close()
    except Exception as e:
        print('get_notifications error:', e)
    return notes


def mark_notification_read(nid):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('UPDATE user_notifications SET is_read = 1 WHERE id = %s', (nid,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print('mark_notification_read error:', e)
        return False


@admin_bp.context_processor
def inject_admin_sidebar():
    admin_sidebar = [
        {'text': 'Dashboard', 'href': url_for('admin.dashboard')},
        {'text': 'Gestión de contenido', 'href': url_for('admin.content_manager')},
        {'text': 'Comunidad', 'href': url_for('admin.admin_community_posts')},
        {'text': 'Recomendaciones', 'href': url_for('admin.recommendations')},
        {'text': 'Estadísticas globales', 'href': url_for('admin.global_statistics')},
        {'text': 'Perfil', 'href': url_for('admin.perfil')},
    ]
    unread = 0
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT COUNT(*) AS total FROM user_notifications WHERE is_read = 0')
            row = cur.fetchone()
            unread = int(row.get('total', 0)) if row else 0
        conn.close()
    except Exception:
        unread = 0
    return dict(admin_sidebar=admin_sidebar, admin_unread_notifications=unread)


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo')
        password = request.form.get('password')
        if not correo or not password:
            flash('Completa todos los campos.', 'warning')
            return redirect(url_for('admin.login'))
        admin_row = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute('SELECT id, email, password FROM admin WHERE email = %s LIMIT 1', (correo,))
                admin_row = cur.fetchone()
            conn.close()
        except Exception:
            admin_row = None
        if not admin_row:
            # fallback to configured default admin
            env_email = DEFAULT_ADMIN_EMAIL
            env_pass = DEFAULT_ADMIN_PASSWORD
            if env_email and env_pass and correo == env_email and password == env_pass:
                session['admin_email'] = correo
                session['admin_id'] = 'env-admin'
                flash('Sesión iniciada (admin env).', 'success')
                return redirect(url_for('admin.dashboard'))
            flash('Credenciales inválidas.', 'danger')
            return redirect(url_for('admin.login'))
        stored = admin_row[2] if isinstance(admin_row, (list, tuple)) else admin_row.get('password')
        ok = False
        try:
            ok = check_password_hash(stored, password)
        except Exception:
            ok = (stored == password)
        if not ok:
            flash('Contraseña incorrecta.', 'danger')
            return redirect(url_for('admin.login'))
        session['admin_email'] = admin_row[1] if isinstance(admin_row, (list, tuple)) else admin_row.get('email')
        session['admin_id'] = admin_row[0] if isinstance(admin_row, (list, tuple)) else admin_row.get('id')
        flash('Sesión de administrador iniciada.', 'success')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/admin_login.html')


@admin_bp.route('/logout')
def logout():
    session.pop('admin_email', None)
    session.pop('admin_id', None)
    flash('Sesión de administrador cerrada.', 'info')
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@admin_login_required
def dashboard():
    stats = get_admin_stats()
    recent_activity = get_recent_activity()
    return render_template('admin/admin_dashboard.html', stats=stats, recent_activity=recent_activity)


def get_recent_activity():
    """Obtiene actividad reciente del sistema"""
    activity = {
        'recent_users': [],
        'recent_recommendations': [],
        'recent_posts': [],
        'recent_routines': []
    }
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Usuarios recientes (últimos 5)
            try:
                cur.execute('''
                    SELECT id, nombre, apellido, fecha_creacion 
                    FROM usuario 
                    ORDER BY fecha_creacion DESC 
                    LIMIT 5
                ''')
                activity['recent_users'] = cur.fetchall() or []
            except Exception as e:
                print(f'Error recent_users: {e}')
                pass
            
            # Recomendaciones recientes (últimas 5)
            try:
                cur.execute('''
                    SELECT id, title, created_at, difficulty, is_public 
                    FROM recommendations 
                    ORDER BY created_at DESC 
                    LIMIT 5
                ''')
                activity['recent_recommendations'] = cur.fetchall() or []
            except Exception as e:
                print(f'Error recent_recommendations: {e}')
                pass
            
            # Posts de comunidad recientes (últimos 5)
            try:
                cur.execute('''
                    SELECT id, title, created_at, approved, user_id 
                    FROM community_posts 
                    ORDER BY created_at DESC 
                    LIMIT 5
                ''')
                activity['recent_posts'] = cur.fetchall() or []
            except Exception as e:
                print(f'Error recent_posts: {e}')
                pass
            
            # Rutinas recientes (últimas 5)
            try:
                cur.execute('''
                    SELECT id_rutina as id, nombre, fecha_creacion, tipo, id_usuario as user_id 
                    FROM rutina 
                    ORDER BY fecha_creacion DESC 
                    LIMIT 5
                ''')
                activity['recent_routines'] = cur.fetchall() or []
            except Exception as e:
                print(f'Error recent_routines: {e}')
                pass
                
        conn.close()
    except Exception as e:
        print('get_recent_activity error:', e)
    
    return activity


@admin_bp.route('/content', methods=['GET', 'POST'])
@admin_login_required
def content_manager():
    requested = request.args.get('type', 'rutina_destacada')
    mapping = {
        'routines': 'rutina_destacada', 'routines_public': 'rutina_destacada', 'rutines': 'rutina_destacada',
        'sections': 'ayuda', 'sections_info': 'ayuda', 'messages': 'message',
        'banners': 'banner', 'community': 'community', 'recommendation': 'recommendation'
    }
    ctype = mapping.get(requested, requested)
    
    # Solo permitir creación para tipos que no sean recommendation
    if request.method == 'POST' and ctype != 'recommendation':
        title = request.form.get('title')
        body = request.form.get('body') or request.form.get('summary') or ''
        is_public = 1 if request.form.get('is_public') in ('1', 'on', 'true') else 0
        image = request.files.get('image')
        image_name = None
        if image and image.filename:
            ext = os.path.splitext(secure_filename(image.filename))[1].lower()
            image_name = f"{uuid.uuid4().hex}{ext}"
            save_path = os.path.join(current_app.config.get('ADMIN_UPLOAD_FOLDER'), image_name)
            image.save(save_path)
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute('INSERT INTO contenido_admin (tipo_contenido, titulo, texto, url_imagen, actualizado_por, actualizado_en) VALUES (%s,%s,%s,%s,%s,%s)', (ctype, title, body, image_name, session.get('admin_id'), datetime.now()))
            conn.commit()
            conn.close()
            flash('Contenido creado.', 'success')
        except Exception as e:
            flash(f'Error creando contenido: {e}', 'danger')
        return redirect(url_for('admin.content_manager', type=ctype))
    elif request.method == 'POST' and ctype == 'recommendation':
        flash('No se pueden crear recomendaciones desde el panel de administración.', 'warning')
        return redirect(url_for('admin.content_manager', type=ctype))
        
    # load items either from contenido_admin or recommendations
    items = []
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if ctype == 'recommendation':
                cur.execute('SELECT * FROM recommendations ORDER BY created_at DESC')
                items = cur.fetchall() or []
            else:
                cur.execute('SELECT * FROM contenido_admin WHERE tipo_contenido = %s ORDER BY actualizado_en DESC', (ctype,))
                items = cur.fetchall() or []
        conn.close()
    except Exception as e:
        print('content_manager load error', e)
    return render_template('admin/admin_content_manager.html', items=items, type=ctype)


@admin_bp.route('/content/delete/<int:item_id>', methods=['POST'])
@admin_login_required
def content_delete(item_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Primero verificar si existe en recommendations
            cur.execute('SELECT id FROM recommendations WHERE id = %s', (item_id,))
            if cur.fetchone():
                cur.execute('DELETE FROM recommendations WHERE id = %s', (item_id,))
                flash('Recomendación eliminada.', 'success')
            else:
                # Si no está en recommendations, intentar con contenido_admin
                cur.execute('DELETE FROM contenido_admin WHERE id = %s', (item_id,))
                flash('Contenido eliminado.', 'success')
        conn.commit()
        conn.close()
    except Exception as e:
        flash(f'Error al eliminar contenido: {e}', 'danger')
    return redirect(request.referrer or url_for('admin.content_manager'))


@admin_bp.route('/community')
@admin_login_required
def community():
    posts = list_admin_content('community')
    return render_template('admin/admin_community.html', posts=posts)


@admin_bp.route('/community_posts')
@admin_login_required
def admin_community_posts():
    # list pending community posts from users
    posts = []
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT cp.id, cp.user_id, u.nombre as user_name, cp.rutina_id, cp.title, cp.summary, cp.image, cp.is_recommendation, cp.approved, cp.created_at FROM community_posts cp LEFT JOIN usuario u ON cp.user_id = u.id ORDER BY cp.created_at DESC')
            posts = cur.fetchall() or []
        conn.close()
    except Exception as e:
        print('admin_community_posts error', e)
    return render_template('admin/admin_community.html', posts=posts)


@admin_bp.route('/community_posts/approve/<int:post_id>', methods=['POST'])
@admin_login_required
def admin_approve_post(post_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('UPDATE community_posts SET approved = 1 WHERE id = %s', (post_id,))
        conn.commit()
        conn.close()
        flash('Publicación aprobada', 'success')
    except Exception as e:
        flash(f'Error al aprobar publicación: {e}', 'danger')
    return redirect(request.referrer or url_for('admin.admin_community_posts'))


@admin_bp.route('/community_posts/delete/<int:post_id>', methods=['POST'])
@admin_login_required
def admin_delete_post(post_id):
    motivo = request.form.get('motivo', 'Violación de normas de la comunidad')
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Obtener información de la publicación antes de eliminarla
            cur.execute('SELECT cp.title, cp.user_id, u.nombre as user_name FROM community_posts cp LEFT JOIN usuario u ON cp.user_id = u.id WHERE cp.id = %s', (post_id,))
            post_info = cur.fetchone()
            
            if post_info:
                # Eliminar la publicación
                cur.execute('DELETE FROM community_posts WHERE id = %s', (post_id,))
                
                # Opcional: Enviar notificación al usuario sobre la eliminación
                try:
                    cur.execute('INSERT INTO user_notifications (user_id, title, message, fecha_programada, is_read) VALUES (%s, %s, %s, %s, %s)', 
                              (post_info['user_id'], 
                               'Publicación eliminada', 
                               f'Tu publicación "{post_info["title"]}" ha sido eliminada por: {motivo}',
                               datetime.now(),
                               0))
                except Exception as e:
                    print(f'Error enviando notificación: {e}')
                
                flash(f'Publicación de {post_info["user_name"]} eliminada por: {motivo}', 'success')
            else:
                flash('Publicación no encontrada.', 'warning')
        conn.commit()
        conn.close()
    except Exception as e:
        flash(f'Error al eliminar publicación: {e}', 'danger')
    return redirect(request.referrer or url_for('admin.admin_community_posts'))


@admin_bp.route('/recommendations/delete/<int:recommendation_id>', methods=['POST'])
@admin_login_required
def delete_recommendation(recommendation_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Verificar si la recomendación existe antes de eliminarla
            cur.execute('SELECT title FROM recommendations WHERE id = %s', (recommendation_id,))
            rec = cur.fetchone()
            if rec:
                cur.execute('DELETE FROM recommendations WHERE id = %s', (recommendation_id,))
                conn.commit()
                flash(f'Recomendación "{rec[0] if isinstance(rec, tuple) else rec.get("title", "")}" eliminada por violación de normas.', 'success')
            else:
                flash('Recomendación no encontrada.', 'warning')
        conn.close()
    except Exception as e:
        flash(f'Error al eliminar recomendación: {e}', 'danger')
    return redirect(request.referrer or url_for('admin.recommendations'))


@admin_bp.route('/recommendations')
@admin_login_required
def recommendations():
    # Load recommendations directly for the new modern interface
    items = []
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT * FROM recommendations ORDER BY created_at DESC')
            items = cur.fetchall() or []
        conn.close()
    except Exception as e:
        print('recommendations load error', e)
        items = []
    
    return render_template('admin/admin_recommendations.html', items=items)


@admin_bp.route('/messages')
@admin_login_required
def messages():
    msgs = list_admin_content('message')
    return render_template('admin/admin_messages.html', messages=msgs)


@admin_bp.route('/banners')
@admin_login_required
def banners():
    banners = list_admin_content('banner')
    return render_template('admin/admin_banners.html', banners=banners)


@admin_bp.route('/notifications')
@admin_login_required
def notifications():
    notes = get_notifications()
    return jsonify(notes)


@admin_bp.route('/notifications/mark', methods=['POST'])
@admin_login_required
def notifications_mark():
    data = request.get_json(silent=True) or {}
    nid = data.get('id')
    if not nid:
        return jsonify({'ok': False}), 400
    ok = mark_notification_read(nid)
    return jsonify({'ok': ok})


@admin_bp.route('/recover', methods=['GET', 'POST'])
def recover():
    # Recovery disabled for now per request: redirect to login so admin can use the default credentials
    flash('Recuperación temporalmente deshabilitada. Usa las credenciales configuradas.', 'info')
    return redirect(url_for('admin.login'))


@admin_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Password reset flow disabled while using fixed admin credentials
    flash('Restablecimiento de contraseña deshabilitado. Contacta al administrador del sistema.', 'warning')
    return redirect(url_for('admin.login'))


@admin_bp.route('/global-statistics')
@admin_login_required
def global_statistics():
    # Obtener parámetros de filtro
    filtro_tipo = request.args.get('tipo', None)  # 'ejercicio', 'estudio', o None para todos
    periodo = request.args.get('periodo', 'mes')  # 'semana', 'mes', 'año'
    formato_export = request.args.get('export', None)  # 'csv', 'pdf', o None
    
    # Obtener estadísticas
    stats = get_global_statistics(filtro_tipo, periodo)
    
    # Si se solicita exportación
    if formato_export == 'csv':
        return export_statistics_csv(stats, filtro_tipo, periodo)
    elif formato_export == 'pdf':
        return export_statistics_pdf(stats, filtro_tipo, periodo)
    
    return render_template('admin/admin_global_statistics.html', 
                         stats=stats, 
                         filtro_tipo=filtro_tipo, 
                         periodo=periodo)


def export_statistics_csv(stats, filtro_tipo, periodo):
    """Exporta las estadísticas en formato CSV con estructura mejorada"""
    import csv
    import io
    from flask import make_response
    from datetime import datetime
    
    # Usar StringIO con encoding específico
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Información del reporte
    writer.writerow(['ESTADISTICAS GLOBALES FOCUSFIT'])
    writer.writerow([])
    writer.writerow(['Informacion del Reporte'])
    writer.writerow(['Filtro de tipo', filtro_tipo or 'Todos'])
    writer.writerow(['Periodo', periodo])
    writer.writerow(['Fecha de exportacion', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    
    # Estadísticas principales
    writer.writerow(['ESTADISTICAS PRINCIPALES'])
    writer.writerow(['Metrica', 'Valor'])
    writer.writerow(['Usuarios totales', stats.get('usuarios_totales', 0)])
    writer.writerow(['Usuarios activos', stats.get('usuarios_activos', 0)])
    writer.writerow(['Rutinas creadas', stats.get('rutinas_creadas', 0)])
    writer.writerow(['Rutinas de ejercicio', stats.get('rutinas_ejercicio', 0)])
    writer.writerow(['Rutinas de estudio', stats.get('rutinas_estudio', 0)])
    writer.writerow(['Actividades completadas', stats.get('actividades_completadas', 0)])
    writer.writerow(['Actividades de ejercicio', stats.get('actividades_ejercicio', 0)])
    writer.writerow(['Actividades de estudio', stats.get('actividades_estudio', 0)])
    writer.writerow([])
    
    # Uso por período (solo si hay datos)
    uso_data = stats.get('uso_por_periodo', [])
    if uso_data:
        writer.writerow(['USO POR PERIODO'])
        writer.writerow(['Fecha', 'Actividades Completadas'])
        for item in uso_data:
            try:
                fecha = item.get('fecha', 'N/A') if isinstance(item, dict) else getattr(item, 'fecha', 'N/A')
                actividades = item.get('actividades', 0) if isinstance(item, dict) else getattr(item, 'actividades', 0)
                # Asegurar que fecha sea string
                fecha_str = str(fecha) if fecha else 'N/A'
                writer.writerow([fecha_str, actividades])
            except Exception as e:
                print(f"Error procesando uso por periodo: {e}")
                continue
        writer.writerow([])
    
    # Actividades por tipo (solo si hay datos)
    tipo_data = stats.get('actividades_por_tipo', [])
    if tipo_data:
        writer.writerow(['ACTIVIDADES POR TIPO'])
        writer.writerow(['Tipo de Actividad', 'Total Completadas'])
        for item in tipo_data:
            try:
                tipo = item.get('tipo_actividad', 'N/A') if isinstance(item, dict) else getattr(item, 'tipo_actividad', 'N/A')
                total = item.get('total', 0) if isinstance(item, dict) else getattr(item, 'total', 0)
                # Asegurar que tipo sea string sin caracteres especiales
                tipo_str = str(tipo).replace('ñ', 'n').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u') if tipo else 'N/A'
                writer.writerow([tipo_str, total])
            except Exception as e:
                print(f"Error procesando actividades por tipo: {e}")
                continue
        writer.writerow([])
    
    # Rutinas más populares (solo si hay datos)
    rutinas_data = stats.get('rutinas_mas_populares', [])
    if rutinas_data:
        writer.writerow(['RUTINAS MAS POPULARES'])
        writer.writerow(['Nombre de la Rutina', 'Tipo', 'Numero de Usos'])
        for rutina in rutinas_data:
            try:
                nombre = rutina.get('nombre', 'N/A') if isinstance(rutina, dict) else getattr(rutina, 'nombre', 'N/A')
                tipo = rutina.get('tipo', 'N/A') if isinstance(rutina, dict) else getattr(rutina, 'tipo', 'N/A')
                usos = rutina.get('usos', 0) if isinstance(rutina, dict) else getattr(rutina, 'usos', 0)
                
                # Limpiar strings de caracteres especiales
                nombre_str = str(nombre).replace('ñ', 'n').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u') if nombre else 'N/A'
                tipo_str = str(tipo).replace('ñ', 'n').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u') if tipo else 'N/A'
                
                writer.writerow([nombre_str, tipo_str, usos])
            except Exception as e:
                print(f"Error procesando rutinas populares: {e}")
                continue
        writer.writerow([])
    
    # Usuarios más activos (solo si hay datos)
    usuarios_data = stats.get('usuarios_mas_activos', [])
    if usuarios_data:
        writer.writerow(['USUARIOS MAS ACTIVOS'])
        writer.writerow(['Nombre', 'Apellido', 'Actividades Completadas'])
        for usuario in usuarios_data:
            try:
                nombre = usuario.get('nombre', 'N/A') if isinstance(usuario, dict) else getattr(usuario, 'nombre', 'N/A')
                apellido = usuario.get('apellido', 'N/A') if isinstance(usuario, dict) else getattr(usuario, 'apellido', 'N/A')
                actividades = usuario.get('actividades_completadas', 0) if isinstance(usuario, dict) else getattr(usuario, 'actividades_completadas', 0)
                
                # Limpiar strings de caracteres especiales
                nombre_str = str(nombre).replace('ñ', 'n').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u') if nombre else 'N/A'
                apellido_str = str(apellido).replace('ñ', 'n').replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u') if apellido else 'N/A'
                
                writer.writerow([nombre_str, apellido_str, actividades])
            except Exception as e:
                print(f"Error procesando usuarios activos: {e}")
                continue
        writer.writerow([])
    
    # Pie de archivo
    writer.writerow([])
    writer.writerow(['FIN DEL REPORTE'])
    writer.writerow(['Generado por FocusFit Admin Panel'])
    
    # Crear respuesta con encoding correcto
    csv_content = output.getvalue()
    
    # Crear respuesta
    response = make_response(csv_content.encode('utf-8'))
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=estadisticas_focusfit_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    return response


def export_statistics_pdf(stats, filtro_tipo, periodo):
    """Exporta las estadísticas en formato PDF"""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from datetime import datetime
        import io
        from flask import make_response
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.5*inch, rightMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        # Título
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.darkblue,
            alignment=1  # Centrado
        )
        story.append(Paragraph("📊 Estadísticas Globales FocusFit", title_style))
        story.append(Spacer(1, 20))
        
        # Información del reporte
        info_style = styles['Normal']
        story.append(Paragraph(f"<b>Filtro de tipo:</b> {filtro_tipo or 'Todos'}", info_style))
        story.append(Paragraph(f"<b>Período:</b> {periodo}", info_style))
        story.append(Paragraph(f"<b>Fecha de exportación:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", info_style))
        story.append(Spacer(1, 30))
        
        # Estadísticas principales
        story.append(Paragraph("📈 Estadísticas Principales", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        data = [
            ['Estadística', 'Valor'],
            ['Usuarios totales', str(stats.get('usuarios_totales', 0))],
            ['Usuarios activos', str(stats.get('usuarios_activos', 0))],
            ['Rutinas creadas', str(stats.get('rutinas_creadas', 0))],
            ['Rutinas de ejercicio', str(stats.get('rutinas_ejercicio', 0))],
            ['Rutinas de estudio', str(stats.get('rutinas_estudio', 0))],
            ['Actividades completadas', str(stats.get('actividades_completadas', 0))],
            ['Actividades de ejercicio', str(stats.get('actividades_ejercicio', 0))],
            ['Actividades de estudio', str(stats.get('actividades_estudio', 0))],
        ]
        
        table = Table(data, colWidths=[3*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        story.append(Spacer(1, 30))
        
        # Uso por período
        uso_data = stats.get('uso_por_periodo', [])
        if uso_data:
            story.append(Paragraph("📅 Uso por Período", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            uso_table_data = [['Fecha', 'Actividades']]
            for item in uso_data[:10]:  # Limitar a 10 elementos
                fecha = item.get('fecha', 'N/A') if isinstance(item, dict) else getattr(item, 'fecha', 'N/A')
                actividades = item.get('actividades', 0) if isinstance(item, dict) else getattr(item, 'actividades', 0)
                uso_table_data.append([str(fecha), str(actividades)])
            
            uso_table = Table(uso_table_data, colWidths=[2*inch, 1.5*inch])
            uso_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(uso_table)
            story.append(Spacer(1, 20))
        
        # Actividades por tipo
        tipo_data = stats.get('actividades_por_tipo', [])
        if tipo_data:
            story.append(Paragraph("🎯 Actividades por Tipo", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            tipo_table_data = [['Tipo', 'Total']]
            for item in tipo_data:
                tipo = item.get('tipo_actividad', 'N/A') if isinstance(item, dict) else getattr(item, 'tipo_actividad', 'N/A')
                total = item.get('total', 0) if isinstance(item, dict) else getattr(item, 'total', 0)
                tipo_table_data.append([str(tipo), str(total)])
            
            tipo_table = Table(tipo_table_data, colWidths=[2*inch, 1.5*inch])
            tipo_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.orange),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(tipo_table)
            story.append(Spacer(1, 20))
        
        # Rutinas más populares
        rutinas_data = stats.get('rutinas_mas_populares', [])
        if rutinas_data:
            story.append(Paragraph("🏆 Rutinas Más Populares", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            rutinas_table_data = [['Nombre', 'Tipo', 'Usos']]
            for rutina in rutinas_data[:10]:  # Limitar a 10 elementos
                nombre = rutina.get('nombre', 'N/A') if isinstance(rutina, dict) else getattr(rutina, 'nombre', 'N/A')
                tipo = rutina.get('tipo', 'N/A') if isinstance(rutina, dict) else getattr(rutina, 'tipo', 'N/A')
                usos = rutina.get('usos', 0) if isinstance(rutina, dict) else getattr(rutina, 'usos', 0)
                # Truncar nombre si es muy largo
                nombre_corto = (nombre[:25] + '...') if len(str(nombre)) > 25 else str(nombre)
                rutinas_table_data.append([nombre_corto, str(tipo), str(usos)])
            
            rutinas_table = Table(rutinas_table_data, colWidths=[2.5*inch, 1*inch, 1*inch])
            rutinas_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.purple),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTSIZE', (0, 1), (-1, -1), 9),  # Texto más pequeño para contenido
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lavender),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(rutinas_table)
            story.append(Spacer(1, 20))
        
        # Usuarios más activos
        usuarios_data = stats.get('usuarios_mas_activos', [])
        if usuarios_data:
            story.append(Paragraph("⭐ Usuarios Más Activos", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            usuarios_table_data = [['Nombre', 'Apellido', 'Actividades']]
            for usuario in usuarios_data[:10]:  # Limitar a 10 elementos
                nombre = usuario.get('nombre', 'N/A') if isinstance(usuario, dict) else getattr(usuario, 'nombre', 'N/A')
                apellido = usuario.get('apellido', 'N/A') if isinstance(usuario, dict) else getattr(usuario, 'apellido', 'N/A')
                actividades = usuario.get('actividades_completadas', 0) if isinstance(usuario, dict) else getattr(usuario, 'actividades_completadas', 0)
                usuarios_table_data.append([str(nombre), str(apellido), str(actividades)])
            
            usuarios_table = Table(usuarios_table_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch])
            usuarios_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.teal),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightcyan),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(usuarios_table)
        
        # Pie de página
        story.append(Spacer(1, 30))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.grey,
            alignment=1
        )
        story.append(Paragraph("Generado por FocusFit Admin Panel", footer_style))
        
        # Construir PDF
        doc.build(story)
        buffer.seek(0)
        
        # Crear respuesta
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=estadisticas_focusfit_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        
        return response
        
    except Exception as e:
        print(f"Error generando PDF: {e}")
        from flask import jsonify
        return jsonify({'error': f'Error generando PDF: {str(e)}'}), 500


@admin_bp.route('/perfil', methods=['GET', 'POST'])
@admin_login_required
def perfil():
    admin = {}
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT id, email, name, avatar FROM admin WHERE id = %s', (session.get('admin_id'),))
            admin = cur.fetchone()
        conn.close()
    except Exception:
        admin = {'email': session.get('admin_email')}

    if request.method == 'POST':
        correo = request.form.get('correo')
        password = request.form.get('password')
        avatar = request.files.get('avatar')
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                if correo and correo != admin.get('email'):
                    cur.execute('UPDATE admin SET email = %s WHERE id = %s', (correo, session.get('admin_id')))
                    session['admin_email'] = correo
                if password:
                    hashed = generate_password_hash(password)
                    cur.execute('UPDATE admin SET password = %s WHERE id = %s', (hashed, session.get('admin_id')))
                if avatar and avatar.filename:
                    ext = os.path.splitext(secure_filename(avatar.filename))[1].lower()
                    unique_name = f"{uuid.uuid4().hex}{ext}"
                    save_path = os.path.join(current_app.config.get('ADMIN_UPLOAD_FOLDER'), unique_name)
                    avatar.save(save_path)
                    cur.execute('UPDATE admin SET avatar = %s WHERE id = %s', (unique_name, session.get('admin_id')))
            conn.commit()
            conn.close()
            flash('Perfil de administrador actualizado.', 'success')
            return redirect(url_for('admin.perfil'))
        except Exception as e:
            flash(f'Error actualizando perfil: {e}', 'danger')

    return render_template('admin/admin_perfil.html', admin=admin)


app = create_admin_app()


if __name__ == '__main__':
    app.run(port=5001, debug=True)
