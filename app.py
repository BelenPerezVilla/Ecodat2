from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Area, InicioLog, Proveedor, Almacen, Producto, InventarioMetal, InventarioProducto, Proceso, Transaccion, Cliente, Venta, RolUsuario, Mantenimiento, Maquina, Calidad, Vehiculo, Chofer, Envio, ProcesoReciclaje, Embarque, Maquinaria, Compra, PedidoVenta, DetallePedido
from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.security import generate_password_hash
from datetime import date
from datetime import datetime, timedelta
from sqlalchemy import func
from fpdf import FPDF
from flask import make_response
from sqlalchemy import func
import csv
import io
from flask import make_response
import json
from sqlalchemy import func
import pandas as pd
from io import BytesIO
from flask import send_file 
from functools import wraps
from flask import session, redirect, url_for, flash 

app = Flask(__name__)
app.secret_key = 'hola123' # Necesario para las sesiones

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
mi_contrasena = "Hola123" 
password_segura = quote_plus(mi_contrasena)

# Conexión a PostgreSQL apuntando a la base de datos EcoData
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://postgres:Hola123@localhost:5432/EcoData'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- VIGILANTE DE SESIONES (Se ejecuta antes de cargar cualquier pantalla) ---
@app.before_request
def cargar_rol():
    if 'usuario' in session:
        # Buscar el rol del usuario en la base de datos
        rol_db = RolUsuario.query.filter_by(nombre_usuario=session['usuario']).first()
        # Si no tiene rol asignado aún, te damos Administrador por defecto para que no te quedes fuera
        session['rol'] = rol_db.rol if rol_db else 'Administrador'

# Crear las tablas automáticamente y un usuario administrador de prueba
with app.app_context():
    db.create_all()
    # Si no existe el usuario admin, lo creamos
    if not InicioLog.query.filter_by(usuario='admin').first():
        area_admin = Area(nombre_area='Administración')
        db.session.add(area_admin)
        db.session.commit()
        
        usuario_admin = InicioLog(id_area=area_admin.id_area, usuario='admin', contrasena='admin123')
        db.session.add(usuario_admin)
        db.session.commit()
    # --- NUEVO: Crear un Proveedor y un Almacén de prueba si no existen ---
    if not Proveedor.query.first():
        prov_prueba = Proveedor(nombre="Reciclados Metálicos S.A.", telefono="555-1234")
        db.session.add(prov_prueba)
        db.session.commit()
        
    if not Almacen.query.first():
        alm_prueba = Almacen(nombre_almacen="Bodega Principal", ubicacion="Nave Industrial 1")
        db.session.add(alm_prueba)
        db.session.commit()
    # --- NUEVO: Crear un par de Productos de prueba en el catálogo ---
    if not Producto.query.first():
        prod1 = Producto(nombre_producto="Pala de Acero", descripcion="Pala cuadrada uso rudo")
        prod2 = Producto(nombre_producto="Pico de Construcción", descripcion="Pico estándar")
        db.session.add_all([prod1, prod2])
        db.session.commit()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Verificamos si alguien inició sesión
        if 'usuario' not in session:
            flash("Por favor, inicia sesión para continuar.", "error")
            return redirect(url_for('login'))
            
        # 2. Verificamos si su rol es Administrador
        if session.get('rol') != 'Administrador':
            flash("Acceso denegado. Esta sección es exclusiva para Administradores.", "error")
            return redirect(url_for('compras')) # O la ruta de tu dashboard principal
            
        # Si pasa las dos pruebas, lo dejamos entrar a la ruta original
        return f(*args, **kwargs)
    return decorated_function

# Ruta principal: Inicio de sesión
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session:
        return redirect(url_for('compras')) # Opcional: mandarlos al dashboard

    error = None
    if request.method == 'POST':
        usuario_form = request.form.get('usuario')
        password_form = request.form.get('password')
        
        user_db = InicioLog.query.filter_by(usuario=usuario_form, contrasena=password_form).first()
        
        if user_db:
            session['usuario'] = user_db.usuario
            session['id_area'] = user_db.id_area
            
            # NUEVO: Guardamos el nombre del área para los permisos del menú
            if user_db.area:
                session['area_nombre'] = user_db.area.nombre_area
            else:
                session['area_nombre'] = 'Sin Area'
            
            rol_db = RolUsuario.query.filter_by(nombre_usuario=user_db.usuario).first()
            session['rol'] = rol_db.rol if rol_db else 'Operador'
            
            return redirect(url_for('compras'))
        else:
            error = "Usuario o contraseña incorrectos. Intenta de nuevo."
            
    return render_template('login.html', error=error)

