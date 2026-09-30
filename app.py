import os
import re
import difflib
import unicodedata
import uuid
import pymysql
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
from conexion.inicializar_bd import inicializar_bd
from validaciones import (
    validar_cantidad, validar_tarjeta_numero, validar_vencimiento, validar_nombre_persona,
    parsear_monto, MAX_UNIDADES_POR_PRODUCTO
)

app = Flask(__name__)
# En Railway define la variable SECRET_KEY (cualquier texto largo y secreto).
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave_secreta_aroma_cafe_2026')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024   # rechaza envíos de más de 1 MB
# Railway está detrás de un proxy HTTPS: esto hace que Flask vea la URL/IP reales.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


# --- MÓDULO PAGOS: helpers ---
# IVA usado tanto en el carrito como en la factura (mismo valor en todo el sistema).
IVA_PORCENTAJE = 0.15

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

def validar_tarjeta(form):
    """Devuelve (datos, errores). datos no incluye número completo ni CVV."""
    errores = []
    titular = " ".join((form.tarjeta_titular.data or '').split())
    numero = re.sub(r'[ -]', '', form.tarjeta_numero.data or '')
    venc = (form.tarjeta_vencimiento.data or '').strip()
    cvv = (form.tarjeta_cvv.data or '').strip()

    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ '\-]{2,59}", titular):
        errores.append('El titular de la tarjeta solo puede tener letras (mínimo 3).')
    ok, msg = validar_tarjeta_numero(numero)
    if not ok:
        errores.append(msg)
    ok, msg = validar_vencimiento(venc)
    if not ok:
        errores.append(msg)
    largo_cvv = 4 if numero.startswith(('34', '37')) else 3
    if not re.fullmatch(r'\d{%d}' % largo_cvv, cvv, re.ASCII):
        errores.append(f'El CVV debe tener {largo_cvv} números.')

    m = re.fullmatch(r'(\d{2})\s*/\s*(\d{2})', venc)
    datos = {
        'titular': titular[:100],
        'tipo': form.tarjeta_tipo.data or 'Crédito',
        'marca': detectar_marca(numero),
        'ultimos4': numero[-4:],
        'vencimiento': f"{m.group(1)}/{m.group(2)}" if m else '',
    }
    return datos, errores


# --- MÓDULO PROVEEDORES: helpers ---
def ruc_ya_registrado(cursor, ruc, excluir_id=None):
    if excluir_id is None:
        cursor.execute("SELECT id FROM proveedores WHERE ruc = %s", (ruc,))
    else:
        cursor.execute("SELECT id FROM proveedores WHERE ruc = %s AND id <> %s", (ruc, excluir_id))
    return cursor.fetchone() is not None

# --- MÓDULO CARRITO: helpers de sesión ---
# El carrito vive en session['carrito'] como un diccionario
# { "producto_id_en_texto": cantidad }. Se guarda solo el id y la cantidad;
# el precio/nombre se leen siempre de la tabla productos al mostrar o al
# facturar, para que el carrito nunca quede desincronizado del stock/precio real.

def obtener_carrito():
    return session.setdefault('carrito', {})

def contar_items_carrito(carrito=None):
    carrito = carrito if carrito is not None else session.get('carrito', {})
    return sum(carrito.values())

@app.context_processor
def inyectar_carrito():
    # Disponible en TODOS los templates para pintar el contador del ícono
    return {
        'carrito_cantidad': contar_items_carrito(),
        'carrito_ids': list(session.get('carrito', {}).keys())  # ids (texto) de productos ya agregados
    }

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

@app.route("/promociones")
def promociones():
    # Productos marcados "en promoción" desde Gestión de Productos
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, nombre, precio_promocion, stock, imagen, precio FROM productos "
        "WHERE en_promocion = 1 AND precio_promocion IS NOT NULL AND stock > 0"
    )
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    productos_promo = []
    for f in filas:
        normal = float(leer_fila(f, 5, "precio"))
        promo = float(leer_fila(f, 2, "precio_promocion"))
        productos_promo.append({
            "id": leer_fila(f, 0, "id"),
            "nombre": leer_fila(f, 1, "nombre"),
            "precio_promo": promo,
            "precio_normal": normal,
            "descuento": round((1 - promo / normal) * 100) if normal > 0 else 0,
            "stock": int(leer_fila(f, 3, "stock", 0) or 0),
            "imagen": resolver_imagen(leer_fila(f, 1, "nombre"), leer_fila(f, 4, "imagen"))
        })
    return render_template("promociones.html", productos_promo=productos_promo)

@app.route("/contacto")
def contacto():
    return render_template("contacto.html")

# --- MÓDULO LOGIN ---
@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        usuario = (request.form.get('usuario') or '').strip()
        password = request.form.get('contrasena') or ''
        if not usuario or not password:
            flash('Escribe tu usuario y contraseña.', 'danger')
            return redirect(url_for('index'))
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

