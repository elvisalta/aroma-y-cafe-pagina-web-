-- Esquema de Aroma y Café (MySQL / MariaDB).
-- NO borra nada: se puede ejecutar varias veces. La app también lo hace sola al iniciar
-- (conexion/inicializar_bd.py), así que este archivo es solo de referencia / para phpMyAdmin.

CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(50) NOT NULL UNIQUE,
    correo VARCHAR(100) NOT NULL UNIQUE,
    contrasena VARCHAR(255) NOT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS clientes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cedula VARCHAR(13) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    correo VARCHAR(100) NOT NULL UNIQUE,
    telefono VARCHAR(20) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT INTO clientes (cedula, nombre, correo, telefono)
SELECT '9999999999', 'Cliente General', 'cliente@aromacafe.com', '0999999999'
WHERE NOT EXISTS (SELECT 1 FROM clientes WHERE cedula = '9999999999');

CREATE TABLE IF NOT EXISTS proveedores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ruc VARCHAR(13) DEFAULT NULL,
    empresa VARCHAR(100) NOT NULL,
    insumo VARCHAR(100) NOT NULL,
    telefono VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    precio DECIMAL(10,2) NOT NULL,
    stock INT NOT NULL,
    imagen VARCHAR(255) DEFAULT NULL,
    en_promocion TINYINT(1) NOT NULL DEFAULT 0,
    precio_promocion DECIMAL(10,2) NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS imagenes_producto (
    clave VARCHAR(100) NOT NULL PRIMARY KEY,
    imagen VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    forma_pago ENUM('Efectivo', 'Tarjeta') NOT NULL DEFAULT 'Efectivo',
    fecha_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS detalle_pedido (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS facturas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    forma_pago ENUM('Efectivo', 'Tarjeta') NOT NULL DEFAULT 'Efectivo',
    fecha_factura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS detalle_factura (
    id INT AUTO_INCREMENT PRIMARY KEY,
    factura_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (factura_id) REFERENCES facturas(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Detalle del pago (no se guarda el número completo de la tarjeta ni el CVV).
CREATE TABLE IF NOT EXISTS pagos_factura (
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
) ENGINE=InnoDB;
