from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email
from validaciones import v_usuario, v_password, v_correo_largo
from forms.campos import minusculas


class UsuarioForm(FlaskForm):
    usuario = StringField('Usuario', filters=[lambda v: v.strip() if isinstance(v, str) else v], validators=[
        DataRequired(message="El usuario es obligatorio."), v_usuario])
    correo = StringField('Correo', filters=[minusculas], validators=[
        DataRequired(message="El correo es obligatorio."),
        Email(message="Ingrese un correo válido."), v_correo_largo])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message="La contraseña es obligatoria."), v_password])
    submit = SubmitField('Guardar')
