import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Apex.settings')
django.setup()

from apex_app.csv_data import sync_database


def run():
    print("Leyendo CSV y actualizando la base de datos...")
    for row in sync_database():
        print(f"  {row['name']:<16} crecimiento {row['growth']:>6}%/año · riesgo {row['risk_level']}")
    print("¡Base de datos actualizada desde los CSV!")


if __name__ == '__main__':
    run()