@app.route('/areas', methods=['GET', 'POST'])
def gestion_areas():
    if request.method == 'POST':
        # Recibimos el nombre del área desde el formulario
        nombre = request.form.get('nombre_area')
        
        if nombre:
            # Guardamos la nueva área en la base de datos
            nueva_area = Area(nombre_area=nombre)
            db.session.add(nueva_area)
            
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return f"Error al guardar el área: {e}"
                
        # Recargamos la página limpia
        return redirect(url_for('gestion_areas'))
    
    # Si es GET, traemos todas las áreas para mostrarlas en la tabla
    todas_las_areas = Area.query.all()
    return render_template('areas.html', areas=todas_las_areas)


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

@app.route('/logout')
def logout():
    session.clear() # Borra los datos de la sesión
    return redirect(url_for('login'))
# --- RUTAS DE LA APLICACIÓN ---

# --- RUTA DEL DASHBOARD (PANEL DE CONTROL CON GRÁFICAS) ---
@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session: 
        return redirect(url_for('login'))
    
    # --- 1. KPIs DE INVENTARIO Y PROCESOS (Tu lógica actual) ---
    metales = InventarioMetal.query.all()
    total_kilos = sum(m.cantidad_kg for m in metales if m.cantidad_kg)
    
    productos_inv = InventarioProducto.query.all()
    total_piezas = sum(p.cantidad_stock for p in productos_inv if p.cantidad_stock)
    
    procesos_activos = Proceso.query.filter_by(estado='En progreso').count()
    
    # --- 2. KPIs DE VENTAS (NUEVO) ---
    # Sumamos el total de dinero de todos los pedidos despachados
    dinero_total = db.session.query(func.sum(PedidoVenta.total)).scalar() or 0
    pedidos_pendientes = PedidoVenta.query.filter_by(estado='Pendiente').count()

    # --- 3. DATOS PARA LAS GRÁFICAS ---
    # Gráfica 1: Stock de Productos (Tu lógica actual)
    nombres_prod = []
    cantidades_prod = []
    for inv in productos_inv:
        prod = Producto.query.get(inv.id_producto)
        if prod:
            nombres_prod.append(f"{prod.nombre_producto} (Alm {inv.id_almacen})")
            cantidades_prod.append(inv.cantidad_stock)
            
    # Gráfica 2: Distribución de Metales (Tu lógica actual)
    tipos_metal = [f"{m.tipo_metal} (Lote {m.id_inventario_m})" for m in metales]
    kilos_metal = [m.cantidad_kg for m in metales]

    # NUEVA Gráfica 3: Tendencia de Ventas (Últimos 7 días)
    hoy = datetime.now()
    hace_siete_dias = hoy - timedelta(days=7)
    ventas_7_dias = db.session.query(
        func.date(PedidoVenta.fecha_pedido), 
        func.sum(PedidoVenta.total)
    ).filter(PedidoVenta.fecha_pedido >= hace_siete_dias)\
     .group_by(func.date(PedidoVenta.fecha_pedido)).all()

    labels_ventas = [v[0].strftime('%d %b') for v in ventas_7_dias]
    valores_ventas = [float(v[1]) for v in ventas_7_dias]

    return render_template('dashboard.html', 
                           usuario_actual=session['usuario'],
                           total_kilos=round(total_kilos, 2),
                           total_piezas=total_piezas,
                           procesos_activos=procesos_activos,
                           dinero_total=dinero_total,
                           pedidos_pendientes=pedidos_pendientes,
                           nombres_prod=nombres_prod,
                           cantidades_prod=cantidades_prod,
                           tipos_metal=tipos_metal,
                           kilos_metal=kilos_metal,
                           labels_ventas=labels_ventas,
                           valores_ventas=valores_ventas)


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
# --- MÓDULO CATÁLOGO BASE DE PRODUCTOS ---
@app.route('/productos', methods=['GET', 'POST'])
def productos():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre_producto = request.form['nombre_producto']
        descripcion = request.form.get('descripcion', '') 
        # Convertimos el precio a float para la base de datos
        precio = float(request.form.get('precio', 0.0))
        
        # Creamos el producto con el nuevo campo 'precio'
        nuevo_producto = Producto(
            nombre_producto=nombre_producto, 
            descripcion=descripcion,
            precio=precio # Asegúrate que tu modelo Producto tenga este campo
        )
        
        try:
            db.session.add(nuevo_producto)
            db.session.commit()
            flash("Producto registrado con éxito", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al registrar: {str(e)}", "danger")
            
        return redirect(url_for('productos'))
        
    lista_productos = Producto.query.all()
    return render_template('productos.html', productos=lista_productos)


@app.route('/editar_producto/<int:id>', methods=['POST'])
def editar_producto(id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    producto = Producto.query.get_or_404(id)
    
    try:
        producto.nombre_producto = request.form['nombre_producto']
        producto.descripcion = request.form['descripcion']
        producto.precio = float(request.form['precio'])
        
        db.session.commit()
        flash(f"Producto {producto.nombre_producto} actualizado correctamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al actualizar: {str(e)}", "danger")
        
    return redirect(url_for('productos'))

@app.route('/mantenimiento', methods=['GET', 'POST'])
def mantenimiento():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Detectamos si estamos guardando una máquina o un mantenimiento
        if 'guardar_maquina' in request.form:
            nueva_maquina = Maquina(
                nombre=request.form['nombre_maquina'],
                modelo=request.form['modelo'],
                estado='Operativa'
            )
            db.session.add(nueva_maquina)
        
        elif 'guardar_mantenimiento' in request.form:
            fecha_dt = datetime.strptime(request.form['fecha'], '%Y-%m-%d').date()
            nuevo_mant = Mantenimiento(
                id_maquina=request.form['id_maquina'],
                tipo=request.form['tipo'],
                descripcion=request.form['descripcion'],
                fecha=fecha_dt,
                costo=float(request.form['costo']),
                tecnico=request.form['tecnico']
            )
            db.session.add(nuevo_mant)
        
        db.session.commit()
        return redirect(url_for('mantenimiento'))

    maquinas = Maquina.query.all()
    historial = Mantenimiento.query.order_by(Mantenimiento.fecha.desc()).all()
    return render_template('mantenimiento.html', maquinas=maquinas, historial=historial)

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
def ventas():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        id_cliente = request.form['id_cliente']
        id_producto = request.form['id_producto']
        cantidad = request.form['cantidad']
        total_venta = request.form['total_venta']
        fecha_str = request.form['fecha_venta']
        
        try:
            fecha_venta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_venta = datetime.today().date()
            
        nueva_venta = Venta(
            id_cliente=id_cliente,
            id_producto=id_producto,
            cantidad=int(cantidad),
            total_venta=float(total_venta),
            fecha_venta=fecha_venta
        )
        db.session.add(nueva_venta)
        db.session.commit()
        return redirect(url_for('ventas'))
        
    # Consultas necesarias para las listas desplegables y la tabla
    lista_ventas = Venta.query.all()
    lista_clientes = Cliente.query.all()
    lista_productos = Producto.query.all()
    
    return render_template('ventas.html', 
                           ventas=lista_ventas, 
                           clientes=lista_clientes, 
                           productos=lista_productos)

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


@app.route('/transporte', methods=['GET', 'POST'])
def transporte():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        nuevo_envio = Envio(
            id_venta=request.form['id_venta'],
            id_vehiculo=request.form['id_vehiculo'],
            id_chofer=request.form['id_chofer'],
            destino=request.form['destino']
        )
        db.session.add(nuevo_envio)
        
        # Actualizamos el estado del vehículo a 'En Ruta'
        vehiculo = Vehiculo.query.get(request.form['id_vehiculo'])
        vehiculo.estado = 'En Ruta'
        
        db.session.commit()
        return redirect(url_for('transporte'))

    envios = Envio.query.order_by(Envio.id_envio.desc()).all()
    ventas_pendientes = Venta.query.all() # Aquí podrías filtrar las que no tienen envío aún
    vehiculos = Vehiculo.query.filter_by(estado='Disponible').all()
    choferes = Chofer.query.all()
    
    return render_template('transporte.html', envios=envios, ventas=ventas_pendientes, vehiculos=vehiculos, choferes=choferes)

@app.route('/vehiculos', methods=['GET', 'POST'])
def vehiculos():
    if request.method == 'POST':
        nuevo = Vehiculo(placa=request.form['placa'], modelo=request.form['modelo'], capacidad_kg=request.form['capacidad'])
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('vehiculos'))
    lista = Vehiculo.query.all()
    return render_template('vehiculos.html', vehiculos=lista)

@app.route('/embarques', methods=['GET', 'POST'])
def embarques():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        peso_bruto = float(request.form['peso_bruto'])
        peso_tara = float(request.form['peso_tara'])
        peso_neto = peso_bruto - peso_tara
        
        tipo_mov = request.form['tipo_movimiento']
        tipo_metal_ingresado = request.form['tipo_metal']

        nuevo_embarque = Embarque(
            tipo_movimiento=tipo_mov,
            placas=request.form['placas'], # Viene del menú desplegable
            chofer=request.form['chofer'],
            origen_destino=request.form['origen_destino'],
            tipo_metal=tipo_metal_ingresado,
            peso_bruto_kg=peso_bruto,
            peso_tara_kg=peso_tara,
            peso_neto_kg=peso_neto,
            fecha_registro=datetime.now()
        )
        db.session.add(nuevo_embarque)

        # --- MAGIA DEL ERP: AUTOMATIZACIÓN DE INVENTARIO ---
        if tipo_mov == 'Entrada':
            # Buscamos si ya existe el metal en el inventario
            inventario = InventarioMetal.query.filter_by(tipo_metal=tipo_metal_ingresado).first()
            
            if inventario:
                # Si existe, sumamos los kilos
                inventario.cantidad_kg += peso_neto
            else:
                # Si es nuevo, creamos el registro (usando Almacen 1 y Proveedor 1 por defecto)
                nuevo_inventario = InventarioMetal(
                    id_almacen=1,       
                    id_proveedor=1,     
                    tipo_metal=tipo_metal_ingresado,
                    cantidad_kg=peso_neto,
                    fecha_entrada=date.today()
                )
                db.session.add(nuevo_inventario)
        # ----------------------------------------------------
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error al registrar el embarque o actualizar inventario: {e}"
            
        return redirect(url_for('embarques'))

    # Para cargar la página (GET)
    # 1. Traemos el historial de embarques
    lista_embarques = Embarque.query.order_by(Embarque.fecha_registro.desc()).all()
    
    # 2. Traemos los catálogos para los menús desplegables
    vehiculos = Vehiculo.query.all()
    proveedores = Proveedor.query.all()
    clientes = Cliente.query.all()
    lista_choferes = Chofer.query.all()
    
    # 3. TRUCO: Sacamos una lista de los metales que ya existen en tu inventario para no duplicarlos
    metales_unicos = db.session.query(InventarioMetal.tipo_metal).distinct().all()
    lista_metales = [m[0] for m in metales_unicos] # Lo convierte en una lista fácil de leer
    
    # Asegúrate de enviar todas estas variables al HTML
    return render_template('embarques.html', 
                           embarques=lista_embarques, 
                           vehiculos=vehiculos,
                           proveedores=proveedores,
                           clientes=clientes,
                           choferes=lista_choferes,
                           metales=lista_metales)




@app.route('/choferes', methods=['GET', 'POST'])
def choferes():
    if request.method == 'POST':
        nuevo = Chofer(nombre=request.form['nombre'], licencia=request.form['licencia'], telefono=request.form['telefono'])
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('choferes'))
    lista = Chofer.query.all()
    return render_template('choferes.html', choferes=lista)

