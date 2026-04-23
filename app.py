# ==========================================================
# IMPORTS PRINCIPALES
# Propósito:
# - Mantener imports limpios
# - Evitar duplicados
# - Incluir lo necesario para permisos, auditoría y exports
# ==========================================================
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, make_response, send_file, abort
)
from models import (
    db, Area, InicioLog, Proveedor, Almacen, Producto,
    InventarioMetal, InventarioProducto, Proceso, Transaccion,
    Cliente, Venta, RolUsuario, Mantenimiento, Maquina, Calidad,
    Vehiculo, Chofer, Envio, ProcesoReciclaje, Embarque,
    Maquinaria, Compra, PedidoVenta, DetallePedido, Auditoria
)

from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import date, datetime, timedelta
from sqlalchemy import func, or_, cast, String, extract, inspect
from fpdf import FPDF
from io import BytesIO
import os
import csv
import io
import json
import pandas as pd

app = Flask(__name__)
app.secret_key = 'hola123' # Necesario para las sesiones

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
mi_contrasena = "Hola123" 
password_segura = quote_plus(mi_contrasena)

# Conexión a PostgreSQL apuntando a la base de datos EcoData
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://postgres:Hola123@localhost:5432/EcoData'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# ==========================================================
# HELPERS GENERALES
# Propósito:
# - Funciones auxiliares para dashboard y auditoría
# ==========================================================
def modelo_tiene_columna(modelo, nombre_columna):
    """
    Verifica si un modelo SQLAlchemy tiene una columna concreta.
    """
    return nombre_columna in [c.key for c in inspect(modelo).mapper.column_attrs]


def registrar_log(accion, modulo, detalle):
    """
    Registra movimiento en la tabla Auditoria usando mapeo dinámico
    para no depender de nombres fijos más allá de los más comunes.
    """
    try:
        registro = Auditoria()
        columnas = {c.key for c in inspect(Auditoria).mapper.column_attrs}
        ahora = datetime.now()
        usuario_actual = session.get('usuario', 'Sistema')

        # ----------------------------------------------
        # Campos comunes del modelo Auditoria
        # ----------------------------------------------
        if 'accion' in columnas:
            registro.accion = accion

        if 'modulo' in columnas:
            registro.modulo = modulo

        if 'detalle' in columnas:
            registro.detalle = detalle
        elif 'descripcion' in columnas:
            registro.descripcion = detalle
        elif 'mensaje' in columnas:
            registro.mensaje = detalle

        if 'usuario' in columnas:
            registro.usuario = usuario_actual
        elif 'nombre_usuario' in columnas:
            registro.nombre_usuario = usuario_actual

        if 'fecha' in columnas:
            registro.fecha = ahora
        elif 'fecha_registro' in columnas:
            registro.fecha_registro = ahora
        elif 'created_at' in columnas:
            registro.created_at = ahora

        if 'ruta' in columnas:
            registro.ruta = request.path if request else None

        if 'metodo' in columnas:
            registro.metodo = request.method if request else None

        if 'ip' in columnas:
            registro.ip = request.remote_addr if request else None

        db.session.add(registro)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print(f"[AUDITORIA] Error al guardar bitácora: {e}")


# ==========================================================
# SEGURIDAD Y PERMISOS
# Propósito:
# - Manejar permisos por rol
# - Evitar bucles de redirección
# - Reutilizar la tabla RolUsuario
# ==========================================================
@app.before_request
def cargar_rol():
    """
    Carga el rol del usuario desde la base en cada request.
    """
    if 'usuario' in session:
        rol_db = RolUsuario.query.filter_by(nombre_usuario=session['usuario']).first()
        session['rol'] = rol_db.rol if rol_db else 'Operador'


PERMISSION_MATRIX = {
    "Administrador": {"*"},

    "Supervisor": {
        "dashboard.ver",
        "productos.ver", "productos.crear", "productos.editar",
        "inventario.ver", "inventario_productos.ver", "almacenes.ver",
        "procesos.ver", "procesos.crear", "procesos.editar",
        "reciclaje.ver", "maquinaria.ver",
        "mantenimiento.ver", "mantenimiento.crear", "mantenimiento.editar",
        "alertas.ver",
        "transporte.ver", "transporte.crear", "transporte.editar",
        "vehiculos.ver", "choferes.ver", "embarques.ver", "dispatch.ver",
        "calidad.ver", "reportes_calidad.ver",
        "compras.ver", "compras.crear", "proveedores.ver", "historial_compras.ver",
        "clientes.ver", "clientes.crear", "clientes.editar",
        "ventas.ver", "ventas.crear",
        "dash_comercial.ver",
        "pedidos.ver", "pedidos.crear", "pedidos.editar",
        "areas.ver", "areas.crear",
        "personal.ver",
        "privilegios.ver",
        "auditoria.ver"
    },

    "Operador": {
        "dashboard.ver",
        "productos.ver",
        "inventario.ver",
        "inventario_productos.ver",
        "procesos.ver",
        "reciclaje.ver",
        "maquinaria.ver",
        "transporte.ver",
        "vehiculos.ver",
        "choferes.ver",
        "embarques.ver",
        "dispatch.ver",
        "clientes.ver",
        "ventas.ver",
        "pedidos.ver"
    },

    "Compras": {
        "dashboard.ver",
        "compras.ver", "compras.crear",
        "proveedores.ver",
        "historial_compras.ver",
        "inventario.ver",
        "embarques.ver"
    },

    "Ventas": {
        "dashboard.ver",
        "dash_comercial.ver",
        "clientes.ver", "clientes.crear", "clientes.editar",
        "ventas.ver", "ventas.crear",
        "pedidos.ver", "pedidos.crear", "pedidos.editar"
    },

    "Logistica": {
        "dashboard.ver",
        "transporte.ver", "transporte.crear", "transporte.editar",
        "vehiculos.ver",
        "choferes.ver",
        "embarques.ver",
        "dispatch.ver",
        "clientes.ver",
        "ventas.ver",
        "pedidos.ver"
    },

    "Produccion": {
        "dashboard.ver",
        "productos.ver",
        "inventario.ver",
        "inventario_productos.ver",
        "procesos.ver", "procesos.crear", "procesos.editar",
        "reciclaje.ver",
        "maquinaria.ver"
    },

    "Mantenimiento": {
        "dashboard.ver",
        "mantenimiento.ver", "mantenimiento.crear", "mantenimiento.editar",
        "alertas.ver",
        "maquinaria.ver"
    },

    "Calidad": {
        "dashboard.ver",
        "calidad.ver",
        "reportes_calidad.ver"
    }
}


def tiene_permiso(permiso):
    """
    Verifica si el rol actual tiene un permiso concreto.
    """
    rol_actual = (session.get("rol") or "Operador").strip()
    permisos_rol = PERMISSION_MATRIX.get(rol_actual, set())

    if "*" in permisos_rol:
        return True

    return permiso in permisos_rol


def registrar_auditoria(modulo, accion, detalle=""):
    """
    Wrapper central de auditoría.
    """
    try:
        usuario = session.get("usuario", "Sistema")
        registrar_log(
            accion,
            modulo,
            f"Usuario={usuario} | Detalle={detalle}"
        )
    except Exception as e:
        print(f"[AUDITORIA] No se pudo registrar movimiento: {e}")


def requiere_permiso(permiso):
    """
    Decorador para proteger rutas por permiso.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario' not in session:
                flash("Por favor, inicia sesión para continuar.", "error")
                return redirect(url_for('login'))

            if not tiene_permiso(permiso):
                flash("No tienes permisos para acceder a este módulo.", "error")
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validar_permiso_accion(permiso, modulo, accion, endpoint_redireccion):
    """
    Valida permisos para acciones POST.
    Retorna un redirect o None.
    """
    if not tiene_permiso(permiso):
        registrar_auditoria(
            modulo,
            f"Bloqueado: {accion}",
            f"Permiso faltante: {permiso}"
        )
        flash("No tienes permisos para realizar esta acción.", "error")
        return redirect(url_for(endpoint_redireccion))
    return None


def admin_required(f):
    """
    Decorador de compatibilidad para secciones exclusivas de administrador.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            flash("Por favor, inicia sesión para continuar.", "error")
            return redirect(url_for('login'))

        if session.get('rol') != 'Administrador':
            flash("Acceso denegado. Esta sección es exclusiva para Administradores.", "error")
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_permission_helpers():
    """
    Expone el helper puede(...) en todos los templates.
    """
    return {
        "puede": tiene_permiso
    }


@app.context_processor
def utilidad_alertas():
    """
    Expone el conteo de alertas para el layout.
    """
    def obtener_conteo():
        try:
            hoy = datetime.now().date()
            ultimos_ids = [
                r[0] for r in db.session.query(
                    func.max(Mantenimiento.id_mantenimiento)
                ).group_by(Mantenimiento.id_maquina).all()
            ]

            if not ultimos_ids:
                return 0

            return Mantenimiento.query.filter(
                Mantenimiento.fecha_proxima <= hoy,
                Mantenimiento.id_mantenimiento.in_(ultimos_ids)
            ).count()
        except Exception:
            return 0

    return dict(global_alertas=obtener_conteo())


@app.route('/auditoria')
@admin_required  # Usamos el decorador que creamos al principio para que solo el admin lo vea
def ver_auditoria():
    # Consultamos todos los registros, los más recientes primero
    registros = Auditoria.query.order_by(Auditoria.fecha.desc()).all()
    return render_template('auditoria.html', registros=registros)

# ==========================================================
# ROUTE: Login
# Propósito:
# - Validar usuario
# - Guardar área y rol en sesión
# - Auditar acceso correcto o fallido
# ==========================================================

# ==========================================================
# ROUTE: Áreas
# Propósito:
# - Mostrar listado de áreas/departamentos
# - Permitir alta de nuevas áreas
# - Respetar el modelo real Area del proyecto
# ==========================================================
@app.route('/areas', methods=['GET', 'POST'])
@requiere_permiso('areas.ver')
def areas():
    # ------------------------------------------------------
    # POST: Registrar nueva área
    # ------------------------------------------------------
    if request.method == 'POST':
        # Comentario:
        # Validamos permiso para crear nuevas áreas.
        permiso_error = validar_permiso_accion(
            'areas.crear',
            'Áreas',
            'Crear área',
            'areas'
        )
        if permiso_error:
            return permiso_error

        # Comentario:
        # Leemos y limpiamos el nombre del área.
        nombre_area = (request.form.get('nombre_area') or '').strip()

        # Comentario:
        # Validación básica del formulario.
        if not nombre_area:
            flash('Debes escribir el nombre del área.', 'error')
            return redirect(url_for('areas'))

        # Comentario:
        # Evitamos duplicados simples por nombre.
        existente = Area.query.filter(
            func.lower(Area.nombre_area) == nombre_area.lower()
        ).first()

        if existente:
            flash('Ya existe un área con ese nombre.', 'warning')
            return redirect(url_for('areas'))

        try:
            # Comentario:
            # Creamos y guardamos la nueva área.
            nueva_area = Area(nombre_area=nombre_area)
            db.session.add(nueva_area)
            db.session.commit()

            # Comentario:
            # Registramos movimiento en auditoría.
            registrar_auditoria(
                "Áreas",
                "Crear",
                f"Área registrada: {nueva_area.nombre_area}"
            )

            flash('Área registrada correctamente.', 'success')

        except Exception as e:
            # Comentario:
            # Si algo falla en la base, revertimos la transacción.
            db.session.rollback()
            flash(f'No se pudo registrar el área: {str(e)}', 'error')

        return redirect(url_for('areas'))

    # ------------------------------------------------------
    # GET: Mostrar listado de áreas
    # ------------------------------------------------------
    areas = Area.query.order_by(Area.nombre_area.asc()).all()

    return render_template(
        'areas.html',
        areas=areas
    )

# ==========================================================
# ROUTE: Login
# Propósito:
# - Validar usuario
# - Crear sesión
# - Redirigir al dashboard
# ==========================================================
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session:
        return redirect(url_for('dashboard'))

    error = None

    if request.method == 'POST':
        usuario_form = request.form.get('usuario')
        password_form = request.form.get('password')

        user_db = InicioLog.query.filter_by(
            usuario=usuario_form,
            contrasena=password_form
        ).first()

        if user_db:
            session['usuario'] = user_db.usuario
            session['id_area'] = user_db.id_area

            if user_db.area:
                session['area_nombre'] = user_db.area.nombre_area
            else:
                session['area_nombre'] = 'Sin Área'

            rol_db = RolUsuario.query.filter_by(nombre_usuario=user_db.usuario).first()
            session['rol'] = rol_db.rol if rol_db else 'Operador'

            registrar_auditoria(
                "Seguridad",
                "Login",
                f"Acceso correcto del usuario {user_db.usuario}"
            )

            return redirect(url_for('dashboard'))

        error = "Usuario o contraseña incorrectos. Intenta de nuevo."

    return render_template('login.html', error=error)
