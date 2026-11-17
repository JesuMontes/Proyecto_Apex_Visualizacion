# APEX | Capital & Intelligence

Dashboard en Django que analiza cuatro competencias (FIFA World Cup, LoL Worlds, CS2 y StarCraft II) a partir de archivos CSV.

## Cómo correrlo (Windows, PowerShell)

Desde esta carpeta (`apex/Apex`):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python populate_db.py
python seed_demo_users.py
python manage.py runserver
```

`populate_db.py` carga la base desde los CSV y `seed_demo_users.py` crea los usuarios de prueba
(un administrador y un manager). Sus contraseñas quedan en `credenciales_demo.txt`, que no se sube a GitHub.

Si PowerShell no deja activar el entorno, corre primero:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Después abre:
- Dashboard: http://127.0.0.1:8000
- Admin: http://127.0.0.1:8000/admin (usuario `apex_admin`)
- Perfil manager: http://127.0.0.1:8000/manager (usuario `apex_manager`)

Los próximos días, basta con activar el entorno y correr `python manage.py runserver`.

## Perfiles

- **Administrador** (`is_staff`): al iniciar sesión entra directo al admin.
- **Manager** (grupo `Manager`): al iniciar sesión entra a `/manager/`, con los equipos y su rendimiento por torneo
  y las estadísticas de cada jugador. Para hacer manager a otro usuario, agrégalo al grupo `Manager` desde el admin.
- **Usuario normal**: entra al dashboard.

## Datos

Los CSV están en las carpetas `counter`, `fifa_dataset`, `lol_dataset` y `starcraft 2`, dos niveles por encima de esta carpeta. No cambies esa estructura.

Si modificas un CSV, recarga la base con `python populate_db.py` o con el botón «Sincronizar desde CSV» del admin.

Para volver a crear los usuarios de demostración: `python seed_demo_users.py`.
