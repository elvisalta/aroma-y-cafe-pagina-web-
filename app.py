import os
import re
import difflib
import unicodedata
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from conexion.conexion import obtener_conexion
from models import Usuario
from forms.cliente_form import ClienteForm
from forms.producto_form import ProductoForm
from forms.proveedor_form import ProveedorForm
from forms.facturacion_form import FacturacionForm
from forms.login_form import LoginForm
from forms.usuario_form import UsuarioForm
from forms.checkout_form import CheckoutForm

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'clave_secreta_aroma_cafe_2026')


# --- MÓDULO PAGOS: helpers ---
# IVA usado tanto en el carrito como en la factura (mismo valor en todo el sistema).
IVA_PORCENTAJE = 0.15

def asegurar_tabla_pagos(cursor):
    """Detalle del pago de cada factura. Se crea sola si no existe.
    Por seguridad NO se guarda el número completo de la tarjeta ni el CVV:
    solo titular, tipo/marca, últimos 4 dígitos y vencimiento."""
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS pagos_factura ("
        "factura_id INT NOT NULL PRIMARY KEY, "
        "forma_pago VARCHAR(20) NOT NULL, "
        "efectivo_recibido DECIMAL(10,2) DEFAULT NULL, "
        "vuelto DECIMAL(10,2) DEFAULT NULL, "
        "tarjeta_titular VARCHAR(100) DEFAULT NULL, "
        "tarjeta_tipo VARCHAR(20) DEFAULT NULL, "
        "tarjeta_marca VARCHAR(20) DEFAULT NULL, "
        "tarjeta_ultimos4 VARCHAR(4) DEFAULT NULL, "
        "tarjeta_vencimiento VARCHAR(5) DEFAULT NULL, "
        "FOREIGN KEY (factura_id) REFERENCES facturas(id) ON DELETE CASCADE)"
    )

def totales_con_iva(subtotal):
    iva = round(subtotal * IVA_PORCENTAJE, 2)
    return iva, round(subtotal + iva, 2)

def detectar_marca(numero):
    if numero.startswith('4'):
        return 'Visa'
    if re.match(r'^(5[1-5]|2[2-7])', numero):
        return 'Mastercard'
    if re.match(r'^3[47]', numero):
        return 'American Express'
    if re.match(r'^(36|38|30[0-5])', numero):
        return 'Diners Club'
    return 'Tarjeta'

def luhn_valido(numero):
    suma, alterna = 0, False
    for d in reversed(numero):
        n = int(d)
        if alterna:
            n *= 2
            if n > 9:
                n -= 9
        suma += n
        alterna = not alterna
    return suma % 10 == 0

def validar_tarjeta(form):
    """Devuelve (datos, errores). datos no incluye número completo ni CVV."""
    errores = []
    titular = (form.tarjeta_titular.data or '').strip()
    numero = re.sub(r'\D', '', form.tarjeta_numero.data or '')
    venc = (form.tarjeta_vencimiento.data or '').strip()
    cvv = (form.tarjeta_cvv.data or '').strip()

    if len(titular) < 3:
        errores.append('Ingresa el nombre del titular de la tarjeta.')
    if not (13 <= len(numero) <= 19) or not luhn_valido(numero):
        errores.append('El número de tarjeta no es válido.')
    m = re.match(r'^(\d{2})\s*/\s*(\d{2})$', venc)
    if not m or not (1 <= int(m.group(1)) <= 12):
        errores.append('El vencimiento debe tener el formato MM/AA.')
    else:
        hoy = datetime.now()
        mes, anio = int(m.group(1)), 2000 + int(m.group(2))
        if (anio, mes) < (hoy.year, hoy.month):
            errores.append('La tarjeta está vencida.')
    largo_cvv = 4 if numero.startswith(('34', '37')) else 3
    if not re.match(r'^\d{%d}$' % largo_cvv, cvv):
        errores.append(f'El CVV debe tener {largo_cvv} dígitos.')

    datos = {
        'titular': titular,
        'tipo': form.tarjeta_tipo.data or 'Crédito',
        'marca': detectar_marca(numero),
        'ultimos4': numero[-4:],
        'vencimiento': f"{m.group(1)}/{m.group(2)}" if m else '',
    }
    return datos, errores

