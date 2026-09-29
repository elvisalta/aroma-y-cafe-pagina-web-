from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email

class UsuarioForm(FlaskForm):
    usuario = StringField('Usuario', validators=[DataRequired(message="El usuario es obligatorio.")])
    correo = StringField('Correo', validators=[DataRequired(message="El correo es obligatorio."), Email(message="Ingrese un correo válido.")])
    password = PasswordField('Contraseña', validators=[DataRequired(message="La contraseña es obligatoria.")])
    submit = SubmitField('Guardar')