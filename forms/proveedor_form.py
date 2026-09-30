from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from validaciones import v_ruc, v_texto, v_telefono
from forms.campos import limpiar


class ProveedorForm(FlaskForm):
    ruc = StringField('RUC', filters=[lambda v: v.strip() if isinstance(v, str) else v], validators=[
        DataRequired(message="El RUC es obligatorio."),
        v_ruc
    ])
    empresa = StringField('Empresa Proveedora', filters=[limpiar], validators=[
        DataRequired(message="El nombre de la empresa es obligatorio."),
        v_texto("El nombre de la empresa", 2, 100)
    ])
    insumo = StringField('Insumo Suministrado', filters=[limpiar], validators=[
        DataRequired(message="El insumo es obligatorio."),
        v_texto("El insumo", 2, 100)
    ])
    telefono = StringField('Teléfono', filters=[lambda v: v.strip() if isinstance(v, str) else v], validators=[
        DataRequired(message="El teléfono es obligatorio."),
        v_telefono
    ])
    submit = SubmitField('Agregar')
