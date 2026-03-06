from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Area, InicioLog, Proveedor, Almacen, Producto, InventarioMetal, InventarioProducto, Proceso, Transaccion, Cliente, Venta, RolUsuario, Mantenimiento, Maquina, Calidad, Vehiculo, Chofer, Envio, ProcesoReciclaje
from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.security import generate_password_hash
from datetime import date
from datetime import datetime
from sqlalchemy import func
from fpdf import FPDF
from flask import make_response
from sqlalchemy import func
import csv
import io
from flask import make_response

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



# Ruta principal: Inicio de sesión
@app.route('/') # La ruta raíz también te lleva al login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        passw = request.form['password']
        
        # 1. Buscamos al usuario en la tabla de credenciales
        usuario_db = InicioLog.query.filter_by(usuario=user).first()
        
        # 2. Verificamos si existe y si la contraseña coincide con el hash
        if usuario_db and check_password_hash(usuario_db.contrasena, passw):
            session['usuario'] = user
            
            # 3. Buscamos el rol en tu tabla RolUsuario
            permiso = RolUsuario.query.filter_by(nombre_usuario=user).first()
            if permiso:
                session['rol'] = permiso.rol # Guardará 'Administrador' u 'Operador'
            else:
                session['rol'] = 'Operador' # Por seguridad, si no tiene rol es Operador
                
            return redirect(url_for('dashboard'))
        else:
            return "Credenciales inválidas, intenta de nuevo."
            
    return render_template('login.html')

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
    
    # 1. KPIs Generales
    metales = InventarioMetal.query.all()
    total_kilos = sum(m.cantidad_kg for m in metales if m.cantidad_kg)
    
    productos_inv = InventarioProducto.query.all()
    total_piezas = sum(p.cantidad_stock for p in productos_inv if p.cantidad_stock)
    
    procesos_activos = Proceso.query.filter_by(estado='En progreso').count()
    
    try:
        total_ventas = Venta.query.count()
    except:
        total_ventas = 0

    # 2. DATOS PARA LAS GRÁFICAS
    # Gráfica 1: Stock de Productos
    nombres_prod = []
    cantidades_prod = []
    for inv in productos_inv:
        prod = Producto.query.get(inv.id_producto)
        if prod:
            # Si hay varios lotes del mismo producto, los mostramos por separado
            nombres_prod.append(f"{prod.nombre_producto} (Almacén {inv.id_almacen})")
            cantidades_prod.append(inv.cantidad_stock)
            
    # Gráfica 2: Kilos de metales
    tipos_metal = []
    kilos_metal = []
    for m in metales:
        tipos_metal.append(f"{m.tipo_metal} (Lote {m.id_inventario_m})")
        kilos_metal.append(m.cantidad_kg)

    return render_template('dashboard.html', 
                           usuario_actual=session['usuario'],
                           total_kilos=round(total_kilos, 2),
                           total_piezas=total_piezas,
                           procesos_activos=procesos_activos,
                           total_ventas=total_ventas,
                           nombres_prod=nombres_prod,
                           cantidades_prod=cantidades_prod,
                           tipos_metal=tipos_metal,
                           kilos_metal=kilos_metal)


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
        
        # Creamos el producto solo con los campos de tu modelo
        nuevo_producto = Producto(
            nombre_producto=nombre_producto, 
            descripcion=descripcion
        )
        db.session.add(nuevo_producto)
        db.session.commit()
        
        return redirect(url_for('productos'))
        
    lista_productos = Producto.query.all()
    return render_template('productos.html', productos=lista_productos)

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
# --- MÓDULO DE ADMINISTRACIÓN CONTABLE ---
@app.route('/contabilidad', methods=['GET', 'POST'])
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

# --- RUTA PARA ELIMINAR USUARIO ---
@app.route('/eliminar_usuario/<int:id_rol>')
def eliminar_usuario(id_rol):
    # 1. Verificación de seguridad: Solo el Administrador puede borrar
    if 'usuario' not in session or session.get('rol') != 'Administrador':
        return redirect(url_for('login'))

    # 2. Buscamos el registro en la tabla de roles
    usuario_rol = RolUsuario.query.get_or_404(id_rol)
    nombre = usuario_rol.nombre_usuario

    # 3. Evitar que el administrador se borre a sí mismo por accidente
    if nombre == session.get('usuario'):
        # Puedes retornar un mensaje de error o simplemente redirigir
        return redirect(url_for('usuarios'))

    # 4. Buscamos el registro correspondiente en la tabla de login
    usuario_login = InicioLog.query.filter_by(usuario=nombre).first()

    try:
        # Borramos de ambas tablas
        db.session.delete(usuario_rol)
        if usuario_login:
            db.session.delete(usuario_login)
        
        db.session.commit()
    except:
        db.session.rollback()
        return "Error al intentar eliminar el usuario."

    return redirect(url_for('usuarios'))

@app.errorhandler(403)
def access_denied(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# --- RUTA PARA EDITAR USUARIO ---
@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
def editar_usuario(id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    usuario_a_editar = InicioLog.query.get_or_404(id)
    lista_areas = Area.query.all()
    
    if request.method == 'POST':
        usuario_a_editar.usuario = request.form['usuario']
        usuario_a_editar.id_area = request.form.get('id_area')
        
        # Solo actualizamos la contraseña si el campo no está vacío
        nueva_contra = request.form['contrasena']
        if nueva_contra.strip() != "":
            usuario_a_editar.contrasena = nueva_contra
            
        db.session.commit()
        flash('Usuario actualizado correctamente.', 'success')
        return redirect(url_for('usuarios'))
        
    return render_template('editar_usuario.html', 
                           user=usuario_a_editar, 
                           areas=lista_areas, 
                           usuario_actual=session['usuario'])



if __name__ == '__main__':
    app.run(debug=True, port=5000)