@app.route('/entregar/<int:id_envio>', methods=['POST'])
def finalizar_entrega(id_envio):
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # 1. Buscamos el envío en la base de datos
    envio = Envio.query.get_or_404(id_envio)

    if envio.estado_entrega != 'Entregado':
        # 2. Marcamos el envío como completado
        envio.estado_entrega = 'Entregado'
        
        # 3. Buscamos el vehículo asociado y lo liberamos
        vehiculo = Vehiculo.query.get(envio.id_vehiculo)
        if vehiculo:
            vehiculo.estado = 'Disponible'
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error al procesar la entrega: {e}"

    return redirect(url_for('transporte'))


@app.route('/imprimir_vale/<int:id_envio>')
def imprimir_vale(id_envio):
    envio = Envio.query.get_or_404(id_envio)
    
    pdf = FPDF()
    pdf.add_page()
    
    # Encabezado
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "ECODATA - VALE DE SALIDA DE MATERIAL", 0, 1, 'C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Fecha: {envio.fecha_salida.strftime('%d/%m/%Y %H:%M')}", 0, 1, 'R')
    pdf.ln(5)
    
    # Datos del Envío
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f" Guia de Despacho: #ENV-{envio.id_envio}", 1, 1, 'L', True)
    
    pdf.set_font("Arial", '', 11)
    pdf.ln(5)
    pdf.cell(0, 8, f"Cliente: {envio.venta.cliente. nombre_contacto}", 0, 1)
    pdf.cell(0, 8, f"Destino: {envio.destino}", 0, 1)
    pdf.ln(5)
    
    # Datos de Transporte
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, "DATOS DEL TRANSPORTE", 0, 1)
    pdf.set_font("Arial", '', 11)
    pdf.cell(95, 8, f"Vehiculo: {envio.vehiculo.modelo}", 1)
    pdf.cell(95, 8, f"Placa: {envio.vehiculo.placa}", 1, 1)
    pdf.cell(190, 8, f"Chofer: {envio.chofer.nombre}", 1, 1)
    
    pdf.ln(20)
    
    # Firmas
    pdf.cell(95, 10, "__________________________", 0, 0, 'C')
    pdf.cell(95, 10, "__________________________", 0, 1, 'C')
    pdf.cell(95, 10, "Firma Despacho EcoData", 0, 0, 'C')
    pdf.cell(95, 10, "Firma de Recibido Cliente", 0, 1, 'C')

    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers.set('Content-Disposition', 'attachment', filename=f'Vale_{envio.id_envio}.pdf')
    response.headers.set('Content-Type', 'application/pdf')
    return response

