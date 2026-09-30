from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Optional
from validaciones import v_cedula, v_nombre_persona, v_telefono, v_correo_largo
from forms.campos import limpiar, minusculas


class CheckoutForm(FlaskForm):
    """Formulario único de facturación usado en la página del carrito.
    Reemplaza al formulario que antes vivía dentro de cada producto:
    ahora el cliente llena sus datos UNA sola vez para todo el pedido.
    """
    cedula = StringField(
        'Cédula o C.I.',
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
        validators=[DataRequired(message="La cédula es obligatoria."), v_cedula]
    )
    nombre = StringField(
        'Nombre completo',
        filters=[limpiar],
        validators=[DataRequired(message="El nombre es obligatorio."), v_nombre_persona]
    )
    correo = StringField(
        'Correo',
        filters=[minusculas],
        validators=[
            DataRequired(message="El correo es obligatorio."),
            Email(message="Correo no válido."),
            v_correo_largo
        ]
    )
    telefono = StringField(
        'Teléfono',
        filters=[lambda v: v.strip() if isinstance(v, str) else v],
        validators=[DataRequired(message="El teléfono es obligatorio."), v_telefono]
    )
    forma_pago = SelectField(
        'Forma de pago',
        choices=[('Efectivo', 'Efectivo'), ('Tarjeta', 'Tarjeta')],
        default='Efectivo',
        validators=[DataRequired(message="Selecciona una forma de pago")]
    )
    # --- Pago en efectivo ---
    efectivo_recibido = StringField('Monto con el que paga', validators=[Optional()])

    # --- Pago con tarjeta (se validan en la ruta solo si forma_pago == 'Tarjeta') ---
    tarjeta_tipo = SelectField(
        'Tipo de tarjeta',
        choices=[('Crédito', 'Crédito'), ('Débito', 'Débito')],
        default='Crédito',
        validators=[Optional()]
    )
    tarjeta_titular = StringField('Titular de la tarjeta', validators=[Optional()])
    tarjeta_numero = StringField('Número de tarjeta', validators=[Optional()])
    tarjeta_vencimiento = StringField('Vencimiento (MM/AA)', validators=[Optional()])
    tarjeta_cvv = StringField('CVV', validators=[Optional()])

    submit = SubmitField('Finalizar compra')