# ==========================================================
# BLOQUE: Dispatch / mapa logístico
# Propósito:
# - Crear y asignar envíos desde el mapa
# - Aplicar filtros avanzados
# - Paginar panel de activos e historial
# - Mostrar resumen rápido operativo
# ==========================================================
@app.route('/dispatch', methods=['GET', 'POST'])
def dispatch_mapa():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        accion = (request.form.get('accion') or '').strip()

        try:
            # ----------------------------------------------------------
            # ACCIÓN: Asignar envío pendiente
            # ----------------------------------------------------------
            if accion == 'asignar_envio':
                id_envio = request.form.get('id_envio', type=int)
                id_vehiculo = request.form.get('id_vehiculo', type=int)
                id_chofer = request.form.get('id_chofer', type=int)

                if not id_envio or not id_vehiculo or not id_chofer:
                    flash('Debes seleccionar envío, vehículo y chofer.', 'warning')
                    return redirect(url_for('dispatch_mapa'))

                envio = Envio.query.get_or_404(id_envio)
                vehiculo = Vehiculo.query.get_or_404(id_vehiculo)
                chofer = Chofer.query.get_or_404(id_chofer)

                if envio.estado_entrega != 'Pendiente':
                    flash('Ese envío ya no está pendiente de asignación.', 'warning')
                    return redirect(url_for('dispatch_mapa'))

                if vehiculo.estado != 'Disponible':
                    flash(f'La unidad {vehiculo.placa} ya no está disponible.', 'danger')
                    return redirect(url_for('dispatch_mapa'))

                otro_envio_activo = Envio.query.filter(
                    Envio.id_venta == envio.id_venta,
                    Envio.id_envio != envio.id_envio,
                    Envio.estado_entrega.in_(['Pendiente', 'En Tránsito'])
                ).first()

                if otro_envio_activo:
                    flash(f'La venta #{envio.id_venta} ya tiene otro envío activo.', 'warning')
                    return redirect(url_for('dispatch_mapa'))

                envio.id_vehiculo = vehiculo.id_vehiculo
                envio.id_chofer = chofer.id_chofer
                envio.estado_entrega = 'En Tránsito'

                if not envio.fecha_salida:
                    envio.fecha_salida = datetime.now()

                vehiculo.estado = 'En Ruta'

                db.session.commit()
                flash(f'Envío #{envio.id_envio} asignado correctamente a {chofer.nombre}.', 'success')
                return redirect(url_for('dispatch_mapa'))

            # ----------------------------------------------------------
            # ACCIÓN: Crear envío pendiente
            # ----------------------------------------------------------
            elif accion == 'crear_envio':
                id_venta = request.form.get('id_venta', type=int)
                destino = (request.form.get('destino') or '').strip()
                latitud = request.form.get('latitud', type=float)
                longitud = request.form.get('longitud', type=float)

                if not id_venta or not destino:
                    flash('Debes indicar la venta y el destino para crear el envío.', 'warning')
                    return redirect(url_for('dispatch_mapa'))

                venta = Venta.query.get(id_venta)
                if not venta:
                    flash(f'La venta #{id_venta} no existe.', 'danger')
                    return redirect(url_for('dispatch_mapa'))

                if venta_tiene_envio_activo(id_venta):
                    flash(f'La venta #{id_venta} ya tiene un envío activo.', 'warning')
                    return redirect(url_for('dispatch_mapa'))

                if (latitud is None or longitud is None) and getattr(venta, 'cliente', None):
                    latitud = venta.cliente.latitud
                    longitud = venta.cliente.longitud

                nuevo_envio = Envio(
                    id_venta=venta.id_venta,
                    destino=destino,
                    latitud=latitud,
                    longitud=longitud,
                    estado_entrega='Pendiente'
                )

                db.session.add(nuevo_envio)
                db.session.commit()

                flash(f'Envío pendiente creado para la venta #{venta.id_venta}.', 'success')
                return redirect(url_for('dispatch_mapa'))

            # ----------------------------------------------------------
            # ACCIÓN: Guardar ubicación del cliente
            # ----------------------------------------------------------
            elif accion == 'guardar_ubicacion_cliente':
                id_cliente = request.form.get('id_cliente', type=int)
                lat = request.form.get('lat', type=float)
                lng = request.form.get('lng', type=float)

                if not id_cliente or lat is None or lng is None:
                    flash('No fue posible guardar la ubicación del cliente.', 'warning')
                    return redirect(url_for('dispatch_mapa'))

                cliente = Cliente.query.get_or_404(id_cliente)
                cliente.latitud = lat
                cliente.longitud = lng

                db.session.commit()
                flash(f'Ubicación guardada para el cliente {cliente.empresa}.', 'success')
                return redirect(url_for('dispatch_mapa'))

            # ----------------------------------------------------------
            # ACCIÓN: Guardar ubicación del almacén
            # ----------------------------------------------------------
            elif accion == 'guardar_ubicacion_almacen':
                id_almacen = request.form.get('id_almacen', type=int)
                lat = request.form.get('lat', type=float)
                lng = request.form.get('lng', type=float)

                if not id_almacen or lat is None or lng is None:
                    flash('No fue posible guardar la ubicación del almacén.', 'warning')
                    return redirect(url_for('dispatch_mapa'))

                almacen = Almacen.query.get_or_404(id_almacen)
                almacen.latitud = lat
                almacen.longitud = lng

                db.session.commit()
                flash(f'Ubicación guardada para el almacén {almacen.nombre_almacen}.', 'success')
                return redirect(url_for('dispatch_mapa'))

            else:
                flash('La acción solicitada no es válida.', 'danger')
                return redirect(url_for('dispatch_mapa'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar la operación de rutas: {str(e)}', 'danger')
            return redirect(url_for('dispatch_mapa'))

    # ==========================================================
    # FILTROS DEL MÓDULO
    # ==========================================================
    filtro_q = (request.args.get('q') or '').strip()
    filtro_vista = (request.args.get('vista') or 'todos').strip()
    filtro_fecha_inicio = (request.args.get('fecha_inicio') or '').strip()
    filtro_fecha_fin = (request.args.get('fecha_fin') or '').strip()
    filtro_id_chofer = request.args.get('id_chofer_filtro', type=int)
    filtro_id_vehiculo = request.args.get('id_vehiculo_filtro', type=int)
    pagina_activos = request.args.get('page_activos', 1, type=int)
    pagina_historial = request.args.get('page_historial', 1, type=int)

    # Catálogos base.
    almacenes = Almacen.query.order_by(Almacen.nombre_almacen.asc()).all()
    clientes = Cliente.query.order_by(Cliente.empresa.asc()).all()
    vehiculos_disponibles = Vehiculo.query.filter_by(estado='Disponible').order_by(Vehiculo.placa.asc()).all()
    vehiculos_filtro = Vehiculo.query.order_by(Vehiculo.placa.asc()).all()
    choferes = Chofer.query.order_by(Chofer.nombre.asc()).all()

    # Conteos globales.
    total_pendientes = Envio.query.filter_by(estado_entrega='Pendiente').count()
    total_activos = Envio.query.filter_by(estado_entrega='En Tránsito').count()
    total_historial = Envio.query.filter_by(estado_entrega='Entregado').count()

    # Consultas base.
    query_pendientes = Envio.query.filter_by(estado_entrega='Pendiente')
    query_activos = Envio.query.filter_by(estado_entrega='En Tránsito')
    query_historial = Envio.query.filter_by(estado_entrega='Entregado')

    # Aplicación de filtros.
    query_pendientes = aplicar_filtros_envios(
        query=query_pendientes,
        texto_busqueda=filtro_q,
        fecha_inicio=filtro_fecha_inicio,
        fecha_fin=filtro_fecha_fin,
        id_chofer=filtro_id_chofer,
        id_vehiculo=filtro_id_vehiculo
    ).order_by(Envio.id_envio.desc())

    query_activos = aplicar_filtros_envios(
        query=query_activos,
        texto_busqueda=filtro_q,
        fecha_inicio=filtro_fecha_inicio,
        fecha_fin=filtro_fecha_fin,
        id_chofer=filtro_id_chofer,
        id_vehiculo=filtro_id_vehiculo
    ).order_by(Envio.fecha_salida.desc(), Envio.id_envio.desc())

    query_historial = aplicar_filtros_envios(
        query=query_historial,
        texto_busqueda=filtro_q,
        fecha_inicio=filtro_fecha_inicio,
        fecha_fin=filtro_fecha_fin,
        id_chofer=filtro_id_chofer,
        id_vehiculo=filtro_id_vehiculo
    ).order_by(Envio.fecha_salida.desc(), Envio.id_envio.desc())

    # Datos completos para el mapa.
    pendientes = query_pendientes.all()
    activos_mapa = query_activos.all()

    # Paginación para panel lateral y tabla de historial.
    paginacion_activos = paginar_query(query_activos, page=pagina_activos, per_page=5)
    activos_panel = paginacion_activos['items']

    paginacion_historial = paginar_query(query_historial, page=pagina_historial, per_page=10)
    historial = paginacion_historial['items']

    # Filtro visual por vista.
    if filtro_vista == 'pendientes':
        activos_mapa = []
        activos_panel = []
        historial = []
    elif filtro_vista == 'activos':
        pendientes = []
        historial = []
    elif filtro_vista == 'historial':
        pendientes = []
        activos_mapa = []
        activos_panel = []

    # Resumen rápido.
    resumen_choferes, resumen_vehiculos = obtener_resumen_operativo_envios()

    return render_template(
        'dispatch.html',
        clientes=clientes,
        pendientes=pendientes,
        activos=activos_mapa,
        activos_panel=activos_panel,
        historial=historial,
        choferes=choferes,
        vehiculos_disponibles=vehiculos_disponibles,
        vehiculos_filtro=vehiculos_filtro,
        almacenes=almacenes,
        total_pendientes=total_pendientes,
        total_activos=total_activos,
        total_historial=total_historial,
        filtro_q=filtro_q,
        filtro_vista=filtro_vista,
        filtro_fecha_inicio=filtro_fecha_inicio,
        filtro_fecha_fin=filtro_fecha_fin,
        filtro_id_chofer=filtro_id_chofer,
        filtro_id_vehiculo=filtro_id_vehiculo,
        pagina_activos=paginacion_activos['page'],
        total_paginas_activos=paginacion_activos['total_pages'],
        total_filtrados_activos=paginacion_activos['total'],
        tiene_anterior_activos=paginacion_activos['has_prev'],
        tiene_siguiente_activos=paginacion_activos['has_next'],
        pagina_historial=paginacion_historial['page'],
        total_paginas_historial=paginacion_historial['total_pages'],
        total_filtrados_historial=paginacion_historial['total'],
        tiene_anterior_historial=paginacion_historial['has_prev'],
        tiene_siguiente_historial=paginacion_historial['has_next'],
        resumen_choferes=resumen_choferes,
        resumen_vehiculos=resumen_vehiculos
    )


# ==========================================================
# FUNCIONES AUXILIARES: Paginación y resumen operativo
# Propósito:
# - Paginar consultas de envíos
# - Obtener resumen rápido por chofer y vehículo
# ==========================================================

def paginar_query(query, page=1, per_page=10):
    """
    Pagina una consulta SQLAlchemy sin depender de helpers externos.
    """
    # Se normalizan valores para evitar páginas inválidas.
    page = page or 1
    per_page = per_page or 10

    if page < 1:
        page = 1

    if per_page < 1:
        per_page = 10

    # Se obtiene el total sin el order_by para evitar conteos innecesariamente pesados.
    total = query.order_by(None).count()
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Si la página pedida supera el total, se ajusta a la última.
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()

    return {
        'items': items,
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages
    }


def obtener_resumen_operativo_envios():
    """
    Obtiene resumen rápido de envíos activos por chofer y por vehículo.
    """
    # Resumen de choferes con más envíos en tránsito.
    resumen_choferes = (
        db.session.query(
            Chofer.id_chofer,
            Chofer.nombre,
            func.count(Envio.id_envio).label('total')
        )
        .join(Envio, Envio.id_chofer == Chofer.id_chofer)
        .filter(Envio.estado_entrega == 'En Tránsito')
        .group_by(Chofer.id_chofer, Chofer.nombre)
        .order_by(func.count(Envio.id_envio).desc(), Chofer.nombre.asc())
        .limit(5)
        .all()
    )

    # Resumen de vehículos con más envíos en tránsito.
    resumen_vehiculos = (
        db.session.query(
            Vehiculo.id_vehiculo,
            Vehiculo.placa,
            Vehiculo.modelo,
            func.count(Envio.id_envio).label('total')
        )
        .join(Envio, Envio.id_vehiculo == Vehiculo.id_vehiculo)
        .filter(Envio.estado_entrega == 'En Tránsito')
        .group_by(Vehiculo.id_vehiculo, Vehiculo.placa, Vehiculo.modelo)
        .order_by(func.count(Envio.id_envio).desc(), Vehiculo.placa.asc())
        .limit(5)
        .all()
    )

    return resumen_choferes, resumen_vehiculos

@app.route('/personal', methods=['GET', 'POST'])
def personal():
    if request.method == 'POST':
        # 1. Recibimos los datos del formulario
        nuevo_usuario = request.form.get('usuario')
        password = request.form.get('password')
        id_area = request.form.get('id_area')
        rol = request.form.get('rol')
        
        # 2. Guardamos el usuario y su contraseña en InicioLog
        nuevo_log = InicioLog(
            usuario=nuevo_usuario, 
            contrasena=password, 
            id_area=id_area
        )
        db.session.add(nuevo_log)
        
        # 3. Le asignamos su Nivel de Acceso en RolUsuario
        nuevo_rol = RolUsuario(
            nombre_usuario=nuevo_usuario,
            rol=rol
        )
        db.session.add(nuevo_rol)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error al registrar personal: {e}"
            
        return redirect(url_for('personal'))
    
    # === Si es método GET (Solo cargar la página) ===
    # Traemos las áreas para llenar el menú desplegable
    areas = Area.query.all()
    
    # Armamos una lista combinando las tablas para que sea fácil leerla en HTML
    usuarios_db = InicioLog.query.all()
    lista_personal = []
    
    for u in usuarios_db:
        # Buscamos el rol de este usuario específico
        rol_obj = RolUsuario.query.filter_by(nombre_usuario=u.usuario).first()
        rol_nombre = rol_obj.rol if rol_obj else 'Sin Rol'
        
        # Si tiene un área asignada, sacamos el nombre
        nombre_area = u.area.nombre_area if u.area else 'Sin Área'
        
        lista_personal.append({
            'id': u.id_usuario,
            'usuario': u.usuario,
            'area': nombre_area,
            'rol': rol_nombre
        })
        
    return render_template('personal.html', areas=areas, personal=lista_personal)

# ==========================================================
# ROUTE: Logout
# Propósito:
# - Cerrar sesión
# - Registrar salida en auditoría
# ==========================================================
# ==========================================================
# ROUTE: Logout
# Propósito:
# - Cerrar sesión
# - Registrar salida en auditoría
# ==========================================================
@app.route('/logout')
def logout():
    if 'usuario' in session:
        registrar_auditoria(
            "Seguridad",
            "Logout",
            f"El usuario {session.get('usuario')} cerró sesión"
        )

    session.clear()
    return redirect(url_for('login'))
# ==========================================================
# ROUTE: Dashboard principal
# Propósito:
# - Pantalla segura de aterrizaje tras el login
# - Mantener KPIs y gráficas
# ==========================================================
@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    alertas = []
    hoy_dt = datetime.now()
    fecha_hoy = hoy_dt.date()
    limite_mantenimiento = fecha_hoy + timedelta(days=7)

    metales_bajos = InventarioMetal.query.filter(InventarioMetal.cantidad_kg <= 500).all()
    for m in metales_bajos:
        alertas.append({
            'nivel': 'peligro' if m.cantidad_kg < 100 else 'advertencia',
            'mensaje': f"Stock crítico de {m.tipo_metal}: {m.cantidad_kg}kg restantes."
        })

    maquinas_prox = Maquinaria.query.filter(
        Maquinaria.proximo_mantenimiento <= limite_mantenimiento
    ).all()

    for maq in maquinas_prox:
        dias = (maq.proximo_mantenimiento - fecha_hoy).days
        msg = f"Mantenimiento de {maq.nombre_equipo} " + (f"en {dias} días" if dias > 0 else "¡ES HOY!")
        alertas.append({
            'nivel': 'peligro' if dias <= 1 else 'advertencia',
            'mensaje': msg
        })

    alertas_abiertas = len(alertas)

    metales = InventarioMetal.query.all()
    total_kilos = sum(m.cantidad_kg for m in metales if m.cantidad_kg)

    productos_inv = InventarioProducto.query.all()
    total_piezas = sum(p.cantidad_stock for p in productos_inv if p.cantidad_stock)

    procesos_activos = Proceso.query.filter_by(estado='En progreso').count()

    dinero_total = db.session.query(func.sum(PedidoVenta.total)).scalar() or 0
    pedidos_pendientes = PedidoVenta.query.filter_by(estado='Pendiente').count()

    choferes_activos = 0
    try:
        if modelo_tiene_columna(Chofer, 'estado'):
            choferes_activos = Chofer.query.filter(func.lower(Chofer.estado) == 'activo').count()
        else:
            choferes_activos = Chofer.query.count()
    except Exception:
        choferes_activos = 0

    unidades_disponibles = 0
    try:
        if modelo_tiene_columna(Vehiculo, 'estado'):
            unidades_disponibles = Vehiculo.query.filter(func.lower(Vehiculo.estado) == 'disponible').count()
        else:
            unidades_disponibles = Vehiculo.query.count()
    except Exception:
        unidades_disponibles = 0

    envios_transito = 0
    try:
        envios_transito = Envio.query.filter(
            func.lower(Envio.estado_entrega).in_(['en tránsito', 'en transito'])
        ).count()
    except Exception:
        envios_transito = 0

    embarques_hoy = 0
    try:
        embarques_hoy = Embarque.query.filter(
            func.date(Embarque.fecha_registro) == fecha_hoy
        ).count()
    except Exception:
        embarques_hoy = 0

    compras_mes = 0
    try:
        compras_mes = Compra.query.filter(
            extract('month', Compra.fecha_compra) == fecha_hoy.month,
            extract('year', Compra.fecha_compra) == fecha_hoy.year
        ).count()
    except Exception:
        compras_mes = 0

    nombres_prod = []
    cantidades_prod = []

    for inv in productos_inv:
        prod = Producto.query.get(inv.id_producto)
        if prod:
            nombres_prod.append(prod.nombre_producto)
            cantidades_prod.append(inv.cantidad_stock)

    tipos_metal = [m.tipo_metal for m in metales]
    kilos_metal = [float(m.cantidad_kg) for m in metales]

    hace_siete_dias = hoy_dt - timedelta(days=7)
    ventas_7_dias = db.session.query(
        func.date(PedidoVenta.fecha_pedido),
        func.sum(PedidoVenta.total)
    ).filter(
        PedidoVenta.fecha_pedido >= hace_siete_dias
    ).group_by(
        func.date(PedidoVenta.fecha_pedido)
    ).all()

    labels_ventas = [v[0].strftime('%d %b') for v in ventas_7_dias]
    valores_ventas = [float(v[1]) for v in ventas_7_dias]

    return render_template(
        'dashboard.html',
        usuario_actual=session['usuario'],
        total_kilos=round(total_kilos, 2),
        total_piezas=total_piezas,
        procesos_activos=procesos_activos,
        dinero_total=round(dinero_total, 2),
        pedidos_pendientes=pedidos_pendientes,
        nombres_prod=nombres_prod,
        cantidades_prod=cantidades_prod,
        tipos_metal=tipos_metal,
        kilos_metal=kilos_metal,
        labels_ventas=labels_ventas,
        valores_ventas=valores_ventas,
        alertas=alertas,
        alertas_abiertas=alertas_abiertas,
        choferes_activos=choferes_activos,
        unidades_disponibles=unidades_disponibles,
        envios_transito=envios_transito,
        embarques_hoy=embarques_hoy,
        compras_mes=compras_mes
    )
# ==========================================================
# BLOQUE: Exportar inventario de metal
# Propósito:
# - Exportar el inventario de materia prima a Excel
# - Usar los nombres reales del proyecto:
#   InventarioMetal, Almacen, Proveedor
# - Descargar el archivo directamente al usuario
# ==========================================================
@app.route('/exportar_inventario')
def exportar_inventario():
    # Validación de sesión para proteger la descarga.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # Se consultan todos los registros del inventario de metal,
    # ordenados del más reciente al más antiguo.
    registros = InventarioMetal.query.order_by(InventarioMetal.fecha_entrada.desc()).all()

    # Se prepara la información para el Excel.
    data = []
    for r in registros:
        data.append({
            "ID Lote": r.id_inventario_m,
            "Tipo de Metal": r.tipo_metal,
            "Cantidad (KG)": r.cantidad_kg,
            "Almacén": r.almacen.nombre_almacen if hasattr(r, 'almacen') and r.almacen else r.id_almacen,
            "Proveedor": r.proveedor.nombre if hasattr(r, 'proveedor') and r.proveedor else r.id_proveedor,
            "Fecha de Entrada": r.fecha_entrada.strftime('%Y-%m-%d') if r.fecha_entrada else ""
        })

    # Si no hay registros, se crea un DataFrame vacío con columnas base
    # para evitar errores al descargar.
    if not data:
        data = [{
            "ID Lote": "",
            "Tipo de Metal": "",
            "Cantidad (KG)": "",
            "Almacén": "",
            "Proveedor": "",
            "Fecha de Entrada": ""
        }]

    # Se convierte a DataFrame de pandas.
    df = pd.DataFrame(data)

    # Se crea el archivo Excel en memoria.
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario Metal')

    output.seek(0)

    # Se envía el archivo al usuario como descarga.
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='Reporte_Inventario_Metal_EcoData.xlsx'
    )

@app.route('/exportar_ventas')
def exportar_ventas():
    # 1. Consultar todos los pedidos (puedes filtrar por fecha si gustas)
    pedidos = PedidoVenta.query.all()
    
    # 2. Crear una lista de diccionarios con la información
    data = []
    for p in pedidos:
        data.append({
            "Folio": f"#{p.id_pedido:04d}",
            "Fecha": p.fecha_pedido.strftime('%Y-%m-%d'),
            "Cliente": p.cliente.nombre_contacto if p.cliente else "N/A",
            "Empresa": p.cliente.empresa if p.cliente else "N/A",
            "Estado": p.estado,
            "Total Venta ($)": p.total
        })
    
    # 3. Convertir a un DataFrame de Pandas
    df = pd.DataFrame(data)
    
    # 4. Crear el archivo Excel en memoria (sin guardarlo en el disco del servidor)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte de Ventas')
    
    output.seek(0)
    
    # 5. Enviar el archivo al usuario
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"Reporte_Ventas_EcoData_{datetime.now().strftime('%Y%m%d')}.xlsx"
    )