# --- IMÁGENES DE PRODUCTOS: reconocimiento automático por nombre ---
# Las fotos viven en static/img. Cada producto se enlaza con su foto así:
#   1) si el nombre del archivo coincide con el nombre del producto
#      (sin importar mayúsculas, tildes, espacios o guiones): "Café Americano" -> "CAFE AMERICANO.jpg"
#   2) si ese producto ya tuvo una imagen antes (tabla imagenes_producto), se reutiliza
#      -> así, si lo eliminas y lo vuelves a agregar, recupera la misma foto
#   3) si el nombre del archivo está contenido en el nombre del producto, o se parece mucho
# Además, el valor guardado en la columna productos.imagen se tolera aunque tenga
# otra mayúscula, una ruta ("static/img/x.jpg") o barras invertidas de Windows.
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
    """Devuelve el nombre REAL del archivo en static/img si el valor existe, o None."""
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

    # 1) coincidencia exacta nombre producto == nombre archivo
    if clave in stems:
        return stems[clave]

    # 2) imagen que ese producto ya tuvo antes (sobrevive a eliminar el producto)
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

    # 3) el nombre del archivo está dentro del nombre del producto (o al revés)
    candidatos = [s for s in stems
                  if len(s) >= 4 and (s in clave or (len(clave) >= 6 and clave in s))]
    if candidatos:
        return stems[max(candidatos, key=len)]

    # 4) nombres casi iguales (ej. "Bizcochos" vs "biscochos.jfif")
    cerca = difflib.get_close_matches(clave, list(stems), n=1, cutoff=0.8)
    return stems[cerca[0]] if cerca else None

def resolver_imagen(nombre, actual=None, cursor=None):
    """Imagen a usar: la de la BD si el archivo existe; si no, la que coincide por nombre."""
    return imagen_valida(actual) or buscar_imagen_por_nombre(nombre, cursor)

# --- PROMOCIONES: columnas nuevas en productos ---
# en_promocion (0/1) y precio_promocion. Se crean solas si no existen.
# PRECIO_FINAL devuelve el precio que se cobra: el de promoción si está activa.
PRECIO_FINAL = "IF(en_promocion = 1 AND precio_promocion IS NOT NULL, precio_promocion, precio)"

def asegurar_columnas_promocion(cursor):
    cursor.execute("SHOW COLUMNS FROM productos LIKE 'en_promocion'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE productos ADD COLUMN en_promocion TINYINT(1) NOT NULL DEFAULT 0")
    cursor.execute("SHOW COLUMNS FROM productos LIKE 'precio_promocion'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE productos ADD COLUMN precio_promocion DECIMAL(10,2) NULL")

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
    """Al iniciar: rellena/corrige productos.imagen de todos los productos existentes."""
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

    return render_template(
        "formulario_usuario.html",
        form=form,
        usuarios=lista_usuarios
    )

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
        except pymysql.err.IntegrityError:
            conexion.rollback()
            flash('Error: La cédula o el correo ya están registrados en el sistema.', 'danger')
        except Exception:
            conexion.rollback()
            app.logger.exception("Error al registrar cliente")
            flash('No se pudo registrar el cliente. Intenta de nuevo.', 'danger')
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
        try:
            cursor.execute(
                "UPDATE clientes SET cedula = %s, nombre = %s, correo = %s, telefono = %s WHERE id = %s",
                (form.cedula.data, form.nombre.data, form.correo.data, form.telefono.data, id)
            )
            conexion.commit()
            cursor.close()
            conexion.close()
            flash('Cliente actualizado correctamente.', 'success')
            return redirect(url_for('clientes'))
        except pymysql.err.IntegrityError:
            conexion.rollback()
            flash('Esa cédula o ese correo ya pertenecen a otro cliente.', 'danger')
    cursor.close()
    conexion.close()
    return render_template("formulario_cliente.html", form=form, editando=True)

@app.route("/clientes/eliminar/<int:id>")
@login_required
def eliminar_cliente(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT cedula FROM clientes WHERE id = %s", (id,))
    fila = cursor.fetchone()
    if fila and leer_fila(fila, 0, "cedula") == "9999999999":
        flash('El "Cliente General" no se puede eliminar: se usa para ventas sin datos.', 'danger')
    else:
        cursor.execute("SELECT COUNT(*) AS n FROM facturas WHERE cliente_id = %s", (id,))
        if int(leer_fila(cursor.fetchone(), 0, "n")) > 0:
            flash('No se puede eliminar: el cliente tiene facturas registradas. '
                  'Eliminarlo borraría también sus facturas.', 'danger')
        else:
            cursor.execute("DELETE FROM clientes WHERE id = %s", (id,))
            conexion.commit()
            flash('Cliente eliminado correctamente.', 'success')
    cursor.close()
    conexion.close()
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
            "INSERT INTO productos (nombre, categoria, precio, stock, imagen, en_promocion, precio_promocion) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (form.nombre.data, cat_str, float(form.precio.data), int(form.stock.data), imagen,
             1 if form.en_promocion.data else 0,
             float(form.precio_promocion.data) if form.en_promocion.data else None)
        )
        recordar_imagen(cursor, form.nombre.data, imagen)
        conexion.commit()
        cursor.close()
        conexion.close()
        flash('Producto agregado correctamente.', 'success')
        return redirect(url_for('productos'))

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, categoria, precio, stock, imagen, en_promocion, precio_promocion FROM productos")
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
            "imagen": leer_fila(f, 5, "imagen"),
            "en_promocion": bool(leer_fila(f, 6, "en_promocion", 0)),
            "precio_promocion": leer_fila(f, 7, "precio_promocion", None)
        })
    return render_template("formulario_producto.html", form=form, productos=lista_productos)

