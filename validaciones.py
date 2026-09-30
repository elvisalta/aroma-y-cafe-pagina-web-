"""
validaciones.py - Filtros de validación de Aroma y Café.

Todo lo de aquí se ejecuta en el SERVIDOR (Flask), que es lo que de verdad
protege la base de datos. Los atributos HTML (maxlength, inputmode) y el JS
solo ayudan al usuario; se pueden saltar desde el navegador.

Cada validar_xxx() devuelve (True, "") o (False, "mensaje en español").
Los v_xxx son adaptadores listos para usar en Flask-WTF: validators=[v_cedula].
"""
import re
from datetime import date
from wtforms.validators import ValidationError

LETRAS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
CONSUMIDOR_FINAL = "9999999999"          # cédula genérica del "Cliente General"

MAX_UNIDADES_POR_PRODUCTO = 100          # tope de sentido común por línea de compra
MAX_PRECIO = 9999.99
MAX_STOCK = 100000


def _solo_digitos(valor, largo):
    """True si valor son exactamente `largo` dígitos 0-9 (re.ASCII evita ², ٣, etc.)."""
    return re.fullmatch(r"\d{%d}" % largo, valor or "", re.ASCII) is not None


# ---------------------------------------------------------------- IDENTIDAD
def validar_cedula(valor, permitir_consumidor_final=False):
    c = (valor or "").strip()
    if permitir_consumidor_final and c == CONSUMIDOR_FINAL:
        return True, ""
    if not _solo_digitos(c, 10):
        return False, "La cédula debe tener exactamente 10 números (sin letras, espacios ni símbolos)."
    prov = int(c[:2])
    if not (1 <= prov <= 24 or prov == 30):
        return False, "Cédula inválida: los dos primeros números deben ser una provincia (01 a 24)."
    if int(c[2]) >= 6:
        return False, "Cédula inválida: el tercer número debe ser menor a 6."
    coef = (2, 1, 2, 1, 2, 1, 2, 1, 2)
    total = 0
    for d, k in zip(c[:9], coef):
        p = int(d) * k
        total += p - 9 if p >= 10 else p
    if (10 - total % 10) % 10 != int(c[9]):
        return False, "Cédula inválida: el dígito verificador no coincide."
    return True, ""


def validar_ruc(valor):
    r = (valor or "").strip()
    if not _solo_digitos(r, 13):
        return False, "El RUC debe tener exactamente 13 números."
    if int(r[10:]) < 1:
        return False, "El RUC debe terminar en 001 (o el número de establecimiento)."
    tercero = int(r[2])
    if tercero < 6:                      # persona natural: empieza con una cédula válida
        ok, msg = validar_cedula(r[:10])
        if not ok:
            return False, "RUC inválido. " + msg
    elif tercero in (6, 9):              # sector público / sociedades
        prov = int(r[:2])
        if not (1 <= prov <= 24 or prov == 30):
            return False, "RUC inválido: los dos primeros números deben ser una provincia (01 a 24)."
    else:
        return False, "RUC inválido: el tercer número no es válido."
    return True, ""


def validar_nombre_persona(valor):
    n = " ".join((valor or "").split())
    if not (3 <= len(n) <= 100):
        return False, "El nombre debe tener entre 3 y 100 caracteres."
    if not re.fullmatch(r"[%s]+(?:[ '\-][%s]+)*" % (LETRAS, LETRAS), n) or len(n.split()) < 2:
        return False, "Escribe nombre y apellido usando solo letras (sin números ni símbolos)."
    return True, ""


def validar_texto_negocio(valor, etiqueta="El texto", minimo=2, maximo=100):
    """Empresa, insumo, categoría, producto: letras, números y . , & - ' ( ) /"""
    t = " ".join((valor or "").split())
    if not (minimo <= len(t) <= maximo):
        return False, f"{etiqueta} debe tener entre {minimo} y {maximo} caracteres."
    if not re.fullmatch(r"[%s0-9 .,&\-'()/ñÑ]+" % LETRAS, t):
        return False, f"{etiqueta} contiene símbolos no permitidos."
    if len(re.findall(r"[%s]" % LETRAS, t)) < 2:
        return False, f"{etiqueta} debe contener letras (no solo números)."
    return True, ""


# ---------------------------------------------------------------- CONTACTO
def validar_telefono(valor):
    t = (valor or "").strip()
    if re.fullmatch(r"09\d{8}", t, re.ASCII) or re.fullmatch(r"0[2-7]\d{7}", t, re.ASCII):
        return True, ""
    return False, "Teléfono inválido: celular de 10 números (09XXXXXXXX) o convencional de 9 números (02XXXXXXX)."