# --- MÓDULO BODEGAS (MATERIA PRIMA) ---
@app.route('/bodegas', methods=['GET', 'POST'])
def bodegas():
    # 1. Verificamos que el usuario haya iniciado sesión
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # 2. Si el usuario envía el formulario para guardar chatarra
    if request.method == 'POST':
        # Capturamos los datos del formulario HTML
        id_proveedor = request.form['id_proveedor']
        tipo_metal = request.form['tipo_metal']
        cantidad_kg = request.form['cantidad_kg']
        
        # Opcional: convertimos la fecha del formulario (string) a un objeto Date de Python
        fecha_str = request.form['fecha_ingreso']
        try:
            fecha_ingreso = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            # Si hay error en la fecha, usamos la fecha de hoy por defecto
            fecha_ingreso = datetime.today().date()
            
        # Creamos el nuevo registro en la base de datos
        nuevo_metal = InventarioMetal(
            id_proveedor=id_proveedor, 
            tipo_metal=tipo_metal, 
            cantidad_kg=float(cantidad_kg), 
            fecha_ingreso=fecha_ingreso
        )
        db.session.add(nuevo_metal)
        db.session.commit()
        
        # Refrescamos la página para ver el nuevo registro
        return redirect(url_for('bodegas'))
        
    # 3. Si el usuario solo está viendo la página (GET)
    # Extraemos todos los metales y todos los proveedores de la base de datos
    lista_metales = InventarioMetal.query.all()
    lista_proveedores = Proveedor.query.all()
    
    # Se los enviamos a bodegas.html
    return render_template('bodegas.html', 
                           metales=lista_metales, 
                           proveedores=lista_proveedores)

    # --- NUEVO: Crear un par de Productos de prueba en el catálogo ---
    if not Producto.query.first():
        prod1 = Producto(nombre_producto="Pala de Acero", descripcion="Pala cuadrada uso rudo")
        prod2 = Producto(nombre_producto="Pico de Construcción", descripcion="Pico estándar")
        db.session.add_all([prod1, prod2])
        db.session.commit()
# --- RUTAS NUEVAS PARA LA AUTOMATIZACIÓN Y ALMACENES ---

# 1. RUTA DEL NUEVO MÓDULO DE ALMACENES
@app.route('/almacenes', methods=['GET', 'POST'])
def almacenes():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Usamos nombre_almacen tal como está en tu modelo
        nuevo_almacen = Almacen(
            nombre_almacen=request.form['nombre_almacen'],
            ubicacion=request.form['ubicacion']
        )
        db.session.add(nuevo_almacen)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error al guardar el almacén: {e}"
            
        return redirect(url_for('almacenes'))

    # Traemos la lista de almacenes
    lista_almacenes = Almacen.query.all()
    return render_template('almacenes.html', almacenes=lista_almacenes)



