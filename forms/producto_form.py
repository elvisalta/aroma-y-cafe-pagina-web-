from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, IntegerField, SubmitField
from wtforms.validators import InputRequired

class ProductoForm(FlaskForm):
    nombre = StringField('Nombre del Producto', validators=[InputRequired(message="El nombre es obligatorio")])
    descripcion = StringField('Descripción', validators=[InputRequired(message="La descripción es obligatoria")])
    precio = DecimalField('Precio ($)', validators=[InputRequired(message="El precio es obligatorio")])
    stock = IntegerField('Stock', validators=[InputRequired(message="El stock es obligatorio")])
    submit = SubmitField('Guardar')