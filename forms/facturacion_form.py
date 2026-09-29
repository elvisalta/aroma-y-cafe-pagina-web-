from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, SubmitField
from wtforms.validators import DataRequired, NumberRange


class FacturacionForm(FlaskForm):
    cliente = SelectField(
        'Seleccionar Cliente',
        coerce=int,
        validators=[DataRequired(message='Selecciona un cliente')]
    )
    producto = SelectField(
        'Seleccionar Producto',
        coerce=int,
        validators=[DataRequired(message='Selecciona un producto')]
    )
    cantidad = IntegerField(
        'Cantidad',
        default=1,
        validators=[DataRequired(message='Ingresa la cantidad'), NumberRange(min=1, message='La cantidad debe ser mayor a 0')]
    )
    forma_pago = SelectField(
        'Forma de pago',
        choices=[('Efectivo', 'Efectivo'), ('Tarjeta', 'Tarjeta')],
        default='Efectivo',
        validators=[DataRequired(message='Selecciona una forma de pago')]
    )
    submit = SubmitField('Generar Factura')