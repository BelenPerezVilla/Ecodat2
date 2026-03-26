from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

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
    precio = db.Column(db.Float, default=0.0) # <--- Agrega esta línea

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
# ==========================================
# 6. MÓDULO DE PRIVILEGIOS (ROLES)
# ==========================================
class RolUsuario(db.Model):
    __tablename__ = 'rol_usuario'
    id_rol = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_usuario = db.Column(db.String(50), nullable=False, unique=True)
    rol = db.Column(db.String(50), nullable=False) # 'Administrador' u 'Operador'

class Maquina(db.Model):
    __tablename__ = 'maquina'
    id_maquina = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(100), nullable=False) # Ej. "Fundidora 1", "Prensa Hidráulica"
    modelo = db.Column(db.String(100))
    estado = db.Column(db.String(50), default='Operativa') # Operativa, En Reparación, Fuera de Servicio

class Mantenimiento(db.Model):
    __tablename__ = 'mantenimiento'
    id_mantenimiento = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_maquina = db.Column(db.Integer, db.ForeignKey('maquina.id_maquina'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False) # Preventivo o Correctivo
    descripcion = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    costo = db.Column(db.Float, default=0.0)
    tecnico = db.Column(db.String(100))
    fecha_proxima = db.Column(db.Date, nullable=True) 
    foto_evidencia = db.Column(db.String(150), nullable=True) # Ruta o URL de la foto

    maquina = db.relationship('Maquina', backref='historial_mantenimiento', lazy=True)
class Calidad(db.Model):
    __tablename__ = 'control_calidad'
    id_inspeccion = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_producto = db.Column(db.Integer, db.ForeignKey('producto.id_producto'), nullable=False)
    fecha_inspeccion = db.Column(db.Date, nullable=False)
    inspector = db.Column(db.String(100), nullable=False)
    resultado = db.Column(db.String(20), nullable=False) 
    observaciones = db.Column(db.Text)
    parametros_tecnicos = db.Column(db.String(200))

    producto = db.relationship('Producto', backref='controles_calidad')

class Vehiculo(db.Model):
    __tablename__ = 'vehiculos'
    id_vehiculo = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(20), unique=True, nullable=False)
    modelo = db.Column(db.String(50))
    capacidad_kg = db.Column(db.Float) # Importante para metales
    estado = db.Column(db.String(20), default='Disponible') # Disponible, En Ruta, Taller

class Chofer(db.Model):
    __tablename__ = 'choferes'
    id_chofer = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    licencia = db.Column(db.String(50))
    telefono = db.Column(db.String(20))

class Envio(db.Model):
    __tablename__ = 'envios'
    id_envio = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('venta.id_venta')) # Vinculado a la venta
    id_vehiculo = db.Column(db.Integer, db.ForeignKey('vehiculos.id_vehiculo'))
    id_chofer = db.Column(db.Integer, db.ForeignKey('choferes.id_chofer'))
    fecha_salida = db.Column(db.DateTime, default=datetime.now)
    destino = db.Column(db.String(200))
    estado_entrega = db.Column(db.String(20), default='En Tránsito') # En Tránsito, Entregado, Cancelado

    # Relaciones para consultas fáciles
    venta = db.relationship('Venta', backref='envio')
    vehiculo = db.relationship('Vehiculo', backref='envios')
    chofer = db.relationship('Chofer', backref='envios')

class ProcesoReciclaje(db.Model):
    __tablename__ = 'procesos_reciclaje'
    id_proceso = db.Column(db.Integer, primary_key=True)
    lote = db.Column(db.String(50), unique=True, nullable=False)
    metal_origen = db.Column(db.String(50)) # Ej: Aluminio, Cobre Mixto
    peso_entrada_kg = db.Column(db.Float, nullable=False) # Chatarra inicial
    peso_salida_kg = db.Column(db.Float) # Metal limpio resultante
    merma_kg = db.Column(db.Float) # Lo que se perdió/quemó
    fecha_inicio = db.Column(db.DateTime, default=datetime.now)
    fecha_fin = db.Column(db.DateTime)
    estado = db.Column(db.String(20), default='En Proceso') # En Proceso, Completado
    id_maquina = db.Column(db.Integer, db.ForeignKey('maquina.id_maquina')) # Asumiendo que tu tabla es 'maquina'

    # Relación
    maquina = db.relationship('Maquina', backref='procesos_reciclaje')

