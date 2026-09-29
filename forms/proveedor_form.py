from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

class ProveedorForm(FlaskForm):
    empresa = StringField('Empresa Proveedora', validators=[
        DataRequired(message="El nombre de la empresa es obligatorio."),
        Length(min=2, max=100, message="Debe tener entre 2 y 100 caracteres.")
    ])
    insumo = StringField('Insumo Suministrado', validators=[
        DataRequired(message="El insumo es obligatorio."),
        Length(min=2, max=100, message="Debe tener entre 2 y 100 caracteres.")
    ])
    telefono = StringField('Teléfono', validators=[
        DataRequired(message="El teléfono es obligatorio."),
        Length(min=7, max=15, message="Ingrese un teléfono válido.")
    ])
    submit = SubmitField('Guardar')