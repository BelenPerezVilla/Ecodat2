from app import app, db
from app import InicioLog, RolUsuario # O de 'models' si los tienes separados
from werkzeug.security import generate_password_hash

with app.app_context():
    # 1. Buscamos si el usuario 'admin' ya existe en la base de datos
    admin_user = InicioLog.query.filter_by(usuario='admin').first()

    if admin_user:
        # Si ya existe, solo le ACTUALIZAMOS la contraseña al nuevo formato encriptado
        admin_user.contrasena = generate_password_hash('admin123')
        print("Usuario 'admin' encontrado. Contraseña actualizada correctamente.")
    else:
        # Si no existe, lo creamos de cero
        nuevo_admin = InicioLog(
            usuario='admin', 
            contrasena=generate_password_hash('admin123') 
        )
        db.session.add(nuevo_admin)
        print("Usuario 'admin' creado desde cero.")

    # 2. Hacemos lo mismo para asegurarnos de que tenga el rol de Administrador
    admin_rol = RolUsuario.query.filter_by(nombre_usuario='admin').first()
    if admin_rol:
        admin_rol.rol = 'Administrador'
    else:
        nuevo_rol = RolUsuario(nombre_usuario='admin', rol='Administrador')
        db.session.add(nuevo_rol)

    # 3. Guardamos los cambios
    db.session.commit()
    print("¡Listo! El sistema está preparado.")