# --- MÓDULO INVENTARIO DE PRODUCTOS TERMINADOS (STOCK) ---
@app.route('/inventario_productos', methods=['GET', 'POST'])
def inventario_productos():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        id_producto = request.form['id_producto']
        id_almacen = request.form['id_almacen']
        cantidad_stock = request.form['cantidad_stock']
        
        # Capturamos la fecha de fabricación del formulario
        fecha_str = request.form['fecha_fabricacion']
        try:
            fecha_fab = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            # Si hay error, usamos la fecha de hoy
            fecha_fab = datetime.today().date()
        
        # Creamos el registro en el inventario con todos tus campos
        nuevo_stock = InventarioProducto(
            id_producto=id_producto,
            id_almacen=id_almacen,
            cantidad_stock=int(cantidad_stock),
            fecha_fabricacion=fecha_fab
        )
        db.session.add(nuevo_stock)
        db.session.commit()
        
        return redirect(url_for('inventario_productos'))
        
    # Mostrar la pantalla con las listas
    lista_inventario = InventarioProducto.query.all()
    lista_productos = Producto.query.all()
    lista_almacenes = Almacen.query.all()
    
    return render_template('inventario_productos.html', 
                           inventario=lista_inventario,
                           productos=lista_productos,
                           almacenes=lista_almacenes)

@app.route('/inventario')
def inventario_metal():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # 1. Obtenemos todo el detalle para la tabla
    registros = InventarioMetal.query.order_by(InventarioMetal.fecha_entrada.desc()).all()

    # 2. Calculamos el Total General en KG
    total_kg = db.session.query(func.sum(InventarioMetal.cantidad_kg)).scalar() or 0

    # 3. Agrupamos los kilos por Tipo de Metal (Para la gráfica y KPIs)
    # Esto nos devolverá una lista como: [('Aluminio', 1500), ('Cobre', 800)]
    resumen_metales = db.session.query(
        InventarioMetal.tipo_metal,
        func.sum(InventarioMetal.cantidad_kg).label('total')
    ).group_by(InventarioMetal.tipo_metal).all()

    # Preparamos los datos para Chart.js
    nombres_metales = [r.tipo_metal for r in resumen_metales]
    cantidades_metales = [r.total for r in resumen_metales]

    return render_template(
        'inventario_metal.html', 
        registros=registros, 
        total_kg=total_kg, 
        resumen_metales=resumen_metales,
        nombres_metales=nombres_metales,
        cantidades_metales=cantidades_metales
    )
@app.route('/productos', methods=['GET', 'POST'])
@requiere_permiso('productos.ver')
def productos():
    if request.method == 'POST':
        permiso_error = validar_permiso_accion(
            'productos.crear',
            'Productos',
            'Crear producto',
            'productos'
        )
        if permiso_error:
            return permiso_error

        nombre_producto = (request.form.get('nombre_producto') or '').strip()
        descripcion = (request.form.get('descripcion') or '').strip()
        precio = request.form.get('precio', type=float)

        nuevo = Producto(
            nombre_producto=nombre_producto,
            descripcion=descripcion,
            precio=precio
        )
        db.session.add(nuevo)
        db.session.commit()

        registrar_auditoria(
            "Productos",
            "Crear",
            f"Producto registrado: {nuevo.nombre_producto}"
        )

        flash('Producto registrado correctamente.', 'success')
        return redirect(url_for('productos'))

    productos = Producto.query.order_by(Producto.id_producto.desc()).all()
    return render_template('productos.html', productos=productos)

# ==========================================================
# ROUTE: Editar producto
# Propósito:
# - Actualizar nombre, descripción y precio del producto
# - Auditar la edición
# ==========================================================
@app.route('/editar_producto/<int:id_producto>', methods=['POST'])
@requiere_permiso('productos.editar')
def editar_producto(id_producto):
    producto = Producto.query.get_or_404(id_producto)

    producto.nombre_producto = (request.form.get('nombre_producto') or '').strip()
    producto.descripcion = (request.form.get('descripcion') or '').strip()
    producto.precio = request.form.get('precio', type=float)

    db.session.commit()

    registrar_auditoria(
        "Productos",
        "Editar",
        f"Producto actualizado: ID={producto.id_producto} | Nombre={producto.nombre_producto}"
    )

    flash('Producto actualizado correctamente.', 'success')
    return redirect(url_for('productos'))
@app.context_processor
def utilidad_alertas():
    def obtener_conteo():
        hoy = datetime.now().date()
        ultimos_ids = [r[0] for r in db.session.query(func.max(Mantenimiento.id_mantenimiento)).group_by(Mantenimiento.id_maquina).all()]
        return Mantenimiento.query.filter(Mantenimiento.fecha_proxima <= hoy, Mantenimiento.id_mantenimiento.in_(ultimos_ids)).count()
    return dict(conteo_alertas=obtener_conteo())

@app.route('/mantenimiento', methods=['GET', 'POST'])
@requiere_permiso('mantenimiento.ver')
def mantenimiento():
    hoy = datetime.now().date()

    if request.method == 'POST':
        permiso_error = validar_permiso_accion(
            'mantenimiento.crear',
            'Mantenimiento',
            'Registrar mantenimiento',
            'mantenimiento'
        )
        if permiso_error:
            return permiso_error

        accion = request.form.get('accion')

        if accion == 'registrar_mantenimiento':
            file = request.files.get('foto')
            nombre_foto_db = None

            if file and file.filename != '':
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = secure_filename(file.filename)
                nombre_foto_db = f"{timestamp}_{filename}"

                # Asegura carpeta de upload
                upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join('static', 'evidencias'))
                os.makedirs(upload_folder, exist_ok=True)
                app.config['UPLOAD_FOLDER'] = upload_folder

                file.save(os.path.join(upload_folder, nombre_foto_db))

            id_maquina = request.form.get('id_maquina', type=int)
            tipo = request.form.get('tipo')
            descripcion = request.form.get('descripcion')
            fecha = datetime.strptime(request.form.get('fecha'), '%Y-%m-%d')
            fecha_proxima_str = request.form.get('fecha_proxima')
            fecha_proxima = datetime.strptime(fecha_proxima_str, '%Y-%m-%d') if fecha_proxima_str else None
            costo = float(request.form.get('costo') or 0)
            tecnico = request.form.get('tecnico')

            nuevo = Mantenimiento(
                id_maquina=id_maquina,
                tipo=tipo,
                descripcion=descripcion,
                fecha=fecha,
                fecha_proxima=fecha_proxima,
                costo=costo,
                tecnico=tecnico,
                foto_evidencia=nombre_foto_db
            )

            maquina = Maquina.query.get(id_maquina)
            if maquina:
                maquina.estado = 'Operativa' if tipo == 'Preventivo' else 'En Reparación'

            db.session.add(nuevo)
            db.session.commit()

            registrar_auditoria(
                "Mantenimiento",
                "Crear",
                f"Mantenimiento registrado para máquina ID={id_maquina}"
            )

            flash("Registro guardado con éxito", "success")
            return redirect(url_for('mantenimiento'))

    maquinas = Maquina.query.all()
    historial = Mantenimiento.query.order_by(Mantenimiento.fecha.desc()).all()
    gasto_mes = db.session.query(
        db.func.sum(Mantenimiento.costo)
    ).filter(
        db.func.extract('month', Mantenimiento.fecha) == hoy.month
    ).scalar() or 0

    return render_template(
        'mantenimiento.html',
        maquinas=maquinas,
        historial=historial,
        gasto_mes=gasto_mes,
        hoy=hoy
    )

@app.route('/mantenimiento/atender/<int:id_maquina>')
def atender_orden(id_maquina):
    maquina = Maquina.query.get_or_404(id_maquina)
    ultimo = Mantenimiento.query.filter_by(id_maquina=id_maquina).order_by(Mantenimiento.fecha.desc()).first()
    return render_template('atender_orden.html', maquina=maquina, ultimo=ultimo, hoy=datetime.now().date())
@app.route('/mantenimiento/alertas')
def alertas_criticas():
    hoy = datetime.now().date()
    
    # 1. Obtenemos los IDs de los mantenimientos más recientes de cada máquina
    ultimos_ids = [r[0] for r in db.session.query(
        func.max(Mantenimiento.id_mantenimiento)
    ).group_by(Mantenimiento.id_maquina).all()]
    alertas = Mantenimiento.query.filter(
        Mantenimiento.fecha_proxima <= hoy,
        Mantenimiento.id_mantenimiento.in_(ultimos_ids)
    ).all()

    return render_template('alertas_mantenimiento.html', alertas=alertas, hoy=hoy)

# 3. RUTA DE AUTOMATIZACIÓN DE PROCESOS (Opción B)
@app.route('/completar_proceso/<int:id>', methods=['POST'])
def completar_proceso(id):
    if 'usuario' not in session: return redirect(url_for('login'))
    
    proceso = Proceso.query.get_or_404(id)
    kg_usados = float(request.form['kg_usados'])
    piezas_creadas = int(request.form['piezas_creadas'])
    
    # PASO 1: Restar el metal del inventario de Materia Prima
    lote_metal = InventarioMetal.query.get(proceso.id_inventario_m)
    if lote_metal.cantidad_kg >= kg_usados:
        lote_metal.cantidad_kg -= kg_usados
    else:
        flash('Error: No hay suficiente metal en este lote para esta fabricación.', 'error')
        return redirect(url_for('procesos'))
        
    # PASO 2: Sumar las herramientas creadas al Inventario de Productos
    id_almacen = lote_metal.id_almacen # Se guarda en el mismo almacén donde estaba el metal
    inv_prod = InventarioProducto.query.filter_by(id_producto=proceso.id_producto, id_almacen=id_almacen).first()
    
    if inv_prod:
        inv_prod.cantidad_stock += piezas_creadas
        inv_prod.fecha_fabricacion = date.today()
    else:
        nuevo_inv = InventarioProducto(id_producto=proceso.id_producto, id_almacen=id_almacen, cantidad_stock=piezas_creadas, fecha_fabricacion=date.today())
        db.session.add(nuevo_inv)
        
    # PASO 3: Marcar el proceso como Terminado
    proceso.estado = 'Terminado'
    db.session.commit()
    
    flash('¡Fabricación exitosa! Se restó el metal y se sumaron los productos automáticamente.', 'success')
    return redirect(url_for('procesos'))
# --- MÓDULO PROCESOS DE FABRICACIÓN ---
# --- MÓDULO PROCESOS DE FABRICACIÓN ---
@app.route('/procesos', methods=['GET', 'POST'])
def procesos():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre_proceso = request.form['nombre_proceso']
        id_inventario_m = request.form['id_inventario_m']
        id_producto = request.form['id_producto']
        
        # Procesamos la fecha
        fecha_str = request.form['fecha_inicio']
        try:
            fecha_inicio = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_inicio = datetime.today().date()
            
        # Creamos el proceso (El "estado" se pone solo como 'En progreso' gracias a tu modelo)
        nuevo_proceso = Proceso(
            nombre_proceso=nombre_proceso,
            id_inventario_m=id_inventario_m,
            id_producto=id_producto,
            fecha_inicio=fecha_inicio
        )
        db.session.add(nuevo_proceso)
        db.session.commit()
        
        return redirect(url_for('procesos'))
        
    # Extraemos procesos, y también metales y productos para los menús desplegables
    lista_procesos = Proceso.query.all()
    lista_metales = InventarioMetal.query.all()
    lista_productos = Producto.query.all()
    
    return render_template('procesos.html', 
                           procesos=lista_procesos,
                           metales=lista_metales,
                           productos=lista_productos)

# Ruta rápida para cambiar el estado del proceso a "Completado"
@app.route('/finalizar_proceso/<int:id_proceso>')
def finalizar_proceso(id_proceso):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # Buscamos el proceso por su ID y le cambiamos el estado
    proceso = Proceso.query.get(id_proceso)
    if proceso:
        proceso.estado = 'Completado'
        db.session.commit()
        
    return redirect(url_for('procesos'))
@app.route('/maquinaria', methods=['GET', 'POST'])
def maquinaria():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        nueva_maquina = Maquina(
            nombre=request.form['nombre'],
            modelo=request.form['modelo'], # <-- Aquí cambiamos 'tipo' por 'modelo'
            estado=request.form.get('estado', 'Operativa')
        )
        db.session.add(nueva_maquina)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error al guardar la máquina: {e}"
            
        return redirect(url_for('maquinaria'))

    lista_maquinas = Maquina.query.all()
    return render_template('maquinaria.html', maquinas=lista_maquinas)

@app.route('/actualizar_maquina/<int:id_maquina>', methods=['POST'])
def actualizar_maquina(id_maquina):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    maquina = Maquina.query.get_or_404(id_maquina)
    nuevo_estado = request.form['estado']
    maquina.estado = nuevo_estado
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return f"Error al actualizar estado: {e}"
        
    return redirect(url_for('maquinaria'))


