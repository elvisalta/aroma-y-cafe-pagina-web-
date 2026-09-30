let listaDePedidos = [];

const form = document.getElementById('formPedido');
const nombreInput = document.getElementById('nombre');
const descInput = document.getElementById('descripcion');
const catInput = document.getElementById('categoria');
const mensaje = document.getElementById('mensaje');
const listaPedidosUI = document.getElementById('listaPedidos');
const totalRegistrosUI = document.getElementById('totalRegistros');
const spinner = document.getElementById('spinnerCarga');
const modalDetalleEl = document.getElementById('modalDetalle');

// Todo este bloque solo corre si existe el formulario de Pedidos en la página actual
if (form) {
    const modalDetalle = modalDetalleEl ? new bootstrap.Modal(modalDetalleEl) : null;

    function renderizar() {
        listaPedidosUI.innerHTML = '';
        listaDePedidos.forEach((item, index) => {
            const borde = item.categoria === 'Café' ? 'border-success' : 'border-warning';
            const col = document.createElement('div');
            col.className = 'col-md-4 mt-3';
            col.innerHTML = `
                <div class="card p-3 ${borde} border-2">
                    <h5>${item.nombre}</h5>
                    <p>${item.descripcion}</p>
                    <p><strong>Categoría:</strong> ${item.categoria}</p>
                    <div class="d-grid gap-2">
                        <button class="btn btn-primary btn-sm" onclick="verDetalles(${index})">Ver detalles</button>
                        <button class="btn btn-danger btn-sm" onclick="eliminarPedido(${index})">Eliminar</button>
                    </div>
                </div>
            `;
            listaPedidosUI.appendChild(col);
        });
        totalRegistrosUI.innerText = `Total de registros: ${listaDePedidos.length}`;
    }

    window.verDetalles = function(index) {
        const item = listaDePedidos[index];
        document.getElementById('modalBodyContent').innerHTML = `
            <p><strong>Nombre:</strong> ${item.nombre}</p>
            <p><strong>Descripción:</strong> ${item.descripcion}</p>
            <p><strong>Categoría:</strong> ${item.categoria}</p>
        `;
        if (modalDetalle) modalDetalle.show();
    };

    window.eliminarPedido = function(index) {
        listaDePedidos.splice(index, 1);
        renderizar();
    };

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const nombre = nombreInput.value.trim();
        const descripcion = descInput.value.trim();
        const categoria = catInput.value;

        if (nombre === '' || descripcion === '' || categoria === '') {
            mensaje.innerHTML = '<div class="alert alert-danger">Por favor, completa los campos correctamente.</div>';
            return;
        }

        spinner.classList.remove('d-none');

        setTimeout(() => {
            mensaje.innerHTML = '<div class="alert alert-success">Pedido agregado correctamente.</div>';
            listaDePedidos.push({ nombre, descripcion, categoria });
            form.reset();
            spinner.classList.add('d-none');
            renderizar();
        }, 800);
    });
}

// ============================================================
// MENÚ: contador de unidades (+/-) para cada producto
// ============================================================
document.querySelectorAll('.contador-cantidad').forEach(contador => {
    const input = contador.querySelector('.cantidad');

    contador.querySelector('.btn-mas').addEventListener('click', () => {
        // Tope: el stock del producto (atributo max) y nunca más de 100 por compra
        const tope = Math.min(parseInt(input.max) || 1, 100);
        if (parseInt(input.value) < tope) {
            input.value = parseInt(input.value) + 1;
        } else if (window.mostrarToastCarrito) {
            window.mostrarToastCarrito('Solo hay ' + tope + ' unidad(es) disponibles de este producto.', 'info');
        }
    });

    contador.querySelector('.btn-menos').addEventListener('click', () => {
        if (parseInt(input.value) > 1) {
            input.value = parseInt(input.value) - 1;
        }
    });
});

// ============================================================
// CARRITO: helpers globales (usados desde el menú y desde
// cualquier página que agregue productos al carrito)
// ============================================================

// Actualiza la burbuja numérica sobre el ícono del carrito en la navbar
window.actualizarContadorCarrito = function (nuevaCantidad) {
    const burbuja = document.getElementById('badgeCarrito');
    if (!burbuja) return;
    burbuja.textContent = nuevaCantidad;
    burbuja.classList.toggle('d-none', !nuevaCantidad || nuevaCantidad <= 0);
};

// Muestra un toast flotante reutilizando el mismo estilo visual de base.html,
// sin necesidad de recargar la página (los flash de Flask solo aparecen tras un redirect).
window.mostrarToastCarrito = function (mensaje, categoria) {
    const contenedor = document.querySelector('.toast-flotante-contenedor');
    if (!contenedor) return;

    const clasesPorCategoria = {
        success: 'toast-flotante-success',
        danger: 'toast-flotante-danger',
        info: 'toast-flotante-info'
    };
    const iconosPorCategoria = {
        success: '✅',
        danger: '⚠️',
        info: 'ℹ️'
    };
    const clase = clasesPorCategoria[categoria] || 'toast-flotante-warning';
    const icono = iconosPorCategoria[categoria] || '⚠️';

    const toast = document.createElement('div');
    toast.className = 'toast-flotante ' + clase;
    toast.setAttribute('role', 'alert');
    toast.innerHTML =
        '<span class="toast-flotante-icono">' + icono + '</span>' +
        '<span class="toast-flotante-texto"></span>' +
        '<button type="button" class="toast-flotante-cerrar" aria-label="Cerrar">&times;</button>';
    toast.querySelector('.toast-flotante-texto').textContent = mensaje; // textContent evita inyección de HTML

    function cerrar() {
        toast.classList.add('toast-saliendo');
        setTimeout(() => toast.remove(), 350);
    }
    toast.querySelector('.toast-flotante-cerrar').addEventListener('click', cerrar);
    setTimeout(cerrar, 5000);

    contenedor.appendChild(toast);
};