@app.route("/productos/editar/<int:id>", methods=['GET', 'POST'])
@login_required
def editar_producto(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, categoria, precio, stock, imagen, en_promocion, precio_promocion FROM productos WHERE id = %s", (id,))
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
        "imagen": leer_fila(item, 5, "imagen"),
        "en_promocion": bool(leer_fila(item, 6, "en_promocion", 0)),
        "precio_promocion": leer_fila(item, 7, "precio_promocion", None)
    }
    form = ProductoForm(data=datos_producto)

    if form.validate_on_submit():
        categoria_val = getattr(form, 'categoria', getattr(form, 'descripcion', None))
        cat_str = categoria_val.data if categoria_val and hasattr(categoria_val, 'data') else 'General'
        asegurar_tabla_imagenes(cursor)
        imagen = buscar_imagen_por_nombre(form.nombre.data, cursor) or imagen_valida(datos_producto["imagen"])
        cursor.execute(
            "UPDATE productos SET nombre = %s, categoria = %s, precio = %s, stock = %s, imagen = %s, en_promocion = %s, precio_promocion = %s WHERE id = %s",
            (form.nombre.data, cat_str, float(form.precio.data), int(form.stock.data), imagen,
             1 if form.en_promocion.data else 0,
             float(form.precio_promocion.data) if form.en_promocion.data else None, id)
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
    cursor.execute("SELECT COUNT(*) AS n FROM detalle_factura WHERE producto_id = %s", (id,))
    if int(leer_fila(cursor.fetchone(), 0, "n")) > 0:
        flash('No se puede eliminar: el producto ya está en facturas emitidas. '
              'Ponle stock 0 para que aparezca como agotado.', 'danger')
    else:
        cursor.execute("DELETE FROM productos WHERE id = %s", (id,))
        conexion.commit()
        flash('Producto eliminado correctamente.', 'success')
    cursor.close()
    conexion.close()
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
    cursor.execute(f"SELECT id, nombre, categoria, {PRECIO_FINAL} AS precio, stock, imagen, precio AS precio_normal, "
                   "(en_promocion = 1 AND precio_promocion IS NOT NULL) AS en_promo FROM productos")
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
            "imagen": resolver_imagen(leer_fila(f, 1, "nombre"), leer_fila(f, 5, "imagen")),
            "precio_normal": leer_fila(f, 6, "precio_normal"),
            "en_promocion": bool(leer_fila(f, 7, "en_promo", 0))
        })
    return render_template("menu.html", productos=lista_productos)

# --- MÓDULO CARRITO ---

class CompraError(Exception):
    """Error 'de negocio' con mensajes pensados para mostrarse tal cual al cliente."""
    def __init__(self, *mensajes):
        super().__init__(" ".join(mensajes))
        self.mensajes = mensajes


def _leer_productos(cursor, ids, bloquear=False):
    """{id: fila} de los productos pedidos, con el precio final (promoción incluida).
    bloquear=True usa SELECT ... FOR UPDATE: si dos clientes compran a la vez, el
    segundo espera a que el primero termine y ve el stock ya descontado."""
    if not ids:
        return {}
    marcas = ",".join(["%s"] * len(ids))
    sql = (f"SELECT id, nombre, {PRECIO_FINAL} AS precio, stock, imagen "
           f"FROM productos WHERE id IN ({marcas}) ORDER BY id")
    if bloquear:
        sql += " FOR UPDATE"
    cursor.execute(sql, tuple(sorted(ids)))
    return {int(leer_fila(f, 0, "id")): f for f in cursor.fetchall()}


def _contexto_carrito():
    """Datos para pintar el carrito. Si el stock cambió desde que el cliente agregó
    el producto (o se agotó / se eliminó), el carrito se ajusta solo y se le avisa."""
    carrito = obtener_carrito()
    items, total = [], 0.0

    if carrito:
        ids = []
        for pid_str in list(carrito):
            try:
                ids.append(int(pid_str))
            except ValueError:
                carrito.pop(pid_str, None)

        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            productos_por_id = _leer_productos(cursor, ids)
        finally:
            cursor.close()
            conexion.close()

        for pid_str, cantidad in list(carrito.items()):
            fila = productos_por_id.get(int(pid_str))
            if not fila:                       # el producto fue eliminado del catálogo
                carrito.pop(pid_str, None)
                continue
            nombre_prod = leer_fila(fila, 1, "nombre")
            precio = float(leer_fila(fila, 2, "precio"))
            stock = int(leer_fila(fila, 3, "stock"))

            if stock <= 0:
                carrito.pop(pid_str, None)
                flash(f'{nombre_prod} se agotó y lo quitamos de tu carrito.', 'info')
                continue
            tope = min(stock, MAX_UNIDADES_POR_PRODUCTO)
            if cantidad > tope:
                cantidad = carrito[pid_str] = tope
                flash(f'Ajustamos {nombre_prod} a {tope} unidad(es), que es lo disponible.', 'info')

            subtotal = round(precio * cantidad, 2)
            total += subtotal
            items.append({
                'id': int(pid_str), 'nombre': nombre_prod, 'precio': precio, 'stock': stock,
                'tope': tope,
                'imagen': resolver_imagen(nombre_prod, leer_fila(fila, 4, "imagen")),
                'cantidad': cantidad, 'subtotal': subtotal
            })
        session['carrito'] = carrito
        session.modified = True

    subtotal = round(total, 2)
    iva, total_general = totales_con_iva(subtotal)
    return dict(items=items, total=subtotal, iva=iva, total_general=total_general,
                iva_porcentaje=int(IVA_PORCENTAJE * 100))


