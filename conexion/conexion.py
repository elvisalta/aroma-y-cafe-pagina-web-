import os
import pymysql

def obtener_conexion():
    conexion = pymysql.connect(
        host=os.getenv('MYSQLHOST', 'localhost'),
        user=os.getenv('MYSQLUSER', 'root'),
        password=os.getenv('MYSQLPASSWORD', ''),
        database=os.getenv('MYSQLDATABASE', 'olidb'),
        port=int(os.getenv('MYSQLPORT', 3306)),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return conexion