def parsear_monto(texto):
    try:
        return round(float((texto or '').strip().replace(',', '.')), 2)
    except ValueError:
        return None

# --- MÓDULO CARRITO: helpers de sesión ---
def obtener_carrito():
    return session.setdefault('carrito', {})

def contar_items_carrito(carrito=None):
    carrito = carrito if carrito is not None else session.get('carrito', {})
    return sum(carrito.values())

@app.context_processor
def inyectar_carrito():
    return {'carrito_cantidad': contar_items_carrito()}

# --- CONFIGURACIÓN DE FLASK-LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Debes iniciar sesión para continuar'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, usuario, correo, contrasena FROM usuarios WHERE id = %s",
        (user_id,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()
    if fila:
        if isinstance(fila, dict):
            return Usuario(fila["id"], fila["usuario"], fila["contrasena"])
        return Usuario(fila[0], fila[1], fila[3])
    return None

# --- RUTA PRINCIPAL ---
@app.route("/")
def index():
    return render_template("index.html", empresa="Aroma y Café")

# --- PÁGINAS PÚBLICAS ---
@app.route("/quienes-somos")
def quienes_somos():
    return render_template("quienes_somos.html")

@app.route("/contacto")
def contacto():
    return render_template("contacto.html")

# --- MÓDULO LOGIN ---
@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('contrasena')
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, usuario, contrasena FROM usuarios WHERE usuario = %s",
            (usuario,)
        )
        resultado = cursor.fetchone()
        cursor.close()
        conn.close()
        if resultado:
            if isinstance(resultado, dict):
                pass_db = resultado["contrasena"]
                id_user = resultado["id"]
                nombre_user = resultado["usuario"]
            else:
                pass_db = resultado[2]
                id_user = resultado[0]
                nombre_user = resultado[1]

            if (pass_db.startswith('pbkdf2:') or pass_db.startswith('scrypt:')) and check_password_hash(pass_db, password):
                valido = True
            elif pass_db == password:
                valido = True
            else:
                valido = False

            if valido:
                usuario_obj = Usuario(id_user, nombre_user, pass_db)
                login_user(usuario_obj)
                flash(f'¡Bienvenido, {nombre_user}!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Contraseña incorrecta.', 'danger')
        else:
            flash('El usuario no existe.', 'danger')
    return redirect(url_for('index'))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada', 'info')
    return redirect(url_for('index'))

# --- FUNCIÓN AUXILIAR: Leer fila con soporte tupla/dict ---
def leer_fila(f, indice, clave, defecto=""):
    if isinstance(f, dict):
        return f.get(clave, defecto)
    return f[indice] if len(f) > indice else defecto

# --- IMÁGENES DE PRODUCTOS ---
EXT_IMAGEN = ('.jpg', '.jpeg', '.png', '.webp', '.avif', '.jfif', '.gif')

def _normalizar(texto):
    texto = unicodedata.normalize('NFD', str(texto or ''))
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', texto.lower())

def _archivos_imagen():
    carpeta = os.path.join(app.root_path, 'static', 'img')
    try:
        return [n for n in os.listdir(carpeta) if n.lower().endswith(EXT_IMAGEN)]
    except OSError:
        return []

def imagen_valida(valor):
    if not valor:
        return None
    base = os.path.basename(str(valor).replace('\\', '/')).strip()
    if not base:
        return None
    for real in _archivos_imagen():
        if real.lower() == base.lower():
            return real
    return None

def buscar_imagen_por_nombre(nombre, cursor=None):
    clave = _normalizar(nombre)
    if not clave:
        return None
    archivos = _archivos_imagen()
    stems = {}
    for real in archivos:
        stems.setdefault(_normalizar(os.path.splitext(real)[0]), real)

    if clave in stems:
        return stems[clave]

    if cursor is not None:
        try:
            cursor.execute("SELECT imagen FROM imagenes_producto WHERE clave = %s", (clave,))
            fila = cursor.fetchone()
            if fila:
                recordada = imagen_valida(leer_fila(fila, 0, "imagen"))
                if recordada:
                    return recordada
        except Exception:
            pass

    candidatos = [s for s in stems if len(s) >= 4 and (s in clave or (len(clave) >= 6 and clave in s))]
    if candidatos:
        return stems[max(candidatos, key=len)]

    cerca = difflib.get_close_matches(clave, list(stems), n=1, cutoff=0.8)
    return stems[cerca[0]] if cerca else None