@app.route('/reciclaje', methods=['GET', 'POST'])
def reciclaje():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        nuevo_lote = ProcesoReciclaje(
            lote=request.form['lote'],
            metal_origen=request.form['metal_origen'],
            peso_entrada_kg=float(request.form['peso_entrada']),
            id_maquina=request.form['id_maquina']
        )
        db.session.add(nuevo_lote)
        
        # Opcional: Aquí podrías restar el peso_entrada del Inventario de chatarra
        
        db.session.commit()
        return redirect(url_for('reciclaje'))

    procesos = ProcesoReciclaje.query.order_by(ProcesoReciclaje.fecha_inicio.desc()).all()
    maquinas = Maquina.query.all() # Traemos las máquinas/hornos disponibles
    
    return render_template('reciclaje.html', procesos=procesos, maquinas=maquinas)


@app.route('/finalizar_reciclaje/<int:id_proceso>', methods=['POST'])
def finalizar_reciclaje(id_proceso):
    if 'usuario' not in session:
        return redirect(url_for('login'))

    proceso = ProcesoReciclaje.query.get_or_404(id_proceso)
    
    if proceso.estado != 'Completado':
        peso_salida = float(request.form['peso_salida'])
        proceso.peso_salida_kg = peso_salida
        
        # Calculamos la merma
        proceso.merma_kg = proceso.peso_entrada_kg - peso_salida
        proceso.estado = 'Completado'
        proceso.fecha_fin = datetime.now()
        
        # --- INTEGRACIÓN CON INVENTARIO ---
        # 1. Buscamos si ya existe ese metal
        inventario = InventarioMetal.query.filter_by(tipo_metal=proceso.metal_origen).first()
        
        if inventario:
            # 2A. Si ya existe, simplemente le sumamos los kilos limpios
            inventario.cantidad_kg += peso_salida
        else:
            # 2B. Si no existe, lo creamos. 
            # NOTA: Usamos id_almacen=1 e id_proveedor=1 por defecto para evitar errores.
            nuevo_inventario = InventarioMetal(
                id_almacen=1,       # Se asigna al Almacén Principal (Asegúrate de que exista el ID 1)
                id_proveedor=1,     # Se asigna a un Proveedor Genérico/Interno (Asegúrate de que exista el ID 1)
                tipo_metal=proceso.metal_origen,
                cantidad_kg=peso_salida,
                fecha_entrada=date.today()
            )
            db.session.add(nuevo_inventario)
        # -----------------------------------
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Hubo un error al guardar o actualizar el inventario: {e}"
            
    return redirect(url_for('reciclaje'))

