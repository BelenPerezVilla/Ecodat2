from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ==========================================
# 1. TABLAS DE USUARIOS (Módulo Privilegios)
# ==========================================
class Area(db.Model):
    __tablename__ = 'area'
    id_area = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_area = db.Column(db.String(100), nullable=False)
    usuarios = db.relationship('InicioLog', backref='area', lazy=True)

class InicioLog(db.Model):
    __tablename__ = 'inicio_log'
    id_usuario = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_area = db.Column(db.Integer, db.ForeignKey('area.id_area'), nullable=True)
    usuario = db.Column(db.String(50), nullable=False, unique=True)
    contrasena = db.Column(db.String(255), nullable=False)

# ==========================================
# 2. TABLAS DE BODEGAS E INVENTARIOS
# ==========================================

# Tabla de Proveedores de chatarra
class Proveedor(db.Model):
    __tablename__ = 'proveedor'
    id_proveedor = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(150), nullable=False)
    telefono = db.Column(db.String(20))
    # Relación: Un proveedor puede tener muchas entregas de metal
    entregas_metal = db.relationship('InventarioMetal', backref='proveedor', lazy=True)

# Tabla de Almacenes (Bodegas)
class Almacen(db.Model):
    __tablename__ = 'almacen'
    id_almacen = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_almacen = db.Column(db.String(100), nullable=False)
    ubicacion = db.Column(db.String(255))
    # Relaciones con los inventarios
    inventario_metal = db.relationship('InventarioMetal', backref='almacen', lazy=True)
    inventario_producto = db.relationship('InventarioProducto', backref='almacen', lazy=True)

# Tabla de Productos (Herramientas de construcción creadas)
class Producto(db.Model):
    __tablename__ = 'producto'
    id_producto = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_producto = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    inventario_producto = db.relationship('InventarioProducto', backref='producto', lazy=True)

# Tabla de Inventario de Metal (Materia Prima)
class InventarioMetal(db.Model):
    __tablename__ = 'inventario_metal'
    id_inventario_m = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_almacen = db.Column(db.Integer, db.ForeignKey('almacen.id_almacen'), nullable=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey('proveedor.id_proveedor'), nullable=False)
    tipo_metal = db.Column(db.String(100), nullable=False) # Ej. Acero, Aluminio, Cobre
    cantidad_kg = db.Column(db.Float, nullable=False)      # Peso en Kilogramos
    fecha_entrada = db.Column(db.Date, nullable=False)

# Tabla de Inventario de Productos (Herramientas Finales)
class InventarioProducto(db.Model):
    __tablename__ = 'inventario_producto'
    id_inventario_p = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_almacen = db.Column(db.Integer, db.ForeignKey('almacen.id_almacen'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('producto.id_producto'), nullable=False)
    cantidad_stock = db.Column(db.Integer, nullable=False) # Piezas disponibles
    fecha_fabricacion = db.Column(db.Date, nullable=False)
# ==========================================
# 3. TABLA DE PROCESOS DE FABRICACIÓN
# ==========================================
class Proceso(db.Model):
    __tablename__ = 'proceso'
    id_proceso = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_proceso = db.Column(db.String(150), nullable=False) # Ej. "Fundición de palas lote A"
    id_inventario_m = db.Column(db.Integer, db.ForeignKey('inventario_metal.id_inventario_m'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('producto.id_producto'), nullable=False)
    estado = db.Column(db.String(50), nullable=False, default='En progreso') 
    fecha_inicio = db.Column(db.Date, nullable=False)

    # Relaciones para conectar la tabla fácilmente
    metal = db.relationship('InventarioMetal', backref='procesos_asignados', lazy=True)
    producto_final = db.relationship('Producto', backref='procesos_asignados', lazy=True)

# ==========================================
# 4. TABLA DE ADMINISTRACIÓN CONTABLE
# ==========================================
class Transaccion(db.Model):
    __tablename__ = 'transaccion'
    id_transaccion = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tipo = db.Column(db.String(50), nullable=False) # 'Ingreso' o 'Egreso'
    concepto = db.Column(db.String(255), nullable=False) # Ej. 'Venta de palas', 'Pago a proveedor'
    monto = db.Column(db.Float, nullable=False)
    fecha_transaccion = db.Column(db.Date, nullable=False)

# ==========================================
# 5. MÓDULO DE VENTAS Y CLIENTES (CRM)
# ==========================================
class Cliente(db.Model):
    __tablename__ = 'cliente'
    id_cliente = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_contacto = db.Column(db.String(150), nullable=False)
    empresa = db.Column(db.String(150), nullable=False) # Ej. "Ferretería El Tornillo"
    telefono = db.Column(db.String(50), nullable=True)

class Venta(db.Model):
    __tablename__ = 'venta'
    id_venta = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('cliente.id_cliente'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('producto.id_producto'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    total_venta = db.Column(db.Float, nullable=False)
    fecha_venta = db.Column(db.Date, nullable=False)

    # Relaciones para conectar la venta con el cliente y el producto
    cliente = db.relationship('Cliente', backref='compras', lazy=True)
    producto = db.relationship('Producto', backref='ventas', lazy=True)