def resolver_imagen(nombre, actual=None, cursor=None):
    return imagen_valida(actual) or buscar_imagen_por_nombre(nombre, cursor)

def asegurar_tabla_imagenes(cursor):
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS imagenes_producto ("
        "clave VARCHAR(100) NOT NULL PRIMARY KEY, "
        "imagen VARCHAR(255) NOT NULL)"
    )

def recordar_imagen(cursor, nombre, imagen):
    clave = _normalizar(nombre)
    if clave and imagen:
        cursor.execute(
            "INSERT INTO imagenes_producto (clave, imagen) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE imagen = VALUES(imagen)",
            (clave[:100], imagen)
        )

def sincronizar_imagenes():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    asegurar_tabla_imagenes(cursor)
    cursor.execute("SELECT id, nombre, imagen FROM productos")
    for f in cursor.fetchall():
        pid = leer_fila(f, 0, "id")
        nombre = leer_fila(f, 1, "nombre")
        actual = leer_fila(f, 2, "imagen")
        final = resolver_imagen(nombre, actual, cursor)
        if final != actual:
            cursor.execute("UPDATE productos SET imagen = %s WHERE id = %s", (final, pid))
        if final:
            recordar_imagen(cursor, nombre, final)
    conexion.commit()
    cursor.close()
    conexion.close()

# --- MÓDULO USUARIOS ---
@app.route("/usuarios", methods=['GET', 'POST'])
@login_required
def usuarios():
    form = UsuarioForm()
    if form.validate_on_submit():
        password_cifrada = generate_password_hash(form.password.data)
        correo_val = form.correo.data
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            cursor.execute(
                "INSERT INTO usuarios (usuario, correo, contrasena) VALUES (%s, %s, %s)",
                (form.usuario.data, correo_val, password_cifrada)
            )
            conexion.commit()
            flash('¡Usuario registrado correctamente!', 'success')
        except Exception as e:
            conexion.rollback()
            flash('Error: El nombre de usuario o correo ya se encuentran registrados.', 'danger')
        finally:
            cursor.close()
            conexion.close()
        return redirect(url_for('usuarios'))

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, usuario, correo FROM usuarios")
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    lista_usuarios = []
    for f in filas:
        lista_usuarios.append({
            "id": leer_fila(f, 0, "id"),
            "usuario": leer_fila(f, 1, "usuario"),
            "correo": leer_fila(f, 2, "correo", "Sin correo")
        })

    return render_template("formulario_usuario.html", form=form, usuarios=lista_usuarios)

@app.route("/usuarios/eliminar/<int:id>")
@login_required
def eliminar_usuario(id):
    if current_user.id == id:
        flash('No puedes eliminar tu propio usuario mientras tienes la sesión iniciada', 'danger')
        return redirect(url_for('usuarios'))
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash('Usuario eliminado correctamente.', 'success')
    return redirect(url_for('usuarios'))

# --- MÓDULO CLIENTES ---
@app.route("/clientes", methods=['GET', 'POST'])
@login_required
def clientes():
    form = ClienteForm()
    if form.validate_on_submit():
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            cursor.execute(
                "INSERT INTO clientes (cedula, nombre, correo, telefono) VALUES (%s, %s, %s, %s)",
                (form.cedula.data, form.nombre.data, form.correo.data, form.telefono.data)
            )
            conexion.commit()
            flash('¡Cliente registrado correctamente!', 'success')
        except Exception as e:
            flash('Error: La cédula o el correo ya están registrados en el sistema.', 'danger')
        finally:
            cursor.close()
            conexion.close()
        return redirect(url_for('clientes'))

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, cedula, nombre, correo, telefono FROM clientes")
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    lista_clientes = []
    for f in filas:
        lista_clientes.append({
            "id": leer_fila(f, 0, "id"),
            "cedula": leer_fila(f, 1, "cedula"),
            "nombre": leer_fila(f, 2, "nombre"),
            "correo": leer_fila(f, 3, "correo"),
            "telefono": leer_fila(f, 4, "telefono")
        })
    return render_template("formulario_cliente.html", form=form, clientes=lista_clientes)