# --- MÓDULO DE ADMINISTRACIÓN CONTABLE ---
@app.route('/contabilidad', methods=['GET', 'POST'])
@admin_required
def contabilidad():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    # Candado de seguridad para Contabilidad
    if session.get('rol') != 'Administrador':
        flash('Acceso restringido. No tienes permisos para ver las finanzas.', 'error')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        tipo = request.form['tipo']
        concepto = request.form['concepto']
        monto = float(request.form['monto'])
        fecha = request.form['fecha_transaccion']
        
        # Guardar el nuevo registro financiero
        nueva_transaccion = Transaccion(
            tipo=tipo,
            concepto=concepto,
            monto=monto,
            fecha_transaccion=fecha
        )
        db.session.add(nueva_transaccion)
        db.session.commit()
        
        flash('Transacción registrada exitosamente.', 'success')
        return redirect(url_for('contabilidad'))
        
    # Consultar todas las transacciones (ordenadas por fecha, las más nuevas primero)
    transacciones = Transaccion.query.order_by(Transaccion.fecha_transaccion.desc()).all()
    
    # Calcular Totales Matemáticamente
    total_ingresos = sum(t.monto for t in transacciones if t.tipo == 'Ingreso')
    total_egresos = sum(t.monto for t in transacciones if t.tipo == 'Egreso')
    balance = total_ingresos - total_egresos
    
    return render_template('contabilidad.html', 
                           transacciones=transacciones, 
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           balance=balance,
                           usuario_actual=session['usuario'])

@app.route('/procesar_carrito', methods=['POST'])
def procesar_carrito():
    datos_carrito_json = request.form.get('datos_carrito')
    id_proveedor = request.form.get('id_proveedor')
    folio_factura = request.form.get('folio_factura')
    
    if not id_proveedor:
        return "Error: Debes seleccionar un proveedor para realizar la compra.", 400

    carrito = json.loads(datos_carrito_json)
    
    # Buscamos el primer almacén disponible para meter la chatarra ahí.
    # (Si aún no tienes almacenes en la BD, asignamos el ID 1 por defecto).
    almacen = Almacen.query.first()
    id_almacen_destino = almacen.id_almacen if almacen else 1
    
    for item in carrito:
        cantidad_comprada = float(item['cantidad'])
        precio = float(item['precio'])
        nombre_producto = item['nombre']
        
        subtotal = cantidad_comprada * precio
        iva = subtotal * 0.16
        total = subtotal + iva
        
        # 1. Guardamos el ticket en la tabla COMPRA
        nueva_compra = Compra(
            id_proveedor=id_proveedor,
            producto=nombre_producto,
            cantidad=cantidad_comprada,
            precio_unitario=precio,
            subtotal=subtotal,
            iva=iva,
            total=total,
            folio_factura=folio_factura if folio_factura else 'Sin Factura',
            estado='Pagada'
        )
        db.session.add(nueva_compra)

        # ==========================================
        # 2. LÓGICA DE INVENTARIO (Usando tus modelos)
        # ==========================================
        # Registramos la entrada de este lote específico de metal
        nuevo_lote_metal = InventarioMetal(
            id_almacen=id_almacen_destino,
            id_proveedor=id_proveedor,
            tipo_metal=nombre_producto,
            cantidad_kg=cantidad_comprada,
            fecha_entrada=datetime.now().date()
        )
        db.session.add(nuevo_lote_metal)
        # ==========================================
        
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return f"Error al guardar la compra o actualizar inventario: {e}"
        
    return redirect(url_for('compras'))

@app.route('/historial_compras')
def historial_compras():
    # Buscamos todas las compras en la base de datos
    # Las ordenamos de la más reciente a la más antigua (descendente)
    todas_las_compras = Compra.query.order_by(Compra.id_compra.desc()).all()
    
    return render_template('historial_compras.html', compras=todas_las_compras)

@app.route('/ventas', methods=['GET', 'POST'])
@requiere_permiso('ventas.ver')
def ventas():
    if request.method == 'POST':
        permiso_error = validar_permiso_accion(
            'ventas.crear',
            'Ventas',
            'Crear venta',
            'ventas'
        )
        if permiso_error:
            return permiso_error

        id_cliente = request.form.get('id_cliente', type=int)
        id_producto = request.form.get('id_producto', type=int)
        cantidad = request.form.get('cantidad', type=int)
        total_venta = request.form.get('total_venta', type=float)
        fecha_venta = request.form.get('fecha_venta')

        nueva_venta = Venta(
            id_cliente=id_cliente,
            id_producto=id_producto,
            cantidad=cantidad,
            total_venta=total_venta,
            fecha_venta=fecha_venta
        )
        db.session.add(nueva_venta)
        db.session.commit()

        registrar_auditoria(
            "Ventas",
            "Crear",
            f"Venta registrada: Cliente={id_cliente} | Producto={id_producto} | Total={total_venta}"
        )

        flash('Venta registrada correctamente.', 'success')
        return redirect(url_for('ventas'))

    ventas = Venta.query.order_by(Venta.id_venta.desc()).all()
    clientes = Cliente.query.order_by(Cliente.empresa.asc()).all()
    productos = Producto.query.order_by(Producto.nombre_producto.asc()).all()

    return render_template(
        'ventas.html',
        ventas=ventas,
        clientes=clientes,
        productos=productos
    )

@app.route('/dash_comercial')
def dash_comercial():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # 1. Total histórico de ingresos
    ingresos_totales = db.session.query(func.sum(Venta.total_venta)).scalar() or 0
    
    # 2. Ticket Promedio (Venta promedio)
    num_ventas = Venta.query.count()
    ticket_promedio = ingresos_totales / num_ventas if num_ventas > 0 else 0
    
    # 3. Datos para gráfica: Ventas por Cliente (Empresa)
    ventas_clientes = db.session.query(
        Cliente.empresa, 
        func.sum(Venta.total_venta)
    ).join(Venta).group_by(Cliente.empresa).all()
    
    labels_clientes = [v[0] for v in ventas_clientes]
    values_dinero = [v[1] for v in ventas_clientes]

    return render_template('dash_comercial.html', 
                           ingresos=ingresos_totales,
                           ticket=ticket_promedio,
                           num_ventas=num_ventas,
                           labels_cli=labels_clientes,
                           values_dinero=values_dinero)

@app.route('/compras', methods=['GET', 'POST'])
def compras():
    if request.method == 'POST':
        id_proveedor = request.form.get('id_proveedor')
        producto = request.form.get('producto')
        cantidad = float(request.form.get('cantidad'))
        precio_unitario = float(request.form.get('precio_unitario'))
        folio_factura = request.form.get('folio_factura')
        estado = request.form.get('estado')

        # Matemáticas financieras automáticas
        subtotal = cantidad * precio_unitario
        iva = subtotal * 0.16  # Cambia a 0.08 si estás en zona fronteriza
        total = subtotal + iva

        nueva_compra = Compra(
            id_proveedor=id_proveedor,
            producto=producto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            subtotal=subtotal,
            iva=iva,
            total=total,
            folio_factura=folio_factura if folio_factura else 'Sin Factura',
            estado=estado
        )
        
        db.session.add(nueva_compra)
        
        try:
            db.session.commit()
            registrar_auditoria(
            "Compras",
            "Compra",
            f"Compra de {producto} ({cantidad} unidades) por un total de ${total:,.2f}"
            )
        except Exception as e:
            db.session.rollback()
            return f"Error al registrar la compra: {e}"
            
        return redirect(url_for('compras'))

    # Para el método GET: Traemos las compras y los proveedores para el menú
    lista_compras = Compra.query.order_by(Compra.fecha_compra.desc()).all()
    lista_proveedores = Proveedor.query.all()
    
    return render_template('compras.html', compras=lista_compras, proveedores=lista_proveedores)

# --- MÓDULO DIRECTORIO DE CLIENTES ---
@app.route('/clientes', methods=['GET', 'POST'])
def clientes():
    # 1. Verificamos sesión
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # 2. Si el usuario llena el formulario de nuevo cliente
    if request.method == 'POST':
        # Capturamos los datos según tu modelo específico
        empresa = request.form['empresa']
        nombre_contacto = request.form['nombre_contacto']
        telefono = request.form.get('telefono', '')
        
        nuevo_cliente = Cliente(
            empresa=empresa, 
            nombre_contacto=nombre_contacto, 
            telefono=telefono
        )
        
        try:
            db.session.add(nuevo_cliente)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error al guardar cliente: {e}")
            
        return redirect(url_for('clientes'))
        
    # 3. Si solo entra a ver la página, listamos los clientes
    lista_clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=lista_clientes)

# --- RUTA PARA GENERAR NOTA DE VENTA EN PDF ---
@app.route('/descargar_nota/<int:id_venta>')
def descargar_nota(id_venta):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # Buscamos la venta y sus relaciones (cliente/producto)
    venta = Venta.query.get_or_404(id_venta)
    
    # Configuración del PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 18)
    
    # Encabezado
    pdf.cell(190, 15, "ECODATA ERP - NOTA DE VENTA", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", '', 10)
    pdf.cell(190, 5, "Comprobante de operación interna", ln=True, align='C')
    pdf.ln(10)
    
    # Información del Cliente y Venta
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(40, 10, "Cliente:", 0)
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 10, f"{venta.cliente.empresa}")
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(20, 10, "Folio:", 0)
    pdf.set_font("Arial", '', 12)
    pdf.cell(30, 10, f"#00{venta.id_venta}", ln=True)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(40, 10, "Atención:", 0)
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 10, f"{venta.cliente.nombre_contacto}")
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(20, 10, "Fecha:", 0)
    pdf.set_font("Arial", '', 12)
    pdf.cell(30, 10, f"{venta.fecha_venta}", ln=True)
    
    pdf.ln(15)
    
    # Tabla de Productos
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Descripción del Producto", 1, 0, 'C', True)
    pdf.cell(40, 10, "Cantidad", 1, 0, 'C', True)
    pdf.cell(50, 10, "Total", 1, 1, 'C', True)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 10, f" {venta.producto.nombre_producto}", 1)
    pdf.cell(40, 10, f"{venta.cantidad} pzas", 1, 0, 'C')
    pdf.cell(50, 10, f"${venta.total_venta}", 1, 1, 'R')
    
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 10, f"TOTAL PAGADO: ${venta.total_venta}", 0, 1, 'R')
    
    # Generar la respuesta
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers.set('Content-Disposition', 'attachment', filename=f'Nota_Venta_{venta.id_venta}.pdf')
    response.headers.set('Content-Type', 'application/pdf')
    
    return response

# --- MÓDULO DIRECTORIO DE PROVEEDORES ---
@app.route('/proveedores', methods=['GET', 'POST'])
def proveedores():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre = request.form['nombre']
        telefono = request.form.get('telefono', '') # Si no hay teléfono, guarda texto vacío
        
        nuevo_prov = Proveedor(nombre=nombre, telefono=telefono)
        db.session.add(nuevo_prov)
        db.session.commit()
        
        return redirect(url_for('proveedores'))
        
    lista_proveedores = Proveedor.query.all()
    return render_template('proveedores.html', 
                           proveedores=lista_proveedores, 
                           usuario_actual=session['usuario'])

@app.route('/calidad', methods=['GET', 'POST'])
def calidad():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Capturamos los datos del formulario
        id_prod = request.form.get('id_producto')
        estado = request.form.get('resultado')
        detalles = request.form.get('parametros')
        obs = request.form.get('observaciones')
        
        # Creamos el registro usando el modelo que ya importamos
        nueva_inspeccion = Calidad(
            id_producto=id_prod,
            fecha_inspeccion=datetime.now().date(), # Fecha automática
            inspector=session.get('usuario'),       # Inspector automático
            resultado=estado,
            parametros_tecnicos=detalles,
            observaciones=obs
        )

        try:
            db.session.add(nueva_inspeccion)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error al registrar inspección: {e}"

        return redirect(url_for('calidad'))

    # Para el GET: traemos productos e historial
    productos = Producto.query.all()
    historial = Calidad.query.order_by(Calidad.id_inspeccion.desc()).all()
    return render_template('calidad.html', productos=productos, historial=historial)

@app.route('/reportes_calidad')
def reportes_calidad():
    # 1. Seguridad: Solo usuarios logueados pueden ver reportes
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # 2. Consultamos todos los registros de calidad
    # Usamos .options(db.joinedload(Calidad.producto)) para cargar el nombre del producto eficientemente
    historial = Calidad.query.order_by(Calidad.fecha_inspeccion.desc()).all()

    # 3. Renderizamos el template de reportes
    return render_template('reportes_calidad.html', historial=historial)


# ==========================================================
# BLOQUE: Reciclaje y fundición
# Propósito:
# - Mostrar la vista de reciclaje
# - Registrar nuevos lotes
# - Finalizar procesos con peso de salida
# - Calcular merma automáticamente
# ==========================================================

