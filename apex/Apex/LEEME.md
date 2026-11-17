# APEX | Capital & Intelligence

Dashboard en Django que analiza cuatro competencias (FIFA World Cup, LoL Worlds, CS2 y StarCraft II) a partir de archivos CSV.

## Cómo correrlo (Windows, PowerShell)

Desde esta carpeta (`apex/Apex`):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Si PowerShell no deja activar el entorno, corre primero:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Después abre:
- Dashboard: http://127.0.0.1:8000
- Admin: http://127.0.0.1:8000/admin (con el usuario que creaste)

La base `db.sqlite3` ya viene cargada. Los próximos días, basta con activar el entorno y correr `python manage.py runserver`.

## Datos

Los CSV están en las carpetas `counter`, `fifa_dataset`, `lol_dataset` y `starcraft 2`, dos niveles por encima de esta carpeta. No cambies esa estructura.

Si modificas un CSV, recarga la base con `python populate_db.py` o con el botón «Sincronizar desde CSV» del admin.

Para volver a crear los usuarios de demostración: `python seed_demo_users.py`.
