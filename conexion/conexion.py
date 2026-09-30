"""
Conexión a MySQL.  Funciona en tu PC (XAMPP) y en Railway SIN cambiar código:

  * En Railway, el servicio de la app recibe las variables del MySQL de Railway
    (MYSQLHOST, MYSQLPORT, MYSQLUSER, MYSQLPASSWORD, MYSQLDATABASE, o MYSQL_URL).
  * En tu PC, si no existe ninguna variable, usa localhost / root / sin clave / olidb.
"""
import os
from urllib.parse import urlparse, unquote
import pymysql


def _config():
    url = os.environ.get('MYSQL_URL') or os.environ.get('DATABASE_URL')
    if url and url.startswith('mysql'):
        u = urlparse(url)
        return {
            'host': u.hostname, 'port': u.port or 3306,
            'user': unquote(u.username or 'root'), 'password': unquote(u.password or ''),
            'database': (u.path or '/olidb').lstrip('/') or 'olidb',
        }
    return {
        'host': os.environ.get('MYSQLHOST') or os.environ.get('DB_HOST', 'localhost'),
        'port': int(os.environ.get('MYSQLPORT') or os.environ.get('DB_PORT', 3306)),
        'user': os.environ.get('MYSQLUSER') or os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('MYSQLPASSWORD') or os.environ.get('DB_PASSWORD', ''),
        'database': os.environ.get('MYSQLDATABASE') or os.environ.get('DB_NAME', 'olidb'),
    }


_CFG = _config()
DB_NAME = _CFG['database']
# En Railway la base ya viene creada (se llama "railway"); en local se crea sola.
EN_NUBE = bool(os.environ.get('MYSQLHOST') or os.environ.get('MYSQL_URL') or os.environ.get('RAILWAY_ENVIRONMENT'))


def _conectar(con_base):
    datos = dict(_CFG)
    if not con_base:
        datos.pop('database')
    return pymysql.connect(
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        autocommit=False,
        **datos
    )


def obtener_conexion():
    return _conectar(True)


def obtener_conexion_servidor():
    """Conexión sin elegir base (solo se usa en local para crear olidb si no existe)."""
    return _conectar(False)
