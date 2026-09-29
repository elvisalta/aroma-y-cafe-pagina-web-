import pymysql

def obtener_conexion():
    conexion = pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='olidb',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return conexion
