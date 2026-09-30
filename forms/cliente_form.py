from flask_wtf import FlaskForm
from wtforms import StringField, EmailField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from validaciones import v_cedula_admin, v_nombre_persona, v_telefono, v_correo_largo
from forms.campos import limpiar, minusculas


class ClienteForm(FlaskForm):
    cedula = StringField('Cédula', filters=[lambda v: v.strip() if isinstance(v, str) else v], validators=[
        DataRequired(message="La cédula es obligatoria."),
        v_cedula_admin
    ])
    nombre = StringField('Nombre del Cliente', filters=[limpiar], validators=[
        DataRequired(message="El nombre es obligatorio."),
        v_nombre_persona
    ])
    correo = EmailField('Correo Electrónico', filters=[minusculas], validators=[
        DataRequired(message="El correo es obligatorio."),
        Email(message="Ingrese un correo electrónico válido."),
        v_correo_largo
    ])
    telefono = StringField('Teléfono', filters=[lambda v: v.strip() if isinstance(v, str) else v], validators=[
        DataRequired(message="El teléfono es obligatorio."),
        v_telefono
    ])
    submit = SubmitField('Guardar')