class Embarque(db.Model):
    __tablename__ = 'embarque'
    id_embarque = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tipo_movimiento = db.Column(db.String(50), nullable=False) # 'Entrada (Compra)' o 'Salida (Venta)'
    placas = db.Column(db.String(20), nullable=False)
    chofer = db.Column(db.String(100))
    origen_destino = db.Column(db.String(150)) # Nombre del Proveedor o Cliente
    tipo_metal = db.Column(db.String(100), nullable=False)
    peso_bruto_kg = db.Column(db.Float, nullable=False) # Camión lleno
    peso_tara_kg = db.Column(db.Float, nullable=False)  # Camión vacío
    peso_neto_kg = db.Column(db.Float, nullable=False)  # Kilos reales de material
    fecha_registro = db.Column(db.DateTime, default=datetime.now)

class Maquinaria(db.Model):
    __tablename__ = 'maquinaria'
    id_maquina = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_equipo = db.Column(db.String(100), nullable=False) # Ej: Prensa Hidráulica 1, Montacargas B
    tipo = db.Column(db.String(50), nullable=False) # Ej: Prensa, Montacargas, Trituradora
    marca = db.Column(db.String(50))
    modelo = db.Column(db.String(50))
    numero_serie = db.Column(db.String(50))
    estado = db.Column(db.String(30), default='Activa', nullable=False) # Activa, En Mantenimiento, Inactiva
    proximo_mantenimiento = db.Column(db.Date) # Para saber cuándo le toca servicio

class Compra(db.Model):
    __tablename__ = 'compra'
    id_compra = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_proveedor = db.Column(db.Integer, db.ForeignKey('proveedor.id_proveedor'), nullable=False)
    
    # Detalles del producto/material comprado
    producto = db.Column(db.String(150), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    
    # Totales y Facturación
    subtotal = db.Column(db.Float, nullable=False)
    iva = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    folio_factura = db.Column(db.String(100)) # ¡Aquí guardamos la factura!
    
    fecha_compra = db.Column(db.DateTime, default=db.func.current_timestamp())
    estado = db.Column(db.String(50), default='Pagada') # Pendiente, Pagada, Cancelada

    # Relación para jalar el nombre del proveedor automáticamente
    proveedor = db.relationship('Proveedor', backref='compras_realizadas')

class PedidoVenta(db.Model):
    __tablename__ = 'pedidos_venta'
    id_pedido = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('cliente.id_cliente'))
    cliente = db.relationship('Cliente', backref='pedidos')
     # Asegúrate que tu tabla clientes use id_cliente
    fecha_pedido = db.Column(db.DateTime, default=db.func.current_timestamp())
    estado = db.Column(db.String(20), default='Pendiente')
    total = db.Column(db.Float, default=0.0)
    
    # Esta es la línea que causaba el error, ahora ya tendrá a quién buscar
    detalles = db.relationship('DetallePedido', backref='pedido', lazy=True)

class DetallePedido(db.Model):
    __tablename__ = 'detalle_pedido'
    id_detalle = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos_venta.id_pedido'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('producto.id_producto'))
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)

    # ESTA ES LA LÍNEA QUE FALTA:
    # Le dice a SQLAlchemy: "Cuando pida .producto, búscalo en la clase Producto"
    producto = db.relationship('Producto', backref='detalles_pedido')


class Auditoria(db.Model):
    __tablename__ = 'auditoria'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    usuario = db.Column(db.String(50))
    accion = db.Column(db.String(100))
    modulo = db.Column(db.String(50))
    detalle = db.Column(db.Text)
    ip = db.Column(db.String(20))