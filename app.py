from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Area, InicioLog, Proveedor, Almacen, Producto, InventarioMetal, InventarioProducto, Proceso, Transaccion, Cliente, Venta, RolUsuario
from urllib.parse import quote_plus
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.security import generate_password_hash

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
def productos():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        id_producto = request.form.get('id_producto')
        id_almacen = request.form.get('id_almacen')
        cantidad = request.form['cantidad']
        fecha = request.form['fecha_fabricacion']
        
        # Registrar la nueva producción en el inventario
        nueva_produccion = InventarioProducto(
            id_producto=id_producto,
            id_almacen=id_almacen,
            cantidad_stock=cantidad,
            fecha_fabricacion=fecha
        )
        db.session.add(nueva_produccion)
        db.session.commit()
        
        flash('Producción de herramientas registrada exitosamente.', 'success')
        return redirect(url_for('productos'))
        
    # Obtener datos para mostrar en la pantalla
    inventario_prod = InventarioProducto.query.all()
    lista_productos = Producto.query.all()
    almacenes = Almacen.query.all()
    
    return render_template('productos.html', 
                           inventario=inventario_prod, 
                           productos=lista_productos, 
                           almacenes=almacenes,
                           usuario_actual=session['usuario'])
# --- MÓDULO PROCESOS DE FABRICACIÓN ---
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