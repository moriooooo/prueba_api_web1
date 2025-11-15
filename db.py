import os
import pymysql

# Configuración de conexión (ajusta según tu entorno)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '12345',
    'db': 'focusfit',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}


def get_db_connection():
    """Crea y devuelve una conexión a la base de datos."""
    return pymysql.connect(**DB_CONFIG)


def init_db_schema_only(admin_email='admin@focusfit.com', admin_password='admin123'):
    """
    Inicializa solo la estructura de la base de datos sin datos de ejemplo.
    Esta función es segura para llamar en arranques sin duplicar datos.
    """
    # conectar sin especificar la BD para poder crearla si hace falta
    cfg = DB_CONFIG.copy()
    db_name = cfg.pop('db')
    conn = None
    try:
        conn = pymysql.connect(host=cfg['host'], user=cfg['user'], password=cfg['password'], charset=cfg.get('charset','utf8mb4'))
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
        conn.close()

        # Conectarse ya a la BD creada
        cfg['db'] = db_name
        conn = pymysql.connect(**cfg)
        with conn.cursor() as cur:
            # Solo crear tabla admin si no existe
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    name VARCHAR(100),
                    avatar VARCHAR(255),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Insertar admin si no existe
            cur.execute("SELECT id FROM admin WHERE email = %s", (admin_email,))
            if not cur.fetchone():
                try:
                    from werkzeug.security import generate_password_hash
                    hashed = generate_password_hash(admin_password)
                except Exception:
                    hashed = admin_password
                cur.execute("INSERT INTO admin (email, password, name) VALUES (%s, %s, %s)", (admin_email, hashed, 'Administrador'))
        conn.commit()
    finally:
        if conn:
            conn.close()


def init_db_from_file(sql_file_path, admin_email='admin@focusfit.com', admin_password='admin123'):
    """
    Inicializa la base de datos ejecutando el SQL provisto en `sql_file_path`.
    Además crea una tabla `admin` si no existe e inserta un admin con la contraseña hasheada.
    Esta función es idempotente y segura para llamar en arranques de desarrollo.
    """
    # conectar sin especificar la BD para poder crearla si hace falta
    cfg = DB_CONFIG.copy()
    db_name = cfg.pop('db')
    conn = None
    try:
        conn = pymysql.connect(host=cfg['host'], user=cfg['user'], password=cfg['password'], charset=cfg.get('charset','utf8mb4'))
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
        conn.close()

        # Conectarse ya a la BD creada
        cfg['db'] = db_name
        conn = pymysql.connect(**cfg)
        with conn.cursor() as cur:
            # Ejecutar archivo SQL si existe
            if sql_file_path and os.path.exists(sql_file_path):
                with open(sql_file_path, 'r', encoding='utf-8') as f:
                    sql = f.read()
                # eliminar comentarios simples
                lines = []
                for line in sql.splitlines():
                    s = line.strip()
                    if s.startswith('--') or s.startswith('/*') or s.startswith('*/'):
                        continue
                    lines.append(line)
                sql_clean = '\n'.join(lines)
                # dividir por ';' y ejecutar cada statement
                for stmt in sql_clean.split(';'):
                    stmt = stmt.strip()
                    if not stmt:
                        continue
                    try:
                        cur.execute(stmt)
                    except Exception:
                        # algunos statements pueden requerir multi-line o fallar; intentar execute sin parar
                        try:
                            conn.commit()
                        except Exception:
                            pass
            # Crear tabla admin si no existe
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    name VARCHAR(100),
                    avatar VARCHAR(255),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Insertar admin si no existe
            cur.execute("SELECT id FROM admin WHERE email = %s", (admin_email,))
            if not cur.fetchone():
                try:
                    from werkzeug.security import generate_password_hash
                    hashed = generate_password_hash(admin_password)
                except Exception:
                    hashed = admin_password
                cur.execute("INSERT INTO admin (email, password, name) VALUES (%s, %s, %s)", (admin_email, hashed, 'Administrador'))
        conn.commit()
    finally:
        if conn:
            conn.close()