def _mostrar_carrito(form):
    """Vuelve a pintar el carrito CONSERVANDO lo que el cliente escribió (y sus errores)."""
    form.tarjeta_cvv.data = ''            # el CVV nunca se devuelve a la página
    return render_template("carrito.html", form=form, **_contexto_carrito())


@app.route("/carrito/agregar", methods=['POST'])
def agregar_al_carrito():
    """Agrega un producto al carrito (sesión). Responde JSON para el botón AJAX."""
    datos = request.get_json(silent=True) or request.form
    try:
        producto_id = int(datos.get('producto_id'))
        cantidad = int(datos.get('cantidad', 1))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'mensaje': 'Producto o cantidad inválidos.'}), 400

    if not (1 <= cantidad <= MAX_UNIDADES_POR_PRODUCTO):
        return jsonify({'ok': False,
                        'mensaje': f'La cantidad debe estar entre 1 y {MAX_UNIDADES_POR_PRODUCTO}.'}), 400

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
    if prod_stock <= 0:
        return jsonify({'ok': False, 'mensaje': f'{prod_nombre} está agotado.'}), 400

    carrito = obtener_carrito()
    en_carrito = carrito.get(str(producto_id), 0)
    disponible = min(prod_stock, MAX_UNIDADES_POR_PRODUCTO) - en_carrito
    if cantidad > disponible:
        if disponible <= 0:
            mensaje = f'Ya tienes en tu carrito todas las unidades disponibles de {prod_nombre}.'
        else:
            mensaje = f'Solo puedes agregar {disponible} más de {prod_nombre} (hay {prod_stock} en stock).'
        return jsonify({'ok': False, 'mensaje': mensaje}), 400

    carrito[str(producto_id)] = en_carrito + cantidad
    session['carrito'] = carrito
    session.modified = True

    return jsonify({
        'ok': True,
        'mensaje': f'{prod_nombre} se agregó al carrito.',
        'carrito_cantidad': contar_items_carrito(carrito)
    })


@app.route("/carrito")
def ver_carrito():
    return render_template("carrito.html", form=CheckoutForm(), **_contexto_carrito())