@app.route('/reciclaje', methods=['GET', 'POST'])
def reciclaje():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Se leen los datos exactamente con los nombres que usa tu HTML.
        lote = (request.form.get('lote') or '').strip()
        metal_origen = (request.form.get('metal_origen') or '').strip()
        peso_entrada = request.form.get('peso_entrada', type=float)
        id_maquina = request.form.get('id_maquina', type=int)

        # Validaciones básicas del formulario.
        if not lote or not metal_origen or peso_entrada is None or not id_maquina:
            flash('Completa todos los campos del proceso de reciclaje.', 'warning')
            return redirect(url_for('reciclaje'))

        if peso_entrada <= 0:
            flash('El peso de entrada debe ser mayor a cero.', 'warning')
            return redirect(url_for('reciclaje'))

        # Se valida que la máquina exista.
        maquina = Maquina.query.get_or_404(id_maquina)

        try:
            # Se crea el lote de reciclaje.
            # IMPORTANTE:
            # Aquí se respetan los nombres de campos que usa tu plantilla:
            # lote, metal_origen, peso_entrada_kg, id_maquina, estado
            nuevo_proceso = ProcesoReciclaje(
                lote=lote,
                metal_origen=metal_origen,
                peso_entrada_kg=peso_entrada,
                id_maquina=id_maquina,
                estado='En proceso'
            )

            db.session.add(nuevo_proceso)
            db.session.commit()

            flash(f'Lote {lote} registrado correctamente.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'No fue posible registrar el lote: {str(e)}', 'danger')

        return redirect(url_for('reciclaje'))

    # Se cargan máquinas y procesos para la vista.
    maquinas = Maquina.query.order_by(Maquina.nombre.asc()).all()
    procesos = ProcesoReciclaje.query.order_by(ProcesoReciclaje.id_proceso.desc()).all()

    return render_template(
        'reciclaje.html',
        maquinas=maquinas,
        procesos=procesos
    )


# ==========================================================
# BLOQUE: Finalizar reciclaje
# Propósito:
# - Registrar peso final del lote
# - Calcular merma
# - Marcar el proceso como completado
# ==========================================================
@app.route('/finalizar_reciclaje/<int:id_proceso>', methods=['POST'])
def finalizar_reciclaje(id_proceso):
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    proceso = ProcesoReciclaje.query.get_or_404(id_proceso)

    # Se toma el peso de salida enviado desde el formulario.
    peso_salida = request.form.get('peso_salida', type=float)

    # Validaciones básicas.
    if peso_salida is None:
        flash('Debes capturar el peso de salida.', 'warning')
        return redirect(url_for('reciclaje'))

    if peso_salida <= 0:
        flash('El peso de salida debe ser mayor a cero.', 'warning')
        return redirect(url_for('reciclaje'))

    if peso_salida > proceso.peso_entrada_kg:
        flash('El peso de salida no puede ser mayor al peso de entrada.', 'danger')
        return redirect(url_for('reciclaje'))

    try:
        # Se actualiza el proceso respetando los nombres de campos esperados en la vista.
        proceso.peso_salida_kg = peso_salida
        proceso.merma_kg = proceso.peso_entrada_kg - peso_salida
        proceso.estado = 'Completado'

        db.session.commit()

        flash(
            f'Proceso {proceso.lote} finalizado. Merma calculada: {proceso.merma_kg:.2f} kg.',
            'success'
        )

    except Exception as e:
        db.session.rollback()
        flash(f'No fue posible finalizar el proceso: {str(e)}', 'danger')

    return redirect(url_for('reciclaje'))

# ==========================================================
# BLOQUE: Logística, transporte, embarques y pedidos
# Propósito:
# - Mejorar validaciones del módulo
# - Evitar envíos duplicados
# - Corregir altas/bajas de items en pedidos
# - Corregir embarques y pesos de báscula
# ==========================================================

# Función auxiliar para recalcular el total del pedido.
# Esto evita que el total quede desfasado al agregar o eliminar productos.
def recalcular_total_pedido(pedido):
    pedido.total = sum(
        (item.cantidad or 0) * (item.precio_unitario or 0)
        for item in pedido.detalles
    )
def obtener_ids_ventas_con_envio_activo():
    """
    Obtiene los IDs de ventas que tienen un envío todavía activo.
    Se consideran activos los estados:
    - Pendiente
    - En Tránsito
    """
    filas = db.session.query(Envio.id_venta).filter(
        Envio.id_venta.isnot(None),
        Envio.estado_entrega.in_(['Pendiente', 'En Tránsito'])
    ).all()

    return [fila[0] for fila in filas if fila[0] is not None]

# ==========================================================
# FUNCIÓN AUXILIAR: Aplicar filtros a envíos
# Propósito:
# - Filtrar por texto libre
# - Filtrar por fecha de salida
# - Filtrar por chofer y vehículo
# - Reutilizar lógica entre transporte y dispatch
# ==========================================================
def aplicar_filtros_envios(
    query,
    texto_busqueda='',
    fecha_inicio='',
    fecha_fin='',
    id_chofer=None,
    id_vehiculo=None
):
    # Se agregan joins para poder buscar por nombre de chofer y placa.
    query = query.outerjoin(Chofer, Envio.id_chofer == Chofer.id_chofer)
    query = query.outerjoin(Vehiculo, Envio.id_vehiculo == Vehiculo.id_vehiculo)

    # ----------------------------------------------------------
    # FILTRO 1: Búsqueda libre
    # ----------------------------------------------------------
    if texto_busqueda:
        patron = f"%{texto_busqueda.strip()}%"

        query = query.filter(
            or_(
                cast(Envio.id_envio, String).ilike(patron),
                cast(Envio.id_venta, String).ilike(patron),
                Envio.destino.ilike(patron),
                Chofer.nombre.ilike(patron),
                Vehiculo.placa.ilike(patron)
            )
        )

    # ----------------------------------------------------------
    # FILTRO 2: Fecha inicial
    # ----------------------------------------------------------
    if fecha_inicio:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            query = query.filter(Envio.fecha_salida >= fecha_inicio_dt)
        except ValueError:
            pass

    # ----------------------------------------------------------
    # FILTRO 3: Fecha final
    # Se suma un día para incluir todo el día final seleccionado.
    # ----------------------------------------------------------
    if fecha_fin:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Envio.fecha_salida < fecha_fin_dt)
        except ValueError:
            pass

    # ----------------------------------------------------------
    # FILTRO 4: Chofer
    # ----------------------------------------------------------
    if id_chofer:
        query = query.filter(Envio.id_chofer == id_chofer)

    # ----------------------------------------------------------
    # FILTRO 5: Vehículo
    # ----------------------------------------------------------
    if id_vehiculo:
        query = query.filter(Envio.id_vehiculo == id_vehiculo)

    return query

def venta_tiene_envio_activo(id_venta):
    """
    Indica si una venta ya tiene un envío activo.
    """
    envio = Envio.query.filter(
        Envio.id_venta == id_venta,
        Envio.estado_entrega.in_(['Pendiente', 'En Tránsito'])
    ).first()

    return envio is not None


def liberar_vehiculo_de_envio(envio):
    """
    Libera el vehículo asociado a un envío, dejándolo disponible nuevamente.
    """
    if not envio or not envio.id_vehiculo:
        return

    vehiculo = Vehiculo.query.get(envio.id_vehiculo)
    if vehiculo:
        vehiculo.estado = 'Disponible'


def marcar_envio_como_entregado(envio):
    """
    Marca un envío como entregado y libera su vehículo.
    """
    if not envio:
        return

    envio.estado_entrega = 'Entregado'
    liberar_vehiculo_de_envio(envio)

