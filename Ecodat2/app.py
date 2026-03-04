from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Area, InicioLog, Proveedor, Almacen, Producto, InventarioMetal, InventarioProducto, Proceso, Transaccion, Cliente, Venta, RolUsuario, Compra
from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from datetime import date

app = Flask(__name__)
app.secret_key = 'hola123' # Necesario para las sesiones

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
mi_contrasena = "Belen123" 
password_segura = quote_plus(mi_contrasena)

# Conexión a PostgreSQL apuntando a la base de datos EcoData
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://postgres:Belen123@localhost:5432/ecodata'
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
    # Si ya tiene sesión, lo mandamos directo al panel
    if 'usuario' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        usuario_ingresado = request.form['usuario']
        password_ingresado = request.form['password']
        
        # 1. Buscamos si el usuario existe
        usuario_db = InicioLog.query.filter_by(usuario=usuario_ingresado).first()
        
        # 2. Comparamos la contraseña encriptada
        if usuario_db and check_password_hash(usuario_db.contrasena, password_ingresado):
            session['usuario'] = usuario_db.usuario
            
            # Buscamos su rol
            rol_db = RolUsuario.query.filter_by(nombre_usuario=usuario_db.usuario).first()
            if rol_db:
                session['rol'] = rol_db.rol
            else:
                session['rol'] = 'Operador' # Por defecto si no tiene
                
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear() # Borra los datos de la sesión
    return redirect(url_for('login'))
# --- RUTAS DE LA APLICACIÓN ---

@app.route('/dashboard')
def dashboard():
    # Validar que el usuario haya iniciado sesión
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # --- RECOPILAR DATOS PARA LAS GRÁFICAS ---
    # 1. Totales de Inventario
    total_metal = db.session.query(db.func.sum(InventarioMetal.cantidad_kg)).scalar() or 0
    total_productos = db.session.query(db.func.sum(InventarioProducto.cantidad_stock)).scalar() or 0
    
    # 2. Finanzas
    total_ingresos = db.session.query(db.func.sum(Transaccion.monto)).filter_by(tipo='Ingreso').scalar() or 0
    total_egresos = db.session.query(db.func.sum(Transaccion.monto)).filter_by(tipo='Egreso').scalar() or 0
    
    # 3. Procesos
    procesos_activos = Proceso.query.filter_by(estado='En progreso').count()
    
    return render_template('dashboard.html', 
                           usuario_actual=session['usuario'],
                           total_metal=total_metal,
                           total_productos=total_productos,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           procesos_activos=procesos_activos)

@app.route('/resumen')
def resumen_graficas():
    # 1. Gastos por Proveedor
    gastos = db.session.query(
        Proveedor.nombre, func.sum(Compra.total)
    ).join(Compra, Proveedor.id_proveedor == Compra.id_proveedor).group_by(Proveedor.nombre).all()
    
    nombres_prov = [g[0] for g in gastos]
    totales_prov = [float(g[1]) for g in gastos]

    # 2. Inventario de Metales
    inventario = db.session.query(
        InventarioMetal.tipo_metal, func.sum(InventarioMetal.cantidad_kg)
    ).group_by(InventarioMetal.tipo_metal).all()
    
    nombres_metal = [i[0] for i in inventario]
    cantidades_metal = [float(i[1]) for i in inventario]

    # 3. Estado de Procesos
    procesos = db.session.query(
        Proceso.estado, func.count(Proceso.id_proceso)
    ).group_by(Proceso.estado).all()
    
    estados_proc = [p[0] for p in procesos]
    cantidades_proc = [int(p[1]) for p in procesos]

    # 4. Total Financiero Histórico (Compras totales vs Ventas totales)
    total_compras = db.session.query(func.sum(Compra.total)).scalar() or 0.0
    
    # SOLUCIÓN: Forzamos las ventas a 0 por ahora para evitar el error
    total_ventas = 0.0

    return render_template('resumen.html', 
                           nombres_prov=nombres_prov, totales_prov=totales_prov,
                           nombres_metal=nombres_metal, cantidades_metal=cantidades_metal,
                           estados_proc=estados_proc, cantidades_proc=cantidades_proc,
                           total_compras=total_compras, total_ventas=total_ventas)