@app.route("/carrito/actualizar/<int:producto_id>", methods=['POST'])
def actualizar_carrito(producto_id):
    carrito = obtener_carrito()
    clave = str(producto_id)
    if clave not in carrito:
        return redirect(url_for('ver_carrito'))

    try:
        cantidad = int(request.form.get('cantidad', 1))
    except (TypeError, ValueError):
        flash('La cantidad debe ser un número entero.', 'danger')
        return redirect(url_for('ver_carrito'))

    if cantidad < 1:
        carrito.pop(clave, None)
        flash('Producto eliminado del carrito.', 'info')
    else:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("SELECT nombre, stock FROM productos WHERE id = %s", (producto_id,))
        fila = cursor.fetchone()
        cursor.close()
        conexion.close()

        stock = int(leer_fila(fila, 1, "stock")) if fila else 0
        nombre_prod = leer_fila(fila, 0, "nombre") if fila else 'El producto'
        tope = min(stock, MAX_UNIDADES_POR_PRODUCTO)
        if tope <= 0:
            carrito.pop(clave, None)
            flash(f'{nombre_prod} ya no está disponible y lo quitamos del carrito.', 'info')
        elif cantidad > tope:
            carrito[clave] = tope
            flash(f'Solo hay {tope} unidad(es) de {nombre_prod}; ajustamos la cantidad.', 'info')
        else:
            carrito[clave] = cantidad

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
    """UN solo pedido y UNA sola factura para todos los ítems del carrito.
    Todo ocurre en una transacción: o se guarda completo, o no se guarda nada."""
    carrito = obtener_carrito()
    if not carrito:
        flash('Tu carrito está vacío.', 'danger')
        return redirect(url_for('ver_carrito'))

    form = CheckoutForm()
    if not form.validate_on_submit():
        if 'csrf_token' in form.errors:
            flash('El formulario estuvo abierto demasiado tiempo. Vuelve a intentarlo.', 'danger')
        return _mostrar_carrito(form)

    cedula = form.cedula.data
    nombre_cliente = form.nombre.data
    correo = form.correo.data
    telefono = form.telefono.data
    forma_pago = form.forma_pago.data or 'Efectivo'

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        conexion.begin()

        # 1) Releer cada producto BLOQUEADO: precio y stock reales, nunca los de la sesión
        try:
            ids = [int(pid) for pid in carrito]
        except ValueError:
            raise CompraError('Tu carrito tiene un producto inválido. Quítalo e inténtalo de nuevo.')
        productos_por_id = _leer_productos(cursor, ids, bloquear=True)

        lineas = []
        for pid_str, cantidad in carrito.items():
            fila = productos_por_id.get(int(pid_str))
            if not fila:
                raise CompraError('Uno de los productos del carrito ya no existe. Revisa tu carrito.')
            nombre_prod = leer_fila(fila, 1, "nombre")
            precio = float(leer_fila(fila, 2, "precio"))
            stock = int(leer_fila(fila, 3, "stock"))
            if stock <= 0:
                raise CompraError(f'{nombre_prod} se agotó. Quítalo del carrito para continuar.')
            ok, msg = validar_cantidad(cantidad, stock)
            if not ok:
                raise CompraError(f'{nombre_prod}: {msg}')
            lineas.append({'producto_id': int(pid_str), 'nombre': nombre_prod, 'cantidad': int(cantidad),
                           'precio': precio, 'subtotal': round(precio * int(cantidad), 2)})

        # 2) Cliente: se identifica por la cédula; el correo no puede ser de otra persona
        cursor.execute("SELECT id FROM clientes WHERE cedula = %s", (cedula,))
        cliente = cursor.fetchone()
        if cliente:
            cliente_id = leer_fila(cliente, 0, "id")
            cursor.execute("SELECT id FROM clientes WHERE correo = %s AND id <> %s", (correo, cliente_id))
            if cursor.fetchone():
                raise CompraError('Ese correo ya está registrado con otra cédula.')
        else:
            cursor.execute("SELECT id FROM clientes WHERE correo = %s", (correo,))
            if cursor.fetchone():
                raise CompraError('Ese correo ya pertenece a otro cliente. Usa tu propio correo.')
            cursor.execute(
                "INSERT INTO clientes (cedula, nombre, correo, telefono) VALUES (%s, %s, %s, %s)",
                (cedula, nombre_cliente, correo, telefono)
            )
            cliente_id = cursor.lastrowid

        # 3) Pago (siempre validado en el servidor, con el total real + IVA)
        subtotal = round(sum(l['subtotal'] for l in lineas), 2)
        _iva, total_a_pagar = totales_con_iva(subtotal)
        efectivo_recibido = vuelto = datos_tarjeta = None
        if forma_pago == 'Efectivo':
            texto = (form.efectivo_recibido.data or '').strip()
            efectivo_recibido = parsear_monto(texto) if texto else total_a_pagar
            if efectivo_recibido is None:
                raise CompraError('El monto con el que paga no es válido (ejemplo: 20 o 20.50).')
            if efectivo_recibido < total_a_pagar:
                raise CompraError(f'El monto recibido (${efectivo_recibido:.2f}) es menor al total a pagar (${total_a_pagar:.2f}).')
            vuelto = round(efectivo_recibido - total_a_pagar, 2)
        else:
            datos_tarjeta, errores_tarjeta = validar_tarjeta(form)
            if errores_tarjeta:
                raise CompraError(*errores_tarjeta)

        # 4) Un único pedido y una única factura para TODO el carrito
        cursor.execute("INSERT INTO pedidos (cliente_id, total, forma_pago) VALUES (%s, %s, %s)",
                       (cliente_id, subtotal, forma_pago))
        pedido_id = cursor.lastrowid
        cursor.execute("INSERT INTO facturas (cliente_id, total, forma_pago) VALUES (%s, %s, %s)",
                       (cliente_id, subtotal, forma_pago))
        factura_id = cursor.lastrowid

        if forma_pago == 'Efectivo':
            cursor.execute(
                "INSERT INTO pagos_factura (factura_id, forma_pago, efectivo_recibido, vuelto) VALUES (%s, %s, %s, %s)",
                (factura_id, 'Efectivo', efectivo_recibido, vuelto))
        else:
            cursor.execute(
                "INSERT INTO pagos_factura (factura_id, forma_pago, tarjeta_titular, tarjeta_tipo, tarjeta_marca, "
                "tarjeta_ultimos4, tarjeta_vencimiento) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (factura_id, 'Tarjeta', datos_tarjeta['titular'], datos_tarjeta['tipo'], datos_tarjeta['marca'],
                 datos_tarjeta['ultimos4'], datos_tarjeta['vencimiento']))

        # Todas las líneas (sean 2 o 50 productos) en una sola instrucción cada tabla
        cursor.executemany(
            "INSERT INTO detalle_pedido (pedido_id, producto_id, cantidad, precio_unitario, subtotal) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(pedido_id, l['producto_id'], l['cantidad'], l['precio'], l['subtotal']) for l in lineas])
        cursor.executemany(
            "INSERT INTO detalle_factura (factura_id, producto_id, cantidad, precio_unitario, subtotal) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(factura_id, l['producto_id'], l['cantidad'], l['precio'], l['subtotal']) for l in lineas])

        # 5) Descontar stock; la condición stock >= cantidad impide vender de más
        for l in lineas:
            cursor.execute("UPDATE productos SET stock = stock - %s WHERE id = %s AND stock >= %s",
                           (l['cantidad'], l['producto_id'], l['cantidad']))
            if cursor.rowcount != 1:
                raise CompraError(f'{l["nombre"]} se agotó mientras comprabas. Revisa tu carrito.')

        conexion.commit()

    except CompraError as e:
        conexion.rollback()
        for m in e.mensajes:
            flash(m, 'danger')
        return _mostrar_carrito(form)
    except pymysql.err.IntegrityError:
        conexion.rollback()
        app.logger.exception("Compra rechazada por la base de datos")
        flash('No se pudo registrar la compra: la cédula o el correo chocan con un cliente ya registrado.', 'danger')
        return _mostrar_carrito(form)
    except Exception:
        conexion.rollback()
        app.logger.exception("Error inesperado en el checkout")
        flash('No pudimos completar tu compra. No se cobró nada; intenta de nuevo.', 'danger')
        return _mostrar_carrito(form)
    finally:
        cursor.close()
        conexion.close()

    session['carrito'] = {}
    session.modified = True
    flash(f'¡Gracias {nombre_cliente}! Tu pedido de {len(lineas)} producto(s) se facturó con éxito.', 'success')
    return redirect(url_for('menu'))


# --- MÓDULO PROVEEDORES ---
@app.route("/proveedores", methods=['GET', 'POST'])
@login_required
def proveedores():
    form = ProveedorForm()
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if form.validate_on_submit():
        ruc = form.ruc.data.strip()
        if ruc_ya_registrado(cursor, ruc):
            form.ruc.errors = list(form.ruc.errors) + ["Ya existe un proveedor registrado con ese RUC."]
        else:
            cursor.execute(
                "INSERT INTO proveedores (ruc, empresa, insumo, telefono) VALUES (%s, %s, %s, %s)",
                (ruc, form.empresa.data.strip(), form.insumo.data.strip(), form.telefono.data.strip())
            )
            conexion.commit()
            cursor.close()
            conexion.close()
            flash('Proveedor registrado correctamente.', 'success')
            return redirect(url_for('proveedores'))

    cursor.execute("SELECT id, ruc, empresa, insumo, telefono FROM proveedores ORDER BY id DESC")
    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    lista_proveedores = []
    for f in filas:
        lista_proveedores.append({
            "id": leer_fila(f, 0, "id"),
            "ruc": leer_fila(f, 1, "ruc") or "",
            "empresa": leer_fila(f, 2, "empresa"),
            "insumo": leer_fila(f, 3, "insumo"),
            "telefono": leer_fila(f, 4, "telefono")
        })
    return render_template("formulario_proveedor.html", form=form, proveedores=lista_proveedores)

@app.route("/proveedores/editar/<int:id>", methods=['GET', 'POST'])
@login_required
def editar_proveedor(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, ruc, empresa, insumo, telefono FROM proveedores WHERE id = %s", (id,))
    item = cursor.fetchone()
    if not item:
        cursor.close()
        conexion.close()
        return redirect(url_for('proveedores'))

    datos = {
        "id": leer_fila(item, 0, "id"),
        "ruc": leer_fila(item, 1, "ruc") or "",
        "empresa": leer_fila(item, 2, "empresa"),
        "insumo": leer_fila(item, 3, "insumo"),
        "telefono": leer_fila(item, 4, "telefono")
    }
    form = ProveedorForm(data=datos)
    form.submit.label.text = 'Guardar cambios'

    if form.validate_on_submit():
        ruc = form.ruc.data.strip()
        if ruc_ya_registrado(cursor, ruc, excluir_id=id):
            form.ruc.errors = list(form.ruc.errors) + ["Ya existe otro proveedor con ese RUC."]
        else:
            cursor.execute(
                "UPDATE proveedores SET ruc = %s, empresa = %s, insumo = %s, telefono = %s WHERE id = %s",
                (ruc, form.empresa.data.strip(), form.insumo.data.strip(), form.telefono.data.strip(), id)
            )
            conexion.commit()
            cursor.close()
            conexion.close()
            flash('Proveedor actualizado correctamente.', 'success')
            return redirect(url_for('proveedores'))
    cursor.close()
    conexion.close()
    return render_template("formulario_proveedor.html", form=form, editando=True)

@app.route("/proveedores/eliminar/<int:id>")
@login_required
def eliminar_proveedor(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM proveedores WHERE id = %s", (id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash('Proveedor eliminado correctamente.', 'success')
    return redirect(url_for('proveedores'))

# --- MÓDULO FACTURACIÓN ---

# El IVA (IVA_PORCENTAJE) se define arriba, en el módulo de pagos.
# El subtotal (facturas.total) se guarda sin impuestos; el IVA y el total
# general se calculan con totales_con_iva().

@app.route("/facturacion", methods=['GET', 'POST'])
@login_required
def facturacion():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, cedula FROM clientes ORDER BY nombre")
    clientes_db = cursor.fetchall()
    cursor.execute(f"SELECT id, nombre, {PRECIO_FINAL} AS precio, stock FROM productos ORDER BY nombre")
    productos_db = cursor.fetchall()

    if not clientes_db:
        flash('No hay clientes registrados.', 'info')
    if not productos_db:
        flash('No hay productos registrados.', 'info')

    form = FacturacionForm()
    form.cliente.choices = [(leer_fila(c, 0, "id"), f"{leer_fila(c, 1, 'nombre')} ({leer_fila(c, 2, 'cedula')})")
                            for c in clientes_db]
    catalogo = [{"id": leer_fila(p, 0, "id"), "nombre": leer_fila(p, 1, "nombre"),
                 "precio": float(leer_fila(p, 2, "precio")), "stock": int(leer_fila(p, 3, "stock"))}
                for p in productos_db]

    if form.validate_on_submit():
        # Las líneas llegan como listas paralelas: producto_id[] y cantidad[]
        ids_form = request.form.getlist('producto_id[]')
        cants_form = request.form.getlist('cantidad[]')
        error = None
        pedidas = {}
        if not ids_form or len(ids_form) != len(cants_form):
            error = 'Agrega al menos un producto a la factura.'
        else:
            for pid_txt, cant_txt in zip(ids_form, cants_form):
                try:
                    pid = int(pid_txt)
                except ValueError:
                    error = 'Hay una línea sin producto seleccionado.'
                    break
                ok, msg = validar_cantidad(cant_txt)
                if not ok:
                    error = msg
                    break
                pedidas[pid] = pedidas.get(pid, 0) + int(cant_txt)   # mismo producto repetido = se suma
                if pedidas[pid] > MAX_UNIDADES_POR_PRODUCTO:
                    error = f'Máximo {MAX_UNIDADES_POR_PRODUCTO} unidades por producto.'
                    break

        if not error:
            try:
                conexion.begin()
                cursor.execute("SELECT id FROM clientes WHERE id = %s", (form.cliente.data,))
                if not cursor.fetchone():
                    raise CompraError('El cliente seleccionado ya no existe.')
                productos_bd = _leer_productos(cursor, list(pedidas), bloquear=True)
                lineas = []
                for pid, cant in pedidas.items():
                    fila = productos_bd.get(pid)
                    if not fila:
                        raise CompraError('Uno de los productos ya no existe.')
                    nombre_prod = leer_fila(fila, 1, "nombre")
                    stock = int(leer_fila(fila, 3, "stock"))
                    if cant > stock:
                        raise CompraError(f'Solo hay {stock} unidades de {nombre_prod}.')
                    precio = float(leer_fila(fila, 2, "precio"))
                    lineas.append((pid, cant, precio, round(precio * cant, 2)))
                subtotal = round(sum(l[3] for l in lineas), 2)
                forma_pago = form.forma_pago.data or 'Efectivo'
                cursor.execute("INSERT INTO facturas (cliente_id, total, forma_pago) VALUES (%s, %s, %s)",
                               (form.cliente.data, subtotal, forma_pago))
                factura_id = cursor.lastrowid
                cursor.executemany(
                    "INSERT INTO detalle_factura (factura_id, producto_id, cantidad, precio_unitario, subtotal) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [(factura_id,) + l for l in lineas])
                for pid, cant, _p, _s in lineas:
                    cursor.execute("UPDATE productos SET stock = stock - %s WHERE id = %s AND stock >= %s",
                                   (cant, pid, cant))
                    if cursor.rowcount != 1:
                        raise CompraError('El stock cambió mientras facturabas. Intenta de nuevo.')
                cursor.execute(
                    "INSERT INTO pagos_factura (factura_id, forma_pago) VALUES (%s, %s)", (factura_id, forma_pago))
                conexion.commit()
                cursor.close()
                conexion.close()
                flash(f'Factura #{factura_id} registrada con {len(lineas)} producto(s).', 'success')
                return redirect(url_for('facturacion'))
            except CompraError as e:
                conexion.rollback()
                error = str(e)
            except Exception:
                conexion.rollback()
                app.logger.exception("Error al generar factura")
                error = 'No se pudo generar la factura. Intenta de nuevo.'
        flash(error, 'danger')
    elif request.method == 'POST':
        for errores in form.errors.values():
            for e in errores:
                flash(e, 'danger')

    # --- Historial de facturas: UNA fila por factura (no por línea de detalle) ---
    # 1) Resumen por factura: cliente, fecha, forma de pago y subtotal (GROUP BY)
    cursor.execute("""
        SELECT f.id, c.nombre AS cliente, f.total AS subtotal, f.forma_pago, f.fecha_factura,
               COUNT(d.id) AS num_items
        FROM facturas f
        JOIN clientes c ON f.cliente_id = c.id
        JOIN detalle_factura d ON d.factura_id = f.id
        GROUP BY f.id, c.nombre, f.total, f.forma_pago, f.fecha_factura
        ORDER BY f.id DESC
    """)
    filas_resumen = cursor.fetchall()

    # 2) Detalle de líneas por factura, comprimido con GROUP_CONCAT para traer
    #    todos los productos de todas las facturas en una sola consulta.
    cursor.execute("""
        SELECT d.factura_id,
               GROUP_CONCAT(d.producto_id ORDER BY d.id SEPARATOR '||') AS ids,
               GROUP_CONCAT(p.nombre ORDER BY d.id SEPARATOR '||') AS nombres,
               GROUP_CONCAT(d.cantidad ORDER BY d.id SEPARATOR '||') AS cantidades,
               GROUP_CONCAT(d.precio_unitario ORDER BY d.id SEPARATOR '||') AS precios,
               GROUP_CONCAT(d.subtotal ORDER BY d.id SEPARATOR '||') AS subtotales
        FROM detalle_factura d
        JOIN productos p ON d.producto_id = p.id
        GROUP BY d.factura_id
    """)
    filas_detalle = cursor.fetchall()

    # 3) Detalle del pago de cada factura (efectivo recibido/vuelto o datos de tarjeta)
    cursor.execute("SELECT * FROM pagos_factura")
    pagos_por_factura = {int(p["factura_id"]): p for p in cursor.fetchall()}
    conexion.commit()
    cursor.close()
    conexion.close()

    # Armamos un diccionario factura_id -> lista de items, separando cada
    # campo GROUP_CONCAT por '||' y emparejando posición a posición.
    items_por_factura = {}
    for fd in filas_detalle:
        factura_id = int(leer_fila(fd, 0, "factura_id"))
        ids = leer_fila(fd, 1, "ids", "").split('||')
        nombres = leer_fila(fd, 2, "nombres", "").split('||')
        cantidades = leer_fila(fd, 3, "cantidades", "").split('||')
        precios = leer_fila(fd, 4, "precios", "").split('||')
        subtotales = leer_fila(fd, 5, "subtotales", "").split('||')

        items_por_factura[factura_id] = [
            {
                "producto_id": ids[i],
                "nombre": nombres[i],
                "cantidad": int(cantidades[i]),
                "precio_unitario": float(precios[i]),
                "subtotal": float(subtotales[i])
            }
            for i in range(len(ids))
        ]

    lista_facturas = []
    for f in filas_resumen:
        factura_id = int(leer_fila(f, 0, "id"))
        subtotal = float(leer_fila(f, 2, "subtotal"))
        iva, total_general = totales_con_iva(subtotal)

        lista_facturas.append({
            "id": factura_id,
            "cliente": leer_fila(f, 1, "cliente"),
            "subtotal": subtotal,
            "iva": iva,
            "total_general": total_general,
            "forma_pago": leer_fila(f, 3, "forma_pago", "Efectivo"),
            "fecha": leer_fila(f, 4, "fecha_factura"),
            "num_items": leer_fila(f, 5, "num_items"),
            "pago": pagos_por_factura.get(factura_id),
            "productos_factura": items_por_factura.get(factura_id, [])
        })

    return render_template("formulario_facturacion.html", form=form, facturas=lista_facturas,
                           iva_porcentaje=int(IVA_PORCENTAJE * 100), catalogo=catalogo)

@app.route("/facturacion/eliminar/<int:id>")
@login_required
def eliminar_factura(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    # "id" ya es el id de facturas (no de detalle_factura); el CASCADE del
    # esquema borra automáticamente sus filas en detalle_factura.
    cursor.execute("DELETE FROM facturas WHERE id = %s", (id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash('Factura eliminada correctamente.', 'success')
    return redirect(url_for('facturacion'))

# --- CREA ADMIN SI NO EXISTE ---
def crear_admin_si_no_existe():
    """Usuario inicial. En Railway define ADMIN_PASSWORD para no usar la clave por defecto."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", ('admin',))
    if not cursor.fetchone():
        password_cifrada = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123'))
        cursor.execute(
            "INSERT INTO usuarios (usuario, correo, contrasena) VALUES (%s, %s, %s)",
            ('admin', 'admin@aromacafe.com', password_cifrada)
        )
        conexion.commit()
    cursor.close()
    conexion.close()


def arrancar():
    """Deja la base lista. Si la BD no responde, la app SÍ arranca (no se cae en el deploy)
    y lo intenta de nuevo en la primera petición."""
    try:
        inicializar_bd()
        crear_admin_si_no_existe()
        sincronizar_imagenes()
        return True
    except Exception as e:
        print("AVISO: no se pudo preparar la base de datos todavía:", e)
        return False


_bd_lista = arrancar()


@app.before_request
def _reintentar_bd():
    global _bd_lista
    if not _bd_lista and request.endpoint != 'salud':
        _bd_lista = arrancar()


@app.route("/salud")
def salud():
    """Railway puede usar esta ruta como Healthcheck."""
    try:
        cx = obtener_conexion()
        cx.ping()
        cx.close()
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": type(e).__name__}), 503


@app.errorhandler(404)
def no_encontrado(e):
    return render_template("index.html", empresa="Aroma y Café"), 404


@app.errorhandler(500)
def error_interno(e):
    return ("<h2>Ups, algo salió mal.</h2><p>Ya lo registramos. "
            "<a href='/'>Volver al inicio</a></p>"), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1',
            host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