# ==========================================================
# BLOQUE: Transporte
# Propósito:
# - Registrar envíos directos
# - Mantener sincronía con dispatch
# - Aplicar filtros avanzados
# - Paginar resultados
# - Mostrar resumen rápido operativo
# ==========================================================
@app.route('/transporte', methods=['GET', 'POST'])
@requiere_permiso('transporte.ver')
def transporte():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        permiso_error = validar_permiso_accion(
            'transporte.crear',
            'Transporte',
            'Crear envío',
            'transporte'
        )
        if permiso_error:
            return permiso_error
        # Se leen los datos del formulario.
        id_venta = request.form.get('id_venta', type=int)
        id_vehiculo = request.form.get('id_vehiculo', type=int)
        id_chofer = request.form.get('id_chofer', type=int)
        destino = (request.form.get('destino') or '').strip()

        # Validación básica.
        if not id_venta or not id_vehiculo or not id_chofer or not destino:
            flash('Completa todos los campos para registrar el envío.', 'warning')
            return redirect(url_for('transporte'))

        venta = Venta.query.get_or_404(id_venta)
        vehiculo = Vehiculo.query.get_or_404(id_vehiculo)
        chofer = Chofer.query.get_or_404(id_chofer)

        # Regla: una venta no puede tener más de un envío activo.
        if venta_tiene_envio_activo(id_venta):
            flash(f'La venta #{venta.id_venta} ya tiene un envío activo.', 'warning')
            return redirect(url_for('transporte'))

        # El vehículo debe estar disponible.
        if vehiculo.estado != 'Disponible':
            flash(f'La unidad {vehiculo.placa} ya no está disponible.', 'danger')
            return redirect(url_for('transporte'))

        try:
            # Se intenta tomar la ubicación del cliente para que el envío aparezca en el mapa.
            latitud = None
            longitud = None

            if getattr(venta, 'cliente', None):
                latitud = venta.cliente.latitud
                longitud = venta.cliente.longitud

            # Se crea el envío ya en tránsito.
            nuevo_envio = Envio(
                id_venta=venta.id_venta,
                id_vehiculo=vehiculo.id_vehiculo,
                id_chofer=chofer.id_chofer,
                destino=destino,
                latitud=latitud,
                longitud=longitud,
                estado_entrega='En Tránsito',
                fecha_salida=datetime.now()
            )

            db.session.add(nuevo_envio)
            vehiculo.estado = 'En Ruta'

            db.session.commit()
            registrar_auditoria(
            "Transporte",
            "Crear",
            f"Envío registrado: Venta={request.form['id_venta']} | Vehículo={request.form['id_vehiculo']} | Chofer={request.form['id_chofer']}"
            )
            flash(f'Envío registrado correctamente para la venta #{venta.id_venta}.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'No fue posible registrar el envío: {str(e)}', 'danger')

        return redirect(url_for('transporte'))

    # ==========================================================
    # FILTROS DEL MÓDULO
    # ==========================================================
    filtro_q = (request.args.get('q') or '').strip()
    filtro_estado = (request.args.get('estado') or 'todos').strip()
    filtro_fecha_inicio = (request.args.get('fecha_inicio') or '').strip()
    filtro_fecha_fin = (request.args.get('fecha_fin') or '').strip()
    filtro_id_chofer = request.args.get('id_chofer_filtro', type=int)
    filtro_id_vehiculo = request.args.get('id_vehiculo_filtro', type=int)
    pagina_envios = request.args.get('page', 1, type=int)

    # Se excluyen ventas que ya tengan un envío pendiente o en tránsito.
    ids_ventas_con_envio_activo = obtener_ids_ventas_con_envio_activo()

    if ids_ventas_con_envio_activo:
        ventas_pendientes = Venta.query.filter(
            ~Venta.id_venta.in_(ids_ventas_con_envio_activo)
        ).order_by(Venta.id_venta.desc()).all()
    else:
        ventas_pendientes = Venta.query.order_by(Venta.id_venta.desc()).all()

    # Consulta base para listado.
    query_envios = Envio.query

    # Filtro por estado.
    if filtro_estado in ['Pendiente', 'En Tránsito', 'Entregado']:
        query_envios = query_envios.filter(Envio.estado_entrega == filtro_estado)

    # Se aplican filtros compartidos.
    query_envios = aplicar_filtros_envios(
        query=query_envios,
        texto_busqueda=filtro_q,
        fecha_inicio=filtro_fecha_inicio,
        fecha_fin=filtro_fecha_fin,
        id_chofer=filtro_id_chofer,
        id_vehiculo=filtro_id_vehiculo
    )

    # Se ordena y pagina el resultado final.
    query_envios = query_envios.order_by(
        Envio.fecha_salida.desc(),
        Envio.id_envio.desc()
    )

    paginacion_envios = paginar_query(query_envios, page=pagina_envios, per_page=10)
    envios = paginacion_envios['items']

    # Catálogos para formulario y filtros.
    total_envios = Envio.query.count()
    vehiculos_disponibles = Vehiculo.query.filter_by(estado='Disponible').order_by(Vehiculo.placa.asc()).all()
    vehiculos_filtro = Vehiculo.query.order_by(Vehiculo.placa.asc()).all()
    choferes = Chofer.query.order_by(Chofer.nombre.asc()).all()

    # Resumen rápido.
    resumen_choferes, resumen_vehiculos = obtener_resumen_operativo_envios()

    # Conteos globales por estado.
    conteo_pendientes = Envio.query.filter_by(estado_entrega='Pendiente').count()
    conteo_transito = Envio.query.filter_by(estado_entrega='En Tránsito').count()
    conteo_entregados = Envio.query.filter_by(estado_entrega='Entregado').count()

    return render_template(
        'transporte.html',
        envios=envios,
        ventas=ventas_pendientes,
        vehiculos_disponibles=vehiculos_disponibles,
        vehiculos_filtro=vehiculos_filtro,
        choferes=choferes,
        total_envios=total_envios,
        filtro_q=filtro_q,
        filtro_estado=filtro_estado,
        filtro_fecha_inicio=filtro_fecha_inicio,
        filtro_fecha_fin=filtro_fecha_fin,
        filtro_id_chofer=filtro_id_chofer,
        filtro_id_vehiculo=filtro_id_vehiculo,
        pagina_envios=paginacion_envios['page'],
        total_paginas_envios=paginacion_envios['total_pages'],
        total_filtrados_envios=paginacion_envios['total'],
        tiene_anterior_envios=paginacion_envios['has_prev'],
        tiene_siguiente_envios=paginacion_envios['has_next'],
        resumen_choferes=resumen_choferes,
        resumen_vehiculos=resumen_vehiculos,
        conteo_pendientes=conteo_pendientes,
        conteo_transito=conteo_transito,
        conteo_entregados=conteo_entregados
    )
# ==========================================================
# BLOQUE: Gestión de vehículos
# Propósito:
# - Registrar unidades con validación básica
# - Evitar placas duplicadas
# - Mostrar mensajes claros al usuario
# ==========================================================
@app.route('/vehiculos', methods=['GET', 'POST'])
def vehiculos():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Se leen y limpian los datos del formulario.
        placa = (request.form.get('placa') or '').strip().upper()
        modelo = (request.form.get('modelo') or '').strip()
        capacidad = request.form.get('capacidad', type=float)

        # Validaciones principales del formulario.
        if not placa or not modelo or capacidad is None:
            flash('Completa todos los campos de la unidad.', 'warning')
            return redirect(url_for('vehiculos'))

        if capacidad <= 0:
            flash('La capacidad debe ser mayor a cero.', 'warning')
            return redirect(url_for('vehiculos'))

        # Se valida que no exista otra unidad con la misma placa.
        existente = Vehiculo.query.filter_by(placa=placa).first()
        if existente:
            flash(f'La placa {placa} ya está registrada.', 'danger')
            return redirect(url_for('vehiculos'))

        try:
            # Se crea la nueva unidad con estado inicial disponible.
            nuevo = Vehiculo(
                placa=placa,
                modelo=modelo,
                capacidad_kg=capacidad,
                estado='Disponible'
            )
            db.session.add(nuevo)
            db.session.commit()

            flash(f'Unidad {placa} registrada correctamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'No fue posible registrar la unidad: {str(e)}', 'danger')

        return redirect(url_for('vehiculos'))

    # Se cargan todas las unidades para la vista.
    lista = Vehiculo.query.order_by(Vehiculo.estado.asc(), Vehiculo.placa.asc()).all()
    return render_template('vehiculos.html', vehiculos=lista)


# ==========================================================
# BLOQUE: Gestión de choferes
# Propósito:
# - Registrar choferes con validaciones básicas
# - Mejorar consistencia de datos
# - Mostrar mensajes claros al usuario
# ==========================================================
@app.route('/choferes', methods=['GET', 'POST'])
def choferes():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Se leen y limpian los datos del formulario.
        nombre = (request.form.get('nombre') or '').strip()
        licencia = (request.form.get('licencia') or '').strip().upper()
        telefono = (request.form.get('telefono') or '').strip()

        # Validaciones básicas del formulario.
        if not nombre or not licencia or not telefono:
            flash('Completa todos los campos del chofer.', 'warning')
            return redirect(url_for('choferes'))

        # Validación simple para no repetir licencias exactas.
        licencia_existente = Chofer.query.filter_by(licencia=licencia).first()
        if licencia_existente:
            flash(f'La licencia {licencia} ya está registrada.', 'danger')
            return redirect(url_for('choferes'))

        try:
            # Se crea el registro del chofer.
            nuevo = Chofer(
                nombre=nombre,
                licencia=licencia,
                telefono=telefono
            )
            db.session.add(nuevo)
            db.session.commit()

            flash(f'Chofer {nombre} registrado correctamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'No fue posible registrar el chofer: {str(e)}', 'danger')

        return redirect(url_for('choferes'))

    # Se listan choferes ordenados por nombre.
    lista = Chofer.query.order_by(Chofer.nombre.asc()).all()
    return render_template('choferes.html', choferes=lista)


@app.route('/embarques', methods=['GET', 'POST'])
def embarques():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Se leen los pesos y demás datos del formulario.
        peso_bruto = request.form.get('peso_bruto', type=float)
        peso_tara = request.form.get('peso_tara', type=float)
        tipo_mov = (request.form.get('tipo_movimiento') or '').strip()
        placas = (request.form.get('placas') or '').strip()
        chofer = (request.form.get('chofer') or '').strip()
        origen_destino = (request.form.get('origen_destino') or '').strip()
        tipo_metal_ingresado = (request.form.get('tipo_metal') or '').strip()

        # Validaciones del pesaje.
        if peso_bruto is None or peso_tara is None:
            flash('Debes capturar peso bruto y peso tara.', 'warning')
            return redirect(url_for('embarques'))

        if peso_bruto <= 0 or peso_tara < 0:
            flash('Los pesos deben ser mayores a cero.', 'warning')
            return redirect(url_for('embarques'))

        if peso_tara >= peso_bruto:
            flash('El peso tara no puede ser mayor o igual al peso bruto.', 'danger')
            return redirect(url_for('embarques'))

        if not tipo_mov or not placas or not chofer or not origen_destino or not tipo_metal_ingresado:
            flash('Completa todos los campos del embarque.', 'warning')
            return redirect(url_for('embarques'))

        peso_neto = peso_bruto - peso_tara

        try:
            # Se registra el movimiento de báscula.
            nuevo_embarque = Embarque(
                tipo_movimiento=tipo_mov,
                placas=placas,
                chofer=chofer,
                origen_destino=origen_destino,
                tipo_metal=tipo_metal_ingresado,
                peso_bruto_kg=peso_bruto,
                peso_tara_kg=peso_tara,
                peso_neto_kg=peso_neto,
                fecha_registro=datetime.now()
            )
            db.session.add(nuevo_embarque)

            # Automatización para entradas: suma al inventario de metal.
            if tipo_mov == 'Entrada':
                inventario = InventarioMetal.query.filter_by(
                    tipo_metal=tipo_metal_ingresado
                ).first()

                if inventario:
                    inventario.cantidad_kg += peso_neto
                else:
                    nuevo_inventario = InventarioMetal(
                        id_almacen=1,
                        id_proveedor=1,
                        tipo_metal=tipo_metal_ingresado,
                        cantidad_kg=peso_neto,
                        fecha_entrada=date.today()
                    )
                    db.session.add(nuevo_inventario)

            db.session.commit()
            flash(
                f'Embarque registrado correctamente. Peso neto: {peso_neto:,.2f} kg.',
                'success'
            )
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar el embarque: {str(e)}', 'danger')

        return redirect(url_for('embarques'))

    # Se carga historial y catálogos del formulario.
    lista_embarques = Embarque.query.order_by(
        Embarque.fecha_registro.desc(),
        Embarque.id_embarque.desc()
    ).all()

    vehiculos = Vehiculo.query.order_by(Vehiculo.placa.asc()).all()
    proveedores = Proveedor.query.order_by(Proveedor.nombre.asc()).all()
    clientes = Cliente.query.order_by(Cliente.empresa.asc()).all()
    lista_choferes = Chofer.query.order_by(Chofer.nombre.asc()).all()

    # Se obtienen tipos de metal ya registrados para sugerencias en el input.
    metales_unicos = db.session.query(InventarioMetal.tipo_metal).distinct().all()
    lista_metales = [m[0] for m in metales_unicos if m[0]]

    return render_template(
        'embarques.html',
        embarques=lista_embarques,
        vehiculos=vehiculos,
        proveedores=proveedores,
        clientes=clientes,
        choferes=lista_choferes,
        metales=lista_metales
    )

# ==========================================================
# BLOQUE: Finalizar entrega desde transporte
# Propósito:
# - Cerrar envío
# - Liberar vehículo
# - Mantener sincronía con dispatch
# ==========================================================
@app.route('/entregar/<int:id_envio>', methods=['POST'])
def finalizar_entrega(id_envio):
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    envio = Envio.query.get_or_404(id_envio)

    try:
        if envio.estado_entrega != 'Entregado':
            marcar_envio_como_entregado(envio)
            db.session.commit()
            flash(f'El envío #{envio.id_envio} se marcó como entregado.', 'success')
        else:
            flash('Ese envío ya estaba marcado como entregado.', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'No fue posible finalizar la entrega: {str(e)}', 'danger')

    return redirect(url_for('transporte'))


# ==========================================================
# BLOQUE: Compatibilidad con endpoint viejo de dispatch
# Propósito:
# - Mantener funcionando llamadas antiguas a completar_envio
# - Usar exactamente la misma lógica que finalizar_entrega
# ==========================================================
@app.route('/completar_envio/<int:id>', methods=['POST'])
def completar_envio(id):
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    envio = Envio.query.get_or_404(id)

    try:
        if envio.estado_entrega != 'Entregado':
            marcar_envio_como_entregado(envio)
            db.session.commit()
            flash(f'El envío #{envio.id_envio} se marcó como entregado.', 'success')
        else:
            flash('Ese envío ya estaba marcado como entregado.', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'No fue posible completar el envío: {str(e)}', 'danger')

    return redirect(url_for('dispatch_mapa'))

@app.route('/pedidos')
def lista_pedidos():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # Se listan pedidos del más reciente al más antiguo.
    pedidos = PedidoVenta.query.order_by(
        PedidoVenta.fecha_pedido.desc(),
        PedidoVenta.id_pedido.desc()
    ).all()

    return render_template('pedidos.html', pedidos=pedidos)


@app.route('/nuevo_pedido', methods=['GET', 'POST'])
def nuevo_pedido():
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        id_cliente = request.form.get('id_cliente', type=int)

        if not id_cliente:
            flash('Debes seleccionar un cliente.', 'warning')
            return redirect(url_for('nuevo_pedido'))

        cliente = Cliente.query.get(id_cliente)
        if not cliente:
            flash('El cliente seleccionado no existe.', 'danger')
            return redirect(url_for('nuevo_pedido'))

        try:
            # Se crea el pedido en estado pendiente y en cero.
            nuevo_p = PedidoVenta(
                id_cliente=id_cliente,
                estado='Pendiente',
                total=0.0
            )
            db.session.add(nuevo_p)
            db.session.commit()

            flash(
                f'Pedido #{nuevo_p.id_pedido:04d} creado correctamente.',
                'success'
            )
            return redirect(url_for('detalle_pedido', id=nuevo_p.id_pedido))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear pedido: {str(e)}', 'danger')

    clientes = Cliente.query.order_by(Cliente.empresa.asc(), Cliente.nombre_contacto.asc()).all()
    return render_template('nuevo_pedido.html', clientes=clientes)


@app.route('/pedido/<int:id>')
def detalle_pedido(id):
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    pedido = PedidoVenta.query.get_or_404(id)

    # Se calcula stock por producto para mostrarlo en el selector.
    productos_con_stock = []
    todos_los_productos = Producto.query.order_by(Producto.nombre_producto.asc()).all()

    for producto in todos_los_productos:
        stock = db.session.query(func.sum(InventarioProducto.cantidad_stock)).filter(
            InventarioProducto.id_producto == producto.id_producto
        ).scalar() or 0

        productos_con_stock.append({
            'obj': producto,
            'stock': stock
        })

    return render_template(
        'detalle_pedido.html',
        pedido=pedido,
        productos=productos_con_stock
    )


@app.route('/despachar_pedido/<int:id_pedido>', methods=['POST'])
def despachar_pedido(id_pedido):
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    pedido = PedidoVenta.query.get_or_404(id_pedido)

    if pedido.estado != 'Pendiente':
        flash('Este pedido ya fue procesado anteriormente.', 'warning')
        return redirect(url_for('detalle_pedido', id=id_pedido))

    if not pedido.detalles:
        flash('No puedes despachar un pedido sin artículos.', 'warning')
        return redirect(url_for('detalle_pedido', id=id_pedido))

    try:
        # Se recorre cada artículo del pedido y se descuenta del inventario.
        for item in pedido.detalles:
            registros_inventario = InventarioProducto.query.filter_by(
                id_producto=item.id_producto
            ).order_by(InventarioProducto.fecha_fabricacion.asc()).all()

            stock_total = sum(reg.cantidad_stock for reg in registros_inventario)

            if stock_total < item.cantidad:
                flash(
                    f'Stock insuficiente para {item.producto.nombre_producto}. '
                    f'Disponible: {stock_total}, solicitado: {item.cantidad}.',
                    'danger'
                )
                db.session.rollback()
                return redirect(url_for('detalle_pedido', id=id_pedido))

            # Se descuenta stock incluso si el producto está repartido entre varios registros.
            cantidad_por_descontar = item.cantidad

            for registro in registros_inventario:
                if cantidad_por_descontar <= 0:
                    break

                descuento = min(registro.cantidad_stock, cantidad_por_descontar)
                registro.cantidad_stock -= descuento
                cantidad_por_descontar -= descuento

        # Se cambia el estado una vez descontado todo correctamente.
        pedido.estado = 'Despachado'

        db.session.commit()
        flash(
            f'Pedido #{id_pedido:04d} despachado con éxito. Inventario actualizado.',
            'success'
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Error al despachar el pedido: {str(e)}', 'danger')

    return redirect(url_for('lista_pedidos'))


@app.route('/agregar_item/<int:id_pedido>', methods=['POST'])
def agregar_item(id_pedido):
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    pedido = PedidoVenta.query.get_or_404(id_pedido)

    if pedido.estado != 'Pendiente':
        flash('Solo puedes editar pedidos pendientes.', 'warning')
        return redirect(url_for('detalle_pedido', id=id_pedido))

    id_prod = request.form.get('id_producto', type=int)
    qty_solicitada = request.form.get('cantidad', type=int)

    if not id_prod or not qty_solicitada:
        flash('Selecciona un producto y una cantidad válida.', 'warning')
        return redirect(url_for('detalle_pedido', id=id_pedido))

    if qty_solicitada <= 0:
        flash('La cantidad debe ser mayor a cero.', 'warning')
        return redirect(url_for('detalle_pedido', id=id_pedido))

    prod = Producto.query.get_or_404(id_prod)
    precio_vta = prod.precio or 0.0

    # Se calcula el stock físico total disponible.
    stock_disponible = db.session.query(func.sum(InventarioProducto.cantidad_stock)).filter(
        InventarioProducto.id_producto == id_prod
    ).scalar() or 0

    # Se calcula cuánto de ese producto ya está capturado dentro del mismo pedido.
    cantidad_ya_en_pedido = sum(
        item.cantidad for item in pedido.detalles if item.id_producto == id_prod
    )

    disponible_para_agregar = stock_disponible - cantidad_ya_en_pedido

    if qty_solicitada > disponible_para_agregar:
        flash(
            f'Stock insuficiente. Disponible para agregar: {disponible_para_agregar} '
            f'unidades de {prod.nombre_producto}.',
            'danger'
        )
        return redirect(url_for('detalle_pedido', id=id_pedido))

    try:
        # Si el producto ya existe en el pedido, solo incrementamos cantidad.
        item_existente = DetallePedido.query.filter_by(
            id_pedido=id_pedido,
            id_producto=id_prod
        ).first()

        if item_existente:
            item_existente.cantidad += qty_solicitada
        else:
            nuevo_item = DetallePedido(
                id_pedido=id_pedido,
                id_producto=id_prod,
                cantidad=qty_solicitada,
                precio_unitario=precio_vta
            )
            db.session.add(nuevo_item)

        # Se sincroniza el total del pedido.
        db.session.flush()
        recalcular_total_pedido(pedido)

        db.session.commit()
        flash(f'{prod.nombre_producto} agregado correctamente al pedido.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar el artículo: {str(e)}', 'danger')

    return redirect(url_for('detalle_pedido', id=id_pedido))


@app.route('/eliminar_item/<int:id_detalle>', methods=['POST'])
def eliminar_item(id_detalle):
    # Validación de sesión para proteger el módulo.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    item = DetallePedido.query.get_or_404(id_detalle)
    pedido = PedidoVenta.query.get_or_404(item.id_pedido)

    if pedido.estado != 'Pendiente':
        flash('No puedes eliminar artículos de un pedido ya despachado.', 'warning')
        return redirect(url_for('detalle_pedido', id=pedido.id_pedido))

    try:
        # Se elimina el detalle y luego se recalcula el total.
        db.session.delete(item)
        db.session.flush()

        recalcular_total_pedido(pedido)

        db.session.commit()
        flash('Artículo eliminado del pedido correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'No fue posible eliminar el artículo: {str(e)}', 'danger')

    return redirect(url_for('detalle_pedido', id=pedido.id_pedido))
@app.route('/imprimir_vale/<int:id_envio>')
def imprimir_vale(id_envio):
    # Validación de sesión para proteger la generación del vale.
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # Se obtiene el envío solicitado.
    envio = Envio.query.get_or_404(id_envio)

    # Se crea el documento PDF.
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Encabezado principal del documento.
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "ECODATA - VALE DE SALIDA", 0, 1, "C")

    pdf.set_font("Arial", "", 10)
    fecha_salida = envio.fecha_salida.strftime('%d/%m/%Y %H:%M') if envio.fecha_salida else "N/D"
    pdf.cell(0, 8, f"Fecha de salida: {fecha_salida}", 0, 1, "R")
    pdf.ln(4)

    # Título del bloque de datos.
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Guia de despacho #ENV-{envio.id_envio}", 1, 1, "L", True)

    pdf.ln(4)
    pdf.set_font("Arial", "", 11)

    # Datos principales del envío.
    cliente_nombre = "N/D"
    empresa = "N/D"
    venta_id = "N/D"
    producto = "N/D"
    cantidad = "N/D"

    if envio.venta:
        venta_id = envio.venta.id_venta

        # Nombre de cliente y empresa asociados a la venta.
        if getattr(envio.venta, 'cliente', None):
            cliente_nombre = envio.venta.cliente.nombre_contacto or "N/D"
            empresa = envio.venta.cliente.empresa or "N/D"

        # Datos del producto en caso de existir esa relación.
        if getattr(envio.venta, 'producto', None):
            producto = envio.venta.producto.nombre_producto or "N/D"

        # Cantidad de la venta, si el modelo la tiene.
        cantidad = getattr(envio.venta, 'cantidad', "N/D")

    vehiculo_placa = envio.vehiculo.placa if getattr(envio, 'vehiculo', None) else "N/D"
    chofer_nombre = envio.chofer.nombre if getattr(envio, 'chofer', None) else "N/D"
    destino = envio.destino or "N/D"
    estado = envio.estado_entrega or "N/D"

    # Contenido del vale.
    pdf.cell(0, 8, f"Cliente: {cliente_nombre}", 0, 1)
    pdf.cell(0, 8, f"Empresa: {empresa}", 0, 1)
    pdf.cell(0, 8, f"Venta relacionada: #{venta_id}", 0, 1)
    pdf.cell(0, 8, f"Producto: {producto}", 0, 1)
    pdf.cell(0, 8, f"Cantidad: {cantidad}", 0, 1)
    pdf.cell(0, 8, f"Vehiculo: {vehiculo_placa}", 0, 1)
    pdf.cell(0, 8, f"Chofer: {chofer_nombre}", 0, 1)
    pdf.cell(0, 8, f"Destino: {destino}", 0, 1)
    pdf.cell(0, 8, f"Estado: {estado}", 0, 1)

    pdf.ln(18)

    # Área de firmas.
    pdf.cell(90, 10, "______________________________", 0, 0, "C")
    pdf.cell(20, 10, "", 0, 0)
    pdf.cell(80, 10, "______________________________", 0, 1, "C")

    pdf.cell(90, 8, "Entrega EcoData", 0, 0, "C")
    pdf.cell(20, 8, "", 0, 0)
    pdf.cell(80, 8, "Recibe cliente", 0, 1, "C")

    # Se construye la respuesta HTTP con el PDF.
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers.set(
        'Content-Disposition',
        'attachment',
        filename=f'Vale_ENV_{envio.id_envio}.pdf'
    )
    response.headers.set('Content-Type', 'application/pdf')

    return response

# --- MÓDULO DE PRIVILEGIOS Y GESTIÓN DE USUARIOS ---
@app.route('/usuarios', methods=['GET', 'POST'])
def usuarios():

    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    if session.get('rol') != 'Administrador':
        abort(403)

    if 'usuario' not in session or session.get('rol') != 'Administrador':
        return redirect(url_for('login'))

    if request.method == 'POST':
        nombre = request.form['nombre_usuario']
        password = request.form['password']
        # Por defecto, los nuevos creados desde aquí serán 'Operador'
        # o puedes agregar un <select> en el HTML para elegir
        rol_elegido = request.form.get('rol', 'Operador') 

        # 1. Guardar credenciales en InicioLog
        nuevo_login = InicioLog(
            usuario=nombre, 
            contrasena=generate_password_hash(password)
        )
        
        # 2. Guardar el rol en RolUsuario
        nuevo_rol = RolUsuario(
            nombre_usuario=nombre, 
            rol=rol_elegido
        )

        try:
            db.session.add(nuevo_login)
            db.session.add(nuevo_rol)
            db.session.commit()
        except:
            db.session.rollback()
            return "Error: El usuario ya existe o hubo un problema."

        return redirect(url_for('usuarios'))

    # 3. Consultar usuarios para la tabla
    # Hacemos un join o simplemente pedimos los roles registrados
    lista_usuarios = RolUsuario.query.all()
    return render_template('usuarios.html', lista_usuarios=lista_usuarios)

# ==========================================
# RUTAS PARA EDITAR Y ELIMINAR USUARIOS
# ==========================================
@app.route('/eliminar_usuario/<int:id>')
def eliminar_usuario(id):
    usuario = InicioLog.query.get(id) # .get usa la primary_key (id_usuario)
    if usuario:
        rol = RolUsuario.query.filter_by(nombre_usuario=usuario.usuario).first()
        if rol: db.session.delete(rol)
        db.session.delete(usuario)
        db.session.commit()
    return redirect(url_for('personal'))

@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
def editar_usuario(id):
    usuario = InicioLog.query.get_or_404(id)
    rol_reg = RolUsuario.query.filter_by(nombre_usuario=usuario.usuario).first()
    rol_actual = rol_reg.rol if rol_reg else "Operador"

    if request.method == 'POST':
        usuario.id_area = request.form.get('id_area')
        nuevo_rol = request.form.get('rol')
        if rol_reg:
            rol_reg.rol = nuevo_rol
        else:
            db.session.add(RolUsuario(nombre_usuario=usuario.usuario, rol=nuevo_rol))
        db.session.commit()
        return redirect(url_for('personal'))

    areas = Area.query.all()
    return render_template('editar_usuario.html', persona=usuario, areas=areas, rol_actual=rol_actual)

@app.route('/privilegios', methods=['GET', 'POST'])
@admin_required
def privilegios():
    roles_disponibles = [
        'Administrador',
        'Supervisor',
        'Operador',
        'Compras',
        'Ventas',
        'Logistica',
        'Produccion',
        'Mantenimiento',
        'Calidad'
    ]

    if request.method == 'POST':
        usuario_modificado = (request.form.get('nombre_usuario') or '').strip()
        nuevo_rol = (request.form.get('rol') or '').strip()

        if not usuario_modificado:
            flash("No se recibió el usuario a actualizar.", "error")
            return redirect(url_for('privilegios'))

        if nuevo_rol not in roles_disponibles:
            flash("El rol seleccionado no es válido.", "error")
            return redirect(url_for('privilegios'))

        usuario_db = InicioLog.query.filter_by(usuario=usuario_modificado).first()
        if not usuario_db:
            flash("El usuario no existe en InicioLog.", "error")
            return redirect(url_for('privilegios'))

        rol_existente = RolUsuario.query.filter_by(nombre_usuario=usuario_modificado).first()

        try:
            if rol_existente:
                rol_anterior = rol_existente.rol
                rol_existente.rol = nuevo_rol
                detalle = f"Usuario={usuario_modificado} | Rol anterior={rol_anterior} | Rol nuevo={nuevo_rol}"
            else:
                nuevo_registro = RolUsuario(
                    nombre_usuario=usuario_modificado,
                    rol=nuevo_rol
                )
                db.session.add(nuevo_registro)
                detalle = f"Usuario={usuario_modificado} | Rol asignado={nuevo_rol}"

            db.session.commit()

            registrar_auditoria(
                "Privilegios",
                "Actualizar rol",
                detalle
            )

            flash(f"Privilegios actualizados: {usuario_modificado} ahora es {nuevo_rol}.", "success")

        except Exception as e:
            db.session.rollback()
            flash(f"No se pudo actualizar el rol: {str(e)}", "error")

        return redirect(url_for('privilegios'))

    usuarios_db = InicioLog.query.order_by(InicioLog.usuario.asc()).all()
    roles_asignados = {r.nombre_usuario: r.rol for r in RolUsuario.query.all()}

    return render_template(
        'privilegios.html',
        usuarios=usuarios_db,
        roles_asignados=roles_asignados,
        roles_disponibles=roles_disponibles
    )

@app.route('/actualizar_bd')
def actualizar_bd():
    try:
        # Ejecutamos el comando SQL directo para agregar la columna
        db.session.execute(db.text("ALTER TABLE embarque ADD COLUMN tipo_metal VARCHAR(100) NOT NULL DEFAULT 'Sin Especificar';"))
        db.session.commit()
        return "¡Base de datos actualizada con éxito! Ya puedes usar el módulo de embarques."
    except Exception as e:
        return f"Ocurrió un error (quizás la columna ya existe): {e}"
    
@app.route('/eliminar_producto/<int:id>')
@admin_required
def eliminar_producto(id):
    prod = Producto.query.get(id)
    registrar_auditoria(
    "Inventario",
    "Eliminar",
    f"Eliminó el producto: {prod.nombre_producto}"
    )
    db.session.delete(prod)
    db.session.commit()
    return redirect(url_for('productos'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)