@app.route('/proveedores', methods=['GET', 'POST'])
def gestionar_proveedores():
    # 1. Protección de ruta: Solo usuarios logueados pueden entrar
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # 2. Si el usuario envía el formulario para agregar un proveedor
    if request.method == 'POST':
        nombre = request.form['nombre']
        rfc = request.form['rfc']
        telefono = request.form['telefono']
        correo = request.form['correo']
        
        # Guardamos en la base de datos
        nuevo_proveedor = Proveedor(nombre=nombre, rfc=rfc, telefono=telefono, correo_electronico=correo)
        db.session.add(nuevo_proveedor)
        db.session.commit()
        
        # Recargamos la página para ver el nuevo registro
        return redirect(url_for('gestionar_proveedores'))
        
    # 3. Si entra normalmente (GET), consultamos todos los proveedores y los mostramos
    lista_proveedores = Proveedor.query.all()
    return render_template('proveedores.html', proveedores=lista_proveedores)

@app.route('/compras', methods=['GET', 'POST'])
def gestionar_compras():
    # 1. Protección de ruta
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # 2. Si el usuario envía el formulario para registrar una compra
    if request.method == 'POST':
        # Obtenemos los datos del formulario HTML
        id_proveedor = request.form['id_proveedor']
        total = request.form['total']
        descripcion = request.form['descripcion']
        
        # Creamos el registro de la compra (la fecha se pone sola por el default=datetime.utcnow)
        nueva_compra = Compra(
            id_proveedor=id_proveedor, 
            total=total, 
            descripcion=descripcion
        )
        db.session.add(nueva_compra)
        db.session.commit()
        
        return redirect(url_for('gestionar_compras'))
        
    # 3. Si entra normalmente (GET)
    # Traemos las compras para la tabla y los proveedores para el menú desplegable
    lista_compras = Compra.query.all()
    lista_proveedores = Proveedor.query.all()
    
    return render_template('compras.html', compras=lista_compras, proveedores=lista_proveedores)

# --- MÓDULO BODEGAS / INVENTARIO DE METAL ---
@app.route('/bodegas', methods=['GET', 'POST'])
def bodegas():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        # Recibir los datos del formulario
        id_almacen = request.form.get('id_almacen')
        id_proveedor = request.form.get('id_proveedor')
        tipo_metal = request.form['tipo_metal']
        cantidad = request.form['cantidad']
        fecha = request.form['fecha_entrada']
        
        # Guardar en la base de datos
        nuevo_metal = InventarioMetal(
            id_almacen=id_almacen,
            id_proveedor=id_proveedor,
            tipo_metal=tipo_metal,
            cantidad_kg=cantidad,
            fecha_entrada=fecha
        )
        db.session.add(nuevo_metal)
        db.session.commit()
        flash('Entrada de metal registrada exitosamente.', 'success')
        return redirect(url_for('bodegas'))
        
    # Obtener los datos para mostrarlos en pantalla
    inventario = InventarioMetal.query.all()
    almacenes = Almacen.query.all()
    proveedores = Proveedor.query.all()
    
    return render_template('bodegas.html', 
                           inventario=inventario, 
                           almacenes=almacenes, 
                           proveedores=proveedores,
                           usuario_actual=session['usuario'])
    # --- NUEVO: Crear un par de Productos de prueba en el catálogo ---
    if not Producto.query.first():
        prod1 = Producto(nombre_producto="Pala de Acero", descripcion="Pala cuadrada uso rudo")
        prod2 = Producto(nombre_producto="Pico de Construcción", descripcion="Pico estándar")
        db.session.add_all([prod1, prod2])
        db.session.commit()
# --- MÓDULO PRODUCTOS / INVENTARIO DE HERRAMIENTAS ---
@app.route('/productos', methods=['GET', 'POST'])
def gestionar_productos():
    if request.method == 'POST':
        # Recibimos solo lo que tu tabla Producto acepta
        nombre = request.form['nombre_producto']
        descripcion = request.form['descripcion']
        
        # Creamos el nuevo producto
        nuevo_producto = Producto(
            nombre_producto=nombre, 
            descripcion=descripcion
        )
        
        # Guardamos en la base de datos
        db.session.add(nuevo_producto)
        db.session.commit()
        
        # Recargamos la página
        return redirect(url_for('gestionar_productos'))
        
    # Si es GET (entrar a la página), buscamos todos los productos
    productos = Producto.query.all()
    return render_template('productos.html', productos=productos)# --- MÓDULO PROCESOS DE FABRICACIÓN ---

