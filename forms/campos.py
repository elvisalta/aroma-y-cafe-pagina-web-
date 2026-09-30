"""Campos numéricos con mensajes de error en español (WTForms los trae en inglés)."""
from wtforms import IntegerField, DecimalField


class EnteroES(IntegerField):
    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            raise ValueError("Ingresa un número entero válido.")


class DecimalES(DecimalField):
    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            raise ValueError("Ingresa un número válido (ej. 2.50).")
        # Decimal acepta "NaN" e "Infinity" como texto válido: se rechazan aquí.
        if self.data is not None and not self.data.is_finite():
            self.data = None
            raise ValueError("Ingresa un número válido (ej. 2.50).")


def limpiar(valor):
    """Filtro: quita espacios de los extremos y espacios repetidos."""
    return " ".join(valor.split()) if isinstance(valor, str) else valor


def minusculas(valor):
    return valor.strip().lower() if isinstance(valor, str) else valor
