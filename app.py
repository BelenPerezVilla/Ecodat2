from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Area, InicioLog
from urllib.parse import quote_plus

app = Flask(__name__)
app.secret_key = 'hola123' # Necesario para las sesiones

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
mi_contrasena = "Hola123" 
password_segura = quote_plus(mi_contrasena)

# Conexión a PostgreSQL apuntando a la base de datos EcoData
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://postgres:Hola123@localhost:5432/EcoData'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

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

# Ruta principal: Inicio de sesión
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contrasena = request.form['contrasena']
        
        # Buscar usuario en la base de datos
        user = InicioLog.query.filter_by(usuario=usuario, contrasena=contrasena).first()
        
        if user:
            session['id_usuario'] = user.id_usuario
            session['usuario'] = user.usuario
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
            
    return render_template('index.html')

# Ruta del Dashboard
@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', usuario=session['usuario'])

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.pop('id_usuario', None)
    session.pop('usuario', None)
    return redirect(url_for('login'))
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

# --- NUEVO MÓDULO: PRIVILEGIOS (USUARIOS) ---
@app.route('/usuarios', methods=['GET', 'POST'])
def usuarios():
    # Validar que el usuario haya iniciado sesión
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # Si se envía el formulario para crear un usuario
    if request.method == 'POST':
        nuevo_usuario = request.form['usuario']
        nueva_contra = request.form['contrasena']
        id_area = request.form.get('id_area')

        # Verificar que el usuario no exista ya en la base de datos
        if InicioLog.query.filter_by(usuario=nuevo_usuario).first():
            flash('Error: El nombre de usuario ya existe.', 'error')
        else:
            # Crear y guardar el nuevo usuario
            nuevo_registro = InicioLog(usuario=nuevo_usuario, contrasena=nueva_contra, id_area=id_area)
            db.session.add(nuevo_registro)
            db.session.commit()
            flash('Usuario registrado exitosamente.', 'success')
            
        return redirect(url_for('usuarios'))

    # Si entramos normalmente (GET), obtenemos la lista de usuarios y áreas
    lista_usuarios = InicioLog.query.all()
    lista_areas = Area.query.all()
    
    return render_template('usuarios.html', 
                           usuarios=lista_usuarios, 
                           areas=lista_areas, 
                           usuario_actual=session['usuario'])

if __name__ == '__main__':
    app.run(debug=True, port=5000)