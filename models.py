from flask_login import UserMixin


class Usuario(UserMixin):
    """
    Clase de usuario compatible con Flask-Login.
    Se construye a partir de una fila de la tabla `usuarios`
    (id, usuario, contrasena) obtenida por conexion/conexion.py.
    """

    def __init__(self, id, usuario, contrasena):
        self.id = id
        self.usuario = usuario
        self.contrasena = contrasena
