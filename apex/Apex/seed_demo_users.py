"""
Crea usuarios de demostración (grupo "Demo") con actividad y portafolios inventados,
calculados con la misma lógica del simulador. Se puede correr varias veces: borra los demo anteriores.

También crea un administrador de prueba (si no existe) y guarda su contraseña en credenciales_demo.txt.
"""
import os
import random
import secrets
from datetime import timedelta
from decimal import Decimal

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Apex.settings')
django.setup()

from django.contrib.auth.models import Group, User
from django.utils import timezone

from apex_app.models import Discipline, Investment
from apex_app.portfolio import allocate

DEMO_USERS = [
    ('Camila', 'Rojas'), ('Matías', 'González'), ('Valentina', 'Muñoz'), ('Benjamín', 'Soto'),
    ('Isidora', 'Contreras'), ('Vicente', 'Silva'), ('Florencia', 'Martínez'), ('Tomás', 'Sepúlveda'),
    ('Antonia', 'Morales'), ('Joaquín', 'Rodríguez'), ('Josefa', 'Fuentes'), ('Agustín', 'Araya'),
    ('Martina', 'Espinoza'), ('Lucas', 'Reyes'), ('Emilia', 'Castillo'), ('Diego', 'Torres'),
]
CAPITALS = [100_000, 250_000, 500_000, 750_000, 1_000_000, 2_000_000, 3_500_000, 5_000_000, 8_000_000]
ADMIN_USERNAME = 'apex_admin'
CREDENTIALS_FILE = 'credenciales_demo.txt'


def profiles():
    rows = []
    for d in Discipline.objects.prefetch_related('radar_scores', 'growth_metrics'):
        growth = next((g.pct_change for g in d.growth_metrics.all() if g.metric_name == 'crecimiento_anual'), 0)
        rows.append({'slug': d.slug, 'risk_level': d.risk_level, 'growth': growth,
                     'scores': {s.axis: s.normalized_value for s in d.radar_scores.all()}})
    return rows


def ensure_admin():
    if User.objects.filter(username=ADMIN_USERNAME).exists():
        return None
    password = secrets.token_urlsafe(12)
    User.objects.create_superuser(ADMIN_USERNAME, '', password, first_name='Admin', last_name='APEX')
    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        f.write(f'Administrador de prueba (solo desarrollo local)\nusuario: {ADMIN_USERNAME}\ncontraseña: {password}\n')
    return CREDENTIALS_FILE


def run():
    disc = profiles()
    if not disc:
        print('La base no tiene disciplinas. Corre primero: python populate_db.py')
        return

    rng = random.Random(2026)
    now = timezone.now()
    demo, _ = Group.objects.get_or_create(name='Demo')
    deleted, _ = User.objects.filter(groups=demo).delete()

    n_inv = 0
    for i, (first, last) in enumerate(DEMO_USERS):
        username = f'{first[0]}{last}'.lower().replace('í', 'i').replace('ú', 'u').replace('é', 'e').replace('ñ', 'n')
        user = User.objects.create(username=username, first_name=first, last_name=last,
                                   email=f'{username}@demo.apex')
        user.set_unusable_password()
        user.date_joined = now - timedelta(days=rng.randint(40, 300))
        # ~70 % entró en los últimos 30 días; el resto está inactivo
        user.last_login = now - timedelta(days=rng.randint(0, 29) if rng.random() < 0.7 else rng.randint(31, 120),
                                          hours=rng.randint(0, 23))
        user.save()
        user.groups.add(demo)

        if rng.random() < 0.65:
            for _ in range(rng.choice([1, 1, 2, 3])):
                capital = rng.choice(CAPITALS)
                risk = rng.choice(['conservador', 'balanceado', 'balanceado', 'agresivo'])
                allocation, expected = allocate(disc, capital, risk)
                inv = Investment.objects.create(user=user, capital=Decimal(capital), risk_profile=risk,
                                                allocation=allocation, expected_return=expected)
                when = user.date_joined + timedelta(days=rng.randint(1, max(2, (now - user.date_joined).days)))
                Investment.objects.filter(pk=inv.pk).update(created_at=min(when, now))
                n_inv += 1

    print(f'Usuarios demo: {len(DEMO_USERS)} creados ({deleted} registros anteriores borrados), {n_inv} portafolios.')
    created = ensure_admin()
    if created:
        print(f'Administrador de prueba creado. Usuario y contraseña en {created}')


if __name__ == '__main__':
    run()