@app.route('/inventario_productos', methods=['GET', 'POST'])
def inventario_productos():
    if request.method == 'POST':
        id_producto = request.form['id_producto']
        cantidad_nueva = int(request.form['cantidad'])
        # Recibimos el ID del almacén desde el formulario
        id_almacen = int(request.form['id_almacen']) 
        
        # Buscamos si el producto ya existe en ESE almacén específico
        inventario_actual = InventarioProducto.query.filter_by(
            id_producto=id_producto, 
            id_almacen=id_almacen
        ).first()
        
        if inventario_actual:
            # Si ya existe, usamos el nombre correcto de tu columna: cantidad_stock
            inventario_actual.cantidad_stock += cantidad_nueva
            # Actualizamos la fecha a hoy
            inventario_actual.fecha_fabricacion = date.today()
        else:
            # Si no existe, lo creamos con TODOS los campos obligatorios
            nuevo_registro = InventarioProducto(
                id_producto=id_producto, 
                id_almacen=id_almacen,
                cantidad_stock=cantidad_nueva,
                fecha_fabricacion=date.today()
            )
            db.session.add(nuevo_registro)
            
        db.session.commit()
        return redirect(url_for('inventario_productos'))
        
    # Si es GET
    productos_catalogo = Producto.query.all()
    inventario_total = InventarioProducto.query.all()
    
    return render_template('inventario_productos.html', 
                           productos=productos_catalogo, 
                           inventarios=inventario_total)

@app.route('/procesos', methods=['GET', 'POST'])
def procesos():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre_proceso = request.form['nombre_proceso']
        id_metal = request.form.get('id_metal')
        id_producto = request.form.get('id_producto')
        estado = request.form['estado']
        fecha_inicio = request.form['fecha_inicio']
        
        # Guardar el nuevo proceso
        nuevo_proceso = Proceso(
            nombre_proceso=nombre_proceso,
            id_inventario_m=id_metal,
            id_producto=id_producto,
            estado=estado,
            fecha_inicio=fecha_inicio
        )
        db.session.add(nuevo_proceso)
        db.session.commit()
        
        flash('Proceso de fabricación registrado exitosamente.', 'success')
        return redirect(url_for('procesos'))
        
    # Obtener datos para los selectores y la tabla
    lista_procesos = Proceso.query.all()
    lotes_metal = InventarioMetal.query.all() # Para saber qué materia prima usar
    catalogo_productos = Producto.query.all() # Para saber qué vamos a fabricar
    
    return render_template('procesos.html', 
                           procesos=lista_procesos, 
                           metales=lotes_metal, 
                           productos=catalogo_productos,
                           usuario_actual=session['usuario'])
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
# --- MÓDULO DE VENTAS Y CLIENTES (CRM) ---
@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        if 'form_cliente' in request.form:
            # 1. Guardar nuevo cliente
            nuevo_cliente = Cliente(
                nombre_contacto=request.form['nombre'],
                empresa=request.form['empresa'],
                telefono=request.form['telefono']
            )
            db.session.add(nuevo_cliente)
            db.session.commit()
            flash('Cliente registrado exitosamente.', 'success')
            
        elif 'form_venta' in request.form:
            # 2. Guardar nueva venta
            id_cliente = request.form['id_cliente']
            id_producto = request.form['id_producto']
            cantidad = request.form['cantidad']
            total_venta = float(request.form['total_venta'])
            fecha = request.form['fecha_venta']
            
            nueva_venta = Venta(
                id_cliente=id_cliente,
                id_producto=id_producto,
                cantidad=cantidad,
                total_venta=total_venta,
                fecha_venta=fecha
            )
            db.session.add(nueva_venta)
            
            # --- NUEVO: AUTOMATIZACIÓN CONTABLE ---
            # Consultamos el nombre del cliente y producto para que el recibo quede bonito
            cliente = Cliente.query.get(id_cliente)
            producto = Producto.query.get(id_producto)
            concepto_ingreso = f"Venta autom.: {cantidad} {producto.nombre_producto} a {cliente.empresa}"
            
            # Creamos el ingreso directamente en la contabilidad
            nuevo_ingreso = Transaccion(
                tipo='Ingreso',
                concepto=concepto_ingreso,
                monto=total_venta,
                fecha_transaccion=fecha
            )
            db.session.add(nuevo_ingreso)
            # --------------------------------------
            
            db.session.commit()
            flash('Venta registrada y dinero sumado a contabilidad exitosamente.', 'success')
            
        return redirect(url_for('ventas'))
        
    lista_clientes = Cliente.query.all()
    lista_ventas = Venta.query.all()
    catalogo_productos = Producto.query.all()
    
    return render_template('ventas.html', 
                           clientes=lista_clientes, 
                           ventas=lista_ventas,
                           productos=catalogo_productos,
                           usuario_actual=session['usuario'])
