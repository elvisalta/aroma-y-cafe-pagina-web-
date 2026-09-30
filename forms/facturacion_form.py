from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired


class FacturacionForm(FlaskForm):
    """Cabecera de la factura del administrador. Las líneas (producto + cantidad)
    llegan como listas desde la tabla dinámica y se validan en la ruta /facturacion,
    así una misma factura puede llevar todos los productos que el cliente quiera."""
    cliente = SelectField(
        'Seleccionar Cliente',
        coerce=int,
        validators=[DataRequired(message='Selecciona un cliente')]
    )
    forma_pago = SelectField(
        'Forma de pago',
        choices=[('Efectivo', 'Efectivo'), ('Tarjeta', 'Tarjeta')],
        default='Efectivo',
        validators=[DataRequired(message='Selecciona una forma de pago')]
    )
    submit = SubmitField('Generar Factura')