@app.route('/exportar_inventario')
def exportar_inventario():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # 1. Traemos todo el inventario de la base de datos
    registros = InventarioMetal.query.order_by(InventarioMetal.fecha_entrada.desc()).all()

    # 2. Creamos un archivo en la memoria del servidor
    si = io.StringIO()
    cw = csv.writer(si)

    # 3. Escribimos la primera fila (Los Encabezados)
    cw.writerow(['Folio Lote', 'Tipo de Metal', 'Cantidad (KG)', 'ID Almacen', 'ID Proveedor', 'Fecha de Entrada'])

    # 4. Recorremos los registros y escribimos fila por fila
    for r in registros:
        cw.writerow([
            f"INV-{r.id_inventario_m}",
            r.tipo_metal,
            r.cantidad_kg,
            r.id_almacen,
            r.id_proveedor,
            r.fecha_entrada.strftime('%d/%m/%Y')
        ])

    # 5. Preparamos la respuesta para que el navegador descargue el archivo
    # El "\ufeff" es un truco (BOM) para que Excel reconozca los acentos y las ñ correctamente
    output = make_response("\ufeff" + si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=Inventario_EcoData.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    
    return output

@app.route('/pedidos')
def lista_pedidos():
    # Usamos PedidoVenta que ya está conectado a tu clase Cliente
    pedidos = PedidoVenta.query.order_by(PedidoVenta.fecha_pedido.desc()).all()
    return render_template('pedidos.html', pedidos=pedidos)

@app.route('/nuevo_pedido', methods=['GET', 'POST'])
def nuevo_pedido():
    if request.method == 'POST':
        id_cliente = request.form.get('id_cliente')
        nuevo_p = PedidoVenta(id_cliente=id_cliente, estado='Pendiente', total=0.0)
        try:
            db.session.add(nuevo_p)
            db.session.commit()
            return redirect(url_for('detalle_pedido', id=nuevo_p.id_pedido))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al crear pedido: {str(e)}", "danger")
            
    clientes = Cliente.query.all()
    return render_template('nuevo_pedido.html', clientes=clientes)

@app.route('/pedido/<int:id>')
def detalle_pedido(id):
    pedido = PedidoVenta.query.get_or_404(id)
    # Consultamos productos y calculamos su stock actual manualmente para el select
    productos_con_stock = []
    todos_los_productos = Producto.query.all()
    
    for p in todos_los_productos:
        stock = db.session.query(func.sum(InventarioProducto.cantidad_stock))\
            .filter(InventarioProducto.id_producto == p.id_producto).scalar() or 0
        productos_con_stock.append({'obj': p, 'stock': stock})
        
    return render_template('detalle_pedido.html', pedido=pedido, productos=productos_con_stock)


@app.route('/despachar_pedido/<int:id_pedido>', methods=['POST'])
def despachar_pedido(id_pedido):
    pedido = PedidoVenta.query.get_or_404(id_pedido)
    
    if pedido.estado != 'Pendiente':
        flash("Este pedido ya fue procesado anteriormente.", "warning")
        return redirect(url_for('detalle_pedido', id=id_pedido))

    try:
        # 1. Recorrer los artículos del pedido para restar del inventario
        for item in pedido.detalles:
            # Buscamos el registro en InventarioProducto para ese ID de producto
            # (Si manejas varias bodegas, podrías filtrar también por id_almacen)
            inventario = InventarioProducto.query.filter_by(id_producto=item.id_producto).first()
            
            if inventario:
                if inventario.cantidad_stock >= item.cantidad:
                    inventario.cantidad_stock -= item.cantidad
                else:
                    # Una última validación de seguridad
                    flash(f"Error: Stock insuficiente para {item.producto.nombre_producto}", "danger")
                    db.session.rollback()
                    return redirect(url_for('detalle_pedido', id=id_pedido))
            else:
                flash(f"El producto {item.id_producto} no existe en inventario.", "danger")
                db.session.rollback()
                return redirect(url_for('detalle_pedido', id=id_pedido))

        # 2. Cambiar el estado del pedido
        pedido.estado = 'Despachado'
        
        db.session.commit()
        flash(f"Pedido #{id_pedido:04d} despachado con éxito. Inventario actualizado.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error crítico: {str(e)}", "danger")
        
    return redirect(url_for('lista_pedidos'))

@app.route('/agregar_item/<int:id_pedido>', methods=['POST'])
def agregar_item(id_pedido):
    id_prod = request.form.get('id_producto')
    qty_solicitada = int(request.form.get('cantidad'))
    
    # 1. Obtener el producto y su precio
    prod = Producto.query.get_or_404(id_prod)
    precio_vta = prod.precio  # Usamos la nueva columna precio de tu BD
    
    # 2. VALIDACIÓN DE INVENTARIO
    # Sumamos todo el stock disponible para este producto en todos los almacenes
    stock_disponible = db.session.query(func.sum(InventarioProducto.cantidad_stock))\
        .filter(InventarioProducto.id_producto == id_prod).scalar() or 0
    
    if qty_solicitada > stock_disponible:
        flash(f"Stock insuficiente. Solo tienes {stock_disponible} unidades de {prod.nombre_producto}.", "danger")
        return redirect(url_for('detalle_pedido', id=id_pedido))
    
    # 3. Si hay stock, procedemos a guardar
    subtotal = precio_vta * qty_solicitada
    
    nuevo_item = DetallePedido(
        id_pedido=id_pedido,
        id_producto=id_prod,
        cantidad=qty_solicitada,
        precio_unitario=precio_vta
    )
    
    # Actualizar el total de la cabecera del pedido
    pedido = PedidoVenta.query.get(id_pedido)
    pedido.total += subtotal
    
    try:
        db.session.add(nuevo_item)
        db.session.commit()
        flash(f"¡{prod.nombre_producto} agregado correctamente!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al guardar: {str(e)}", "danger")
        
    return redirect(url_for('detalle_pedido', id=id_pedido))

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
    # 1. Seguridad básica: Solo administradores pueden entrar aquí
    if 'usuario' not in session or session.get('rol') != 'Administrador':
        flash("Acceso denegado. Solo administradores pueden gestionar privilegios.", "error")
        return redirect(url_for('compras')) # O la ruta que uses como inicio

    # 2. Si se envía el formulario para cambiar un rol
    if request.method == 'POST':
        usuario_modificado = request.form.get('nombre_usuario')
        nuevo_rol = request.form.get('rol')
        
        # Buscamos si ya tiene un registro en la tabla RolUsuario
        rol_existente = RolUsuario.query.filter_by(nombre_usuario=usuario_modificado).first()
        
        if rol_existente:
            rol_existente.rol = nuevo_rol
        else:
            # Si por alguna razón no estaba en la tabla de roles, lo creamos
            nuevo_registro = RolUsuario(nombre_usuario=usuario_modificado, rol=nuevo_rol)
            db.session.add(nuevo_registro)
            
        db.session.commit()
        flash(f"Privilegios actualizados: {usuario_modificado} ahora es {nuevo_rol}.", "success")
        return redirect(url_for('privilegios'))

    # 3. GET: Traer todos los usuarios para mostrarlos en la tabla
    usuarios_db = InicioLog.query.all()
    
    # Creamos un diccionario rápido con los roles actuales para mostrar en el HTML
    # Quedará algo así: {'admin': 'Administrador', 'juan': 'Operador'}
    roles_asignados = {r.nombre_usuario: r.rol for r in RolUsuario.query.all()}

    return render_template('privilegios.html', usuarios=usuarios_db, roles_asignados=roles_asignados)

@app.route('/actualizar_bd')
def actualizar_bd():
    try:
        # Ejecutamos el comando SQL directo para agregar la columna
        db.session.execute(db.text("ALTER TABLE embarque ADD COLUMN tipo_metal VARCHAR(100) NOT NULL DEFAULT 'Sin Especificar';"))
        db.session.commit()
        return "¡Base de datos actualizada con éxito! Ya puedes usar el módulo de embarques."
    except Exception as e:
        return f"Ocurrió un error (quizás la columna ya existe): {e}"


if __name__ == '__main__':
    app.run(debug=True, port=5000)