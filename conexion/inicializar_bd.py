"""
Deja la base de datos lista SIN borrar nada.

Se ejecuta sola al iniciar app.py:
  1) crea la base 'olidb' si no existe
  2) crea las tablas que falten (CREATE TABLE IF NOT EXISTS)
  3) agrega las columnas nuevas que le falten a tablas viejas (ruc, promociones)
  4) agrega reglas CHECK (stock >= 0, precio > 0, cantidad > 0) para que la BD
     misma rechace datos imposibles aunque alguien se salte la página
  5) crea el "Cliente General" (cédula 9999999999) si no existe

Es seguro ejecutarla muchas veces. Los datos existentes no se tocan.
"""
from conexion.conexion import obtener_conexion, obtener_conexion_servidor, DB_NAME, EN_NUBE

TABLAS = [
    """CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(50) NOT NULL UNIQUE,
        correo VARCHAR(100) NOT NULL UNIQUE,
        contrasena VARCHAR(255) NOT NULL,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS clientes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cedula VARCHAR(13) NOT NULL UNIQUE,
        nombre VARCHAR(100) NOT NULL,
        correo VARCHAR(100) NOT NULL UNIQUE,
        telefono VARCHAR(20) NOT NULL,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS proveedores (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ruc VARCHAR(13) DEFAULT NULL,
        empresa VARCHAR(100) NOT NULL,
        insumo VARCHAR(100) NOT NULL,
        telefono VARCHAR(20) NOT NULL
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS productos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(100) NOT NULL,
        categoria VARCHAR(50) NOT NULL,
        precio DECIMAL(10,2) NOT NULL,
        stock INT NOT NULL,
        imagen VARCHAR(255) DEFAULT NULL,
        en_promocion TINYINT(1) NOT NULL DEFAULT 0,
        precio_promocion DECIMAL(10,2) NULL
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS imagenes_producto (
        clave VARCHAR(100) NOT NULL PRIMARY KEY,
        imagen VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS pedidos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cliente_id INT NOT NULL,
        total DECIMAL(10,2) NOT NULL,
        forma_pago ENUM('Efectivo', 'Tarjeta') NOT NULL DEFAULT 'Efectivo',
        fecha_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS detalle_pedido (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL,
        producto_id INT NOT NULL,
        cantidad INT NOT NULL,
        precio_unitario DECIMAL(10,2) NOT NULL,
        subtotal DECIMAL(10,2) NOT NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
        FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS facturas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cliente_id INT NOT NULL,
        total DECIMAL(10,2) NOT NULL,
        forma_pago ENUM('Efectivo', 'Tarjeta') NOT NULL DEFAULT 'Efectivo',
        fecha_factura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""",

    """CREATE TABLE IF NOT EXISTS detalle_factura (
        id INT AUTO_INCREMENT PRIMARY KEY,
        factura_id INT NOT NULL,
        producto_id INT NOT NULL,
        cantidad INT NOT NULL,
        precio_unitario DECIMAL(10,2) NOT NULL,
        subtotal DECIMAL(10,2) NOT NULL,
        FOREIGN KEY (factura_id) REFERENCES facturas(id) ON DELETE CASCADE,
        FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""",

    # Detalle del pago de cada factura. NO se guarda el número completo de la tarjeta ni el CVV.
    """CREATE TABLE IF NOT EXISTS pagos_factura (
        factura_id INT NOT NULL PRIMARY KEY,
        forma_pago VARCHAR(20) NOT NULL,
        efectivo_recibido DECIMAL(10,2) DEFAULT NULL,
        vuelto DECIMAL(10,2) DEFAULT NULL,
        tarjeta_titular VARCHAR(100) DEFAULT NULL,
        tarjeta_tipo VARCHAR(20) DEFAULT NULL,
        tarjeta_marca VARCHAR(20) DEFAULT NULL,
        tarjeta_ultimos4 VARCHAR(4) DEFAULT NULL,
        tarjeta_vencimiento VARCHAR(5) DEFAULT NULL,
        FOREIGN KEY (factura_id) REFERENCES facturas(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""",
]

# (tabla, nombre de la regla, condición). Se agregan solo si la tabla aún no las tiene.
REGLAS_CHECK = [
    ("productos", "chk_producto_stock", "stock >= 0"),
    ("productos", "chk_producto_precio", "precio > 0"),
    ("detalle_factura", "chk_detfac_cantidad", "cantidad > 0"),
    ("detalle_pedido", "chk_detped_cantidad", "cantidad > 0"),
]


def _columna_existe(cur, tabla, columna):
    cur.execute(f"SHOW COLUMNS FROM {tabla} LIKE %s", (columna,))
    return cur.fetchone() is not None


def _regla_existe(cur, tabla, nombre):
    cur.execute(
        "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = %s",
        (DB_NAME, tabla, nombre)
    )
    return cur.fetchone() is not None


def inicializar_bd():
    # 1) base de datos (solo en local; en Railway la base ya existe y no hay que crearla)
    if not EN_NUBE:
        cx = obtener_conexion_servidor()
        try:
            with cx.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            cx.commit()
        finally:
            cx.close()

    cx = obtener_conexion()
    try:
        cur = cx.cursor()

        # 2) tablas que falten
        for ddl in TABLAS:
            cur.execute(ddl)

        # 3) columnas nuevas en tablas que ya existían de versiones anteriores
        if not _columna_existe(cur, "proveedores", "ruc"):
            cur.execute("ALTER TABLE proveedores ADD COLUMN ruc VARCHAR(13) DEFAULT NULL")
        if not _columna_existe(cur, "productos", "en_promocion"):
            cur.execute("ALTER TABLE productos ADD COLUMN en_promocion TINYINT(1) NOT NULL DEFAULT 0")
        if not _columna_existe(cur, "productos", "precio_promocion"):
            cur.execute("ALTER TABLE productos ADD COLUMN precio_promocion DECIMAL(10,2) NULL")

        # 4) reglas CHECK (MariaDB de XAMPP y MySQL 8 las aplican; MySQL 5.7 las ignora)
        cur.execute("UPDATE productos SET stock = 0 WHERE stock < 0")   # limpia datos imposibles
        for tabla, nombre, condicion in REGLAS_CHECK:
            try:
                if not _regla_existe(cur, tabla, nombre):
                    cur.execute(f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} CHECK ({condicion})")
            except Exception as e:
                print(f"Aviso: no se pudo agregar la regla {nombre}: {e}")

        # 5) Cliente General (consumidor final)
        cur.execute("SELECT id FROM clientes WHERE cedula = %s", ("9999999999",))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO clientes (cedula, nombre, correo, telefono) VALUES (%s, %s, %s, %s)",
                ("9999999999", "Cliente General", "cliente@aromacafe.com", "0999999999")
            )
        cx.commit()
        cur.close()
    finally:
        cx.close()
