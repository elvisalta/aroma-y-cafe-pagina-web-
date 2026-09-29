from flask_wtf import FlaskForm
from wtforms import StringField, EmailField, SubmitField
from wtforms.validators import DataRequired, Email, Length

class ClienteForm(FlaskForm):
    cedula = StringField('Cédula', validators=[
        DataRequired(message="La cédula es obligatoria."),
        Length(min=10, max=13, message="La cédula debe tener entre 10 y 13 dígitos.")
    ])
    nombre = StringField('Nombre del Cliente', validators=[
        DataRequired(message="El nombre es obligatorio."),
        Length(min=3, max=100, message="Debe tener entre 3 y 100 caracteres.")
    ])
    correo = EmailField('Correo Electrónico', validators=[
        DataRequired(message="El correo es obligatorio."),
        Email(message="Ingrese un correo electrónico válido.")
    ])
    telefono = StringField('Teléfono', validators=[
        DataRequired(message="El teléfono es obligatorio."),
        Length(min=7, max=15, message="Ingrese un número de teléfono válido.")
    ])
    submit = SubmitField('Guardar')