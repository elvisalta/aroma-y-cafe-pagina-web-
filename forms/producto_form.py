from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField
from wtforms.validators import InputRequired, Optional
from validaciones import v_texto, v_precio, v_stock, validar_precio
from forms.campos import limpiar, EnteroES, DecimalES


class ProductoForm(FlaskForm):
    nombre = StringField('Nombre del Producto', filters=[limpiar], validators=[
        InputRequired(message="El nombre es obligatorio"),
        v_texto("El nombre del producto", 2, 100)
    ])
    descripcion = StringField('Categoría', filters=[limpiar], validators=[
        InputRequired(message="La categoría es obligatoria"),
        v_texto("La categoría", 2, 50)
    ])
    precio = DecimalES('Precio ($)', validators=[
        InputRequired(message="El precio es obligatorio"),
        v_precio
    ])
    stock = EnteroES('Stock', validators=[
        InputRequired(message="El stock es obligatorio"),
        v_stock
    ])
    en_promocion = BooleanField('Poner este producto en promoción')
    precio_promocion = DecimalES('Precio en promoción ($)', validators=[Optional()])
    submit = SubmitField('Guardar')

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators)
        if self.en_promocion.data:
            p = self.precio_promocion.data
            error = None
            if p is None:
                error = 'Si está en promoción, ingresa el precio de promoción.'
            else:
                valido, msg = validar_precio(p)
                if not valido:
                    error = msg
                elif self.precio.data is not None and p >= self.precio.data:
                    error = 'El precio de promoción debe ser menor que el precio normal.'
            if error:
                self.precio_promocion.errors = list(self.precio_promocion.errors) + [error]
                ok = False
        return ok