def validar_correo_largo(valor):
    if len((valor or "").strip()) > 100:
        return False, "El correo no puede pasar de 100 caracteres."
    return True, ""


# ---------------------------------------------------------------- USUARIOS
def validar_usuario(valor):
    u = (valor or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._\-]{2,29}", u):
        return False, "El usuario debe tener 3 a 30 caracteres, empezar con letra y usar solo letras, números, punto, guion o guion bajo."
    return True, ""


def validar_password(valor):
    p = valor or ""
    if not (8 <= len(p) <= 64):
        return False, "La contraseña debe tener entre 8 y 64 caracteres."
    if not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p):
        return False, "La contraseña debe combinar letras y números."
    return True, ""


# ---------------------------------------------------------------- PRODUCTOS
def validar_precio(valor):
    try:
        p = float(valor)
    except (TypeError, ValueError):
        return False, "Ingresa un precio válido."
    if p != p or p in (float("inf"), float("-inf")):
        return False, "Ingresa un precio válido."
    if p <= 0:
        return False, "El precio debe ser mayor que 0."
    if p > MAX_PRECIO:
        return False, f"El precio no puede pasar de ${MAX_PRECIO:,.2f}."
    if round(p, 2) != p:
        return False, "El precio solo puede tener 2 decimales."
    return True, ""


def validar_stock(valor):
    if valor is None:
        return False, "Ingresa el stock."
    if int(valor) < 0:
        return False, "El stock no puede ser negativo."
    if int(valor) > MAX_STOCK:
        return False, f"El stock no puede pasar de {MAX_STOCK:,}."
    return True, ""


def validar_cantidad(valor, stock=None):
    try:
        q = int(valor)
    except (TypeError, ValueError):
        return False, "La cantidad debe ser un número entero."
    if q < 1:
        return False, "La cantidad mínima es 1."
    if q > MAX_UNIDADES_POR_PRODUCTO:
        return False, f"Máximo {MAX_UNIDADES_POR_PRODUCTO} unidades por producto."
    if stock is not None and q > stock:
        return False, f"Solo hay {stock} unidades disponibles."
    return True, ""


# ---------------------------------------------------------------- PAGOS
def parsear_monto(texto):
    """'12,50' -> 12.5.  Devuelve None si no es un monto real (rechaza nan, inf, letras, negativos)."""
    t = (texto or "").strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,6}(\.\d{1,2})?", t, re.ASCII):
        return None
    return round(float(t), 2)


def validar_tarjeta_numero(valor):
    n = re.sub(r"[ -]", "", valor or "")
    if not re.fullmatch(r"\d{13,19}", n, re.ASCII):
        return False, "El número de tarjeta solo puede tener números (13 a 19)."
    suma, alterna = 0, False             # algoritmo de Luhn
    for d in reversed(n):
        x = int(d)
        if alterna:
            x *= 2
            if x > 9:
                x -= 9
        suma += x
        alterna = not alterna
    if suma % 10:
        return False, "El número de tarjeta no es válido."
    return True, ""


def validar_vencimiento(valor):
    m = re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*(\d{2})", (valor or "").strip())
    if not m:
        return False, "El vencimiento debe tener el formato MM/AA."
    hoy = date.today()
    if (2000 + int(m.group(2)), int(m.group(1))) < (hoy.year, hoy.month):
        return False, "La tarjeta está vencida."
    return True, ""


# ---------------------------------------------------------------- ADAPTADORES WTForms
def _wtf(func, **extra):
    def _validator(form, field):
        ok, msg = func(field.data, **extra)
        if not ok:
            raise ValidationError(msg)
    return _validator


v_cedula = _wtf(validar_cedula)                                        # compras públicas
v_cedula_admin = _wtf(validar_cedula, permitir_consumidor_final=True)  # gestión de clientes
v_ruc = _wtf(validar_ruc)
v_nombre_persona = _wtf(validar_nombre_persona)
v_telefono = _wtf(validar_telefono)
v_correo_largo = _wtf(validar_correo_largo)
v_usuario = _wtf(validar_usuario)
v_password = _wtf(validar_password)
v_precio = _wtf(validar_precio)
v_stock = _wtf(validar_stock)


def v_texto(etiqueta, minimo=2, maximo=100):
    return _wtf(validar_texto_negocio, etiqueta=etiqueta, minimo=minimo, maximo=maximo)