@app.route("/clientes/editar/<int:id>", methods=['GET', 'POST'])
@login_required
def editar_cliente(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, cedula, nombre, correo, telefono FROM clientes WHERE id = %s", (id,))
    item = cursor.fetchone()
    if not item:
        cursor.close()
        conexion.close()
        return redirect(url_for('clientes'))

    datos = {
        "id": leer_fila(item, 0, "id"),
        "cedula": leer_fila(item, 1, "cedula"),
        "nombre": leer_fila(item, 2, "nombre"),
        "correo": leer_fila(item, 3, "correo"),
        "telefono": leer_fila(item, 4, "telefono")
    }
    form = ClienteForm(data=datos)

    if form.validate_on_submit():
        cursor.execute(
            "UPDATE clientes SET cedula = %s, nombre = %s, correo = %s, telefono = %s WHERE id = %s",
            (form.cedula.data, form.nombre.data, form.correo.data, form.telefono.data, id)
        )
        conexion.commit()
        cursor.close()
        conexion.close()
        flash('Cliente actualizado correctamente.', 'success')
        return redirect(url_for('clientes'))
    cursor.close()
    conexion.close()
    return render_template("formulario_cliente.html", form=form, editando=True)

@app.route("/clientes/eliminar/<int:id>")
@login_required
def eliminar_cliente(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM clientes WHERE id = %s", (id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash('Cliente eliminado correctamente.', 'success')
    return redirect(url_for('clientes'))

# --- MÓDULO PRODUCTOS ---
@app.route("/productos", methods=['GET', 'POST'])
@login_required
def productos():
    form = ProductoForm()
    if form.validate_on_submit():
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        categoria_val = getattr(form, 'categoria', getattr(form, 'descripcion', None))
        cat_str = categoria_val.data if categoria_val and hasattr(categoria_val, 'data') else 'General'
        asegurar_tabla_imagenes(cursor)
        imagen = buscar_imagen_por_nombre(form.nombre.data, cursor)
        cursor.execute(
            "INSERT INTO productos (nombre, categoria, precio, stock, imagen) VALUES (%s, %s, %s, %s, %s)",
            (form.nombre.data, cat_str, float(form.precio.data), int(form.stock.data), imagen)
        )
        recordar_imagen(cursor, form.nombre.data, imagen)
        conexion.commit()
        cursor.close()
        conexion.close()
        flash('Producto agregado correctamente.', 'success')
        return redirect(url_for('productos'))

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, categoria, precio, stock, imagen FROM productos")
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    lista_productos = []
    for f in filas:
        lista_productos.append({
            "id": leer_fila(f, 0, "id"),
            "nombre": leer_fila(f, 1, "nombre"),
            "categoria": leer_fila(f, 2, "categoria"),
            "precio": leer_fila(f, 3, "precio"),
            "stock": leer_fila(f, 4, "stock"),
            "imagen": leer_fila(f, 5, "imagen")
        })
    return render_template("formulario_producto.html", form=form, productos=lista_productos)

@app.route("/productos/editar/<int:id>", methods=['GET', 'POST'])
@login_required
def editar_producto(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, categoria, precio, stock, imagen FROM productos WHERE id = %s", (id,))
    item = cursor.fetchone()
    if not item:
        cursor.close()
        conexion.close()
        return redirect(url_for('productos'))

    datos_producto = {
        "id": leer_fila(item, 0, "id"),
        "nombre": leer_fila(item, 1, "nombre"),
        "descripcion": leer_fila(item, 2, "categoria"),
        "precio": leer_fila(item, 3, "precio"),
        "stock": leer_fila(item, 4, "stock"),
        "imagen": leer_fila(item, 5, "imagen")
    }
    form = ProductoForm(data=datos_producto)

    if form.validate_on_submit():
        categoria_val = getattr(form, 'categoria', getattr(form, 'descripcion', None))
        cat_str = categoria_val.data if categoria_val and hasattr(categoria_val, 'data') else 'General'
        asegurar_tabla_imagenes(cursor)
        imagen = buscar_imagen_por_nombre(form.nombre.data, cursor) or imagen_valida(datos_producto["imagen"])
        cursor.execute(
            "UPDATE productos SET nombre = %s, categoria = %s, precio = %s, stock = %s, imagen = %s WHERE id = %s",
            (form.nombre.data, cat_str, float(form.precio.data), int(form.stock.data), imagen, id)
        )
        recordar_imagen(cursor, form.nombre.data, imagen)
        conexion.commit()
        cursor.close()
        conexion.close()
        flash('Producto actualizado correctamente.', 'success')
        return redirect(url_for('productos'))
    cursor.close()
    conexion.close()
    return render_template("formulario_producto.html", form=form, editando=True)

@app.route("/productos/eliminar/<int:id>")
@login_required
def eliminar_producto(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM productos WHERE id = %s", (id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash('Producto eliminado correctamente.', 'success')
    return redirect(url_for('productos'))

# --- MÓDULO MENÚ ---
@app.route("/menu")
def menu():
    try:
        sincronizar_imagenes()
    except Exception as e:
        print("Aviso: no se pudieron sincronizar las imágenes:", e)
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, categoria, precio, stock, imagen FROM productos")
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    lista_productos = []
    for f in filas:
        lista_productos.append({
            "id": leer_fila(f, 0, "id"),
            "nombre": leer_fila(f, 1, "nombre"),
            "categoria": leer_fila(f, 2, "categoria"),
            "precio": leer_fila(f, 3, "precio"),
            "stock": leer_fila(f, 4, "stock"),
            "imagen": resolver_imagen(leer_fila(f, 1, "nombre"), leer_fila(f, 5, "imagen"))
        })
    return render_template("menu.html", productos=lista_productos)

# --- MÓDULO CARRITO ---
@app.route("/carrito/agregar", methods=['POST'])
def agregar_al_carrito():
    datos = request.get_json(silent=True) or request.form
    try:
        producto_id = int(datos.get('producto_id'))
        cantidad = int(datos.get('cantidad', 1))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'mensaje': 'Producto o cantidad inválidos.'}), 400

    if cantidad < 1:
        cantidad = 1

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, stock FROM productos WHERE id = %s", (producto_id,))
    producto = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not producto:
        return jsonify({'ok': False, 'mensaje': 'El producto ya no existe.'}), 404

    prod_nombre = leer_fila(producto, 1, "nombre")
    prod_stock = int(leer_fila(producto, 2, "stock"))

    carrito = obtener_carrito()
    cantidad_actual = carrito.get(str(producto_id), 0)
    nueva_cantidad = cantidad_actual + cantidad

    if nueva_cantidad > prod_stock:
        return jsonify({
            'ok': False,
            'mensaje': f'Solo quedan {prod_stock} unidades de {prod_nombre}.'
        }), 400

    carrito[str(producto_id)] = nueva_cantidad
    session['carrito'] = carrito
    session.modified = True

    return jsonify({
        'ok': True,
        'mensaje': f'{prod_nombre} se agregó al carrito.',
        'carrito_cantidad': contar_items_carrito(carrito)
    })

@app.route("/carrito")
def ver_carrito():
    carrito = obtener_carrito()
    items = []
    total = 0.0

    if carrito:
        ids = [int(pid) for pid in carrito.keys()]
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        formato_ids = ",".join(["%s"] * len(ids))
        cursor.execute(
            f"SELECT id, nombre, precio, stock, imagen FROM productos WHERE id IN ({formato_ids})",
            tuple(ids)
        )
        filas = cursor.fetchall()
        cursor.close()
        conexion.close()

        productos_por_id = {int(leer_fila(f, 0, "id")): f for f in filas}

        for pid_str, cantidad in carrito.items():
            pid = int(pid_str)
            fila = productos_por_id.get(pid)
            if not fila:
                continue
            precio = float(leer_fila(fila, 2, "precio"))
            stock = int(leer_fila(fila, 3, "stock"))
            subtotal = round(precio * cantidad, 2)
            total += subtotal
            items.append({
                'id': pid,
                'nombre': leer_fila(fila, 1, "nombre"),
                'precio': precio,
                'stock': stock,
                'imagen': resolver_imagen(leer_fila(fila, 1, "nombre"), leer_fila(fila, 4, "imagen")),
                'cantidad': cantidad,
                'subtotal': subtotal
            })

    form = CheckoutForm()
    subtotal = round(total, 2)
    iva, total_general = totales_con_iva(subtotal)
    return render_template(
        "carrito.html", items=items, total=subtotal, iva=iva, total_general=total_general,
        iva_porcentaje=int(IVA_PORCENTAJE * 100), form=form
    )

@app.route("/carrito/actualizar/<int:producto_id>", methods=['POST'])
def actualizar_carrito(producto_id):
    carrito = obtener_carrito()
    try:
        cantidad = int(request.form.get('cantidad', 1))
    except (TypeError, ValueError):
        cantidad = 1

    if str(producto_id) in carrito:
        if cantidad < 1:
            carrito.pop(str(producto_id))
        else:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            cursor.execute("SELECT stock FROM productos WHERE id = %s", (producto_id,))
            fila = cursor.fetchone()
            cursor.close()
            conexion.close()
            stock = int(leer_fila(fila, 0, "stock")) if fila else 0
            carrito[str(producto_id)] = min(cantidad, stock) if stock else cantidad
        session['carrito'] = carrito
        session.modified = True

    return redirect(url_for('ver_carrito'))

@app.route("/carrito/eliminar/<int:producto_id>", methods=['POST'])
def eliminar_del_carrito(producto_id):
    carrito = obtener_carrito()
    carrito.pop(str(producto_id), None)
    session['carrito'] = carrito
    session.modified = True
    flash('Producto eliminado del carrito.', 'info')
    return redirect(url_for('ver_carrito'))

@app.route("/carrito/checkout", methods=['POST'])
def checkout_carrito():
    carrito = obtener_carrito()
    if not carrito:
        flash('Tu carrito está vacío.', 'danger')
        return redirect(url_for('ver_carrito'))

    form = CheckoutForm()
    if not form.validate_on_submit():
        for errores in form.errors.values():
            for error in errores:
                flash(error, 'danger')
        return redirect(url_for('ver_carrito'))

    cedula_form = form.cedula.data
    nombre_form = form.nombre.data
    correo_form = form.correo.data
    telefono_form = form.telefono.data
    forma_pago = form.forma_pago.data or 'Efectivo'

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    ids = [int(pid) for pid in carrito.keys()]
    formato_ids = ",".join(["%s"] * len(ids))
    cursor.execute(
        f"SELECT id, nombre, precio, stock FROM productos WHERE id IN ({formato_ids})",
        tuple(ids)
    )
    productos_por_id = {int(leer_fila(f, 0, "id")): f for f in cursor.fetchall()}

    lineas = []
    for pid_str, cantidad in carrito.items():
        pid = int(pid_str)
        fila = productos_por_id.get(pid)
        if not fila:
            cursor.close()
            conexion.close()
            flash('Uno de los productos del carrito ya no existe. Revisa tu carrito.', 'danger')
            return redirect(url_for('ver_carrito'))

        prod_nombre = leer_fila(fila, 1, "nombre")
        prod_precio = float(leer_fila(fila, 2, "precio"))
        prod_stock = int(leer_fila(fila, 3, "stock"))

        if cantidad > prod_stock:
            cursor.close()
            conexion.close()
            flash(f'Solo quedan {prod_stock} unidades de {prod_nombre}.', 'danger')
            return redirect(url_for('ver_carrito'))

        lineas.append({
            'producto_id': pid,
            'nombre': prod_nombre,
            'cantidad': cantidad,
            'precio': prod_precio,
            'subtotal': round(prod_precio * cantidad, 2)
        })

    cursor.execute("SELECT id FROM clientes WHERE cedula = %s OR correo = %s", (cedula_form, correo_form))
    cliente = cursor.fetchone()
    if cliente:
        cliente_id = leer_fila(cliente, 0, "id")
    else:
        try:
            cursor.execute(
                "INSERT INTO clientes (cedula, nombre, correo, telefono) VALUES (%s, %s, %s, %s)",
                (cedula_form, nombre_form, correo_form, telefono_form)
            )
            cliente_id = cursor.lastrowid
        except Exception:
            conexion.rollback()
            cursor.close()
            conexion.close()
            flash('Error al registrar los datos del cliente. Es posible que la cédula o correo ya estén en uso.', 'danger')
            return redirect(url_for('ver_carrito'))

    total_pedido = round(sum(l['subtotal'] for l in lineas), 2)
    _iva, total_a_pagar = totales_con_iva(total_pedido)

    efectivo_recibido = vuelto = None
    datos_tarjeta = None
    if forma_pago == 'Efectivo':
        texto = (form.efectivo_recibido.data or '').strip()
        efectivo_recibido = parsear_monto(texto) if texto else total_a_pagar
        if efectivo_recibido is None:
            cursor.close(); conexion.close()
            flash('El monto con el que paga no es válido.', 'danger')
            return redirect(url_for('ver_carrito'))
        if efectivo_recibido < total_a_pagar:
            cursor.close(); conexion.close()
            flash(f'El monto recibido (${efectivo_recibido:.2f}) es menor al total a pagar (${total_a_pagar:.2f}).', 'danger')
            return redirect(url_for('ver_carrito'))
        vuelto = round(efectivo_recibido - total_a_pagar, 2)
    else:
        datos_tarjeta, errores_tarjeta = validar_tarjeta(form)
        if errores_tarjeta:
            cursor.close(); conexion.close()
            for e in errores_tarjeta:
                flash(e, 'danger')
            return redirect(url_for('ver_carrito'))

    cursor.execute(
        "INSERT INTO pedidos (cliente_id, total, forma_pago) VALUES (%s, %s, %s)",
        (cliente_id, total_pedido, forma_pago)
    )
    pedido_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO facturas (cliente_id, total, forma_pago) VALUES (%s, %s, %s)",
        (cliente_id, total_pedido, forma_pago)
    )
    factura_id = cursor.lastrowid

    asegurar_tabla_pagos(cursor)
    if forma_pago == 'Efectivo':
        cursor.execute(
            "INSERT INTO pagos_factura (factura_id, forma_pago, efectivo_recibido, vuelto) VALUES (%s, %s, %s, %s)",
            (factura_id, 'Efectivo', efectivo_recibido, vuelto)
        )
    else:
        cursor.execute(
            "INSERT INTO pagos_factura (factura_id, forma_pago, tarjeta_titular, tarjeta_tipo, tarjeta_marca, tarjeta_ultimos4, tarjeta_vencimiento) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (factura_id, 'Tarjeta', datos_tarjeta['titular'], datos_tarjeta['tipo'], datos_tarjeta['marca'], datos_tarjeta['ultimos4'], datos_tarjeta['vencimiento'])
        )

    for l in lineas:
        cursor.execute(
            "INSERT INTO detalle_pedido (pedido_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (%s, %s, %s, %s, %s)",
            (pedido_id, l['producto_id'], l['cantidad'], l['precio'], l['subtotal'])
        )
        cursor.execute(
            "INSERT INTO detalle_factura (factura_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (%s, %s, %s, %s, %s)",
            (factura_id, l['producto_id'], l['cantidad'], l['precio'], l['subtotal'])
        )
        cursor.execute(
            "UPDATE productos SET stock = stock - %s WHERE id = %s",
            (l['cantidad'], l['producto_id'])
        )

    conexion.commit()
    cursor.close()
    conexion.close()

    session.pop('carrito', None)
    flash(f'¡Compra realizada con éxito! Factura #{factura_id} generada.', 'success')
    return redirect(url_for('menu'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
