from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired

class LoginForm(FlaskForm):
    usuario = StringField('Usuario', validators=[DataRequired()])
    contrasena = PasswordField('Contraseña', validators=[DataRequired()])
    submit = SubmitField('Ingresar')