# --- MÓDULO DE PRIVILEGIOS Y GESTIÓN DE USUARIOS ---
@app.route('/usuarios', methods=['GET', 'POST'])
def usuarios():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if session.get('rol') != 'Administrador':
        flash('Acceso denegado: Solo los administradores pueden gestionar usuarios.', 'error')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        accion = request.form.get('accion')
        
        # ACCIÓN 1: CREAR O EDITAR USUARIO
        if accion == 'guardar':
            nombre_usuario = request.form['nombre_usuario']
            password_plano = request.form['password']
            nuevo_rol = request.form['rol']
            
            # 1. Guardar/Actualizar en la tabla de Inicio de Sesión (InicioLog)
            usuario_login = InicioLog.query.filter_by(usuario=nombre_usuario).first()
            if not usuario_login:
                # Si no existe, lo creamos con contraseña encriptada
                nuevo_user = InicioLog(
                    usuario=nombre_usuario, 
                    contrasena=generate_password_hash(password_plano)
                )
                db.session.add(nuevo_user)
            elif password_plano: 
                # Si ya existe y el admin escribió una nueva contraseña, se la actualizamos
                usuario_login.contrasena = generate_password_hash(password_plano)

            # 2. Guardar/Actualizar en la tabla de Roles (RolUsuario)
            usuario_rol = RolUsuario.query.filter_by(nombre_usuario=nombre_usuario).first()
            if not usuario_rol:
                db.session.add(RolUsuario(nombre_usuario=nombre_usuario, rol=nuevo_rol))
            else:
                usuario_rol.rol = nuevo_rol
                
            db.session.commit()
            flash(f'Usuario {nombre_usuario} guardado/actualizado correctamente.', 'success')
            
        # ACCIÓN 2: ELIMINAR USUARIO
        elif accion == 'eliminar':
            nombre_eliminar = request.form['nombre_usuario']
            
            # No permitir que el admin se elimine a sí mismo
            if nombre_eliminar == session['usuario']:
                flash('No puedes eliminar tu propia cuenta mientras estás conectado.', 'error')
            else:
                # Eliminar de ambas tablas
                RolUsuario.query.filter_by(nombre_usuario=nombre_eliminar).delete()
                InicioLog.query.filter_by(usuario=nombre_eliminar).delete()
                db.session.commit()
                flash(f'Usuario {nombre_eliminar} eliminado del sistema.', 'success')
                
        return redirect(url_for('usuarios'))
        
    # Consultar la lista de roles para mostrar en la tabla
    lista_roles = RolUsuario.query.all()
    return render_template('usuarios.html', 
                           roles=lista_roles, 
                           usuario_actual=session['usuario'],
                           rol_actual=session.get('rol'))

# --- RUTA PARA ELIMINAR USUARIO ---
@app.route('/eliminar_usuario/<int:id>')
def eliminar_usuario(id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    usuario_a_eliminar = InicioLog.query.get_or_404(id)
    
    # Protección: Evitar que se elimine al usuario "admin" principal
    if usuario_a_eliminar.usuario == 'admin':
        flash('Seguridad: No puedes eliminar al administrador principal.', 'error')
    else:
        db.session.delete(usuario_a_eliminar)
        db.session.commit()
        flash('Usuario eliminado correctamente.', 'success')
        
    return redirect(url_for('usuarios'))

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