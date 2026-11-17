import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse, Http404
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import Discipline, Investment
from .csv_data import RADAR_AXES, AXIS_NOTES, NOTES, sync_database

BALANCE_FROM_YEAR = 2010  # era moderna: el rango de años parte aquí por defecto
CAPITAL_RANGE = (50_000, 10_000_000)


@ensure_csrf_cookie
def dashboard_view(request):
    disciplines = Discipline.objects.all()
    context = {'disciplines': disciplines}
    return render(request, 'dashboard.html', context)


def api_chart_data(request):
    if not Discipline.objects.exists():
        sync_database()
    disciplines = Discipline.objects.prefetch_related(
        'radar_scores', 'regional_titles', 'balance_records', 'growth_metrics', 'series_points')

    radar_datasets, regional_dict, line_datasets, profiles = [], {}, [], []
    years = []
    for disc in disciplines:
        notes = NOTES.get(disc.slug, {})
        points = defaultdict(list)
        for p in disc.series_points.all():
            points[p.series].append(p)

        # 1. Radar (historia completa)
        scores = {s.axis: s.normalized_value for s in disc.radar_scores.all()}
        radar_datasets.append({
            'slug': disc.slug,
            'label': disc.name,
            'data': [scores.get(axis, 0) for axis in RADAR_AXES],
            'borderColor': disc.accent_color,
            'backgroundColor': disc.accent_color + '1f',
        })

        # 2. Poder Regional: totales + títulos con año para filtrar por rango
        titles = sorted(disc.regional_titles.all(), key=lambda t: -t.pct_of_total)
        by_year = [{'year': int(p.label), 'region': p.extra} for p in points['titulos']]
        years += [t['year'] for t in by_year]
        regional_dict[disc.slug] = {
            'name': disc.name,
            'labels': [t.region for t in titles],
            'data': [t.pct_of_total for t in titles],
            'counts': [t.title_count for t in titles],
            'by_year': by_year,
            'color': disc.accent_color,
            'note': notes.get('regional', ''),
            'sources': notes.get('sources', []),
        }

        # 3. Balance Competitivo (paridad por año)
        parity = sorted((int(r.era_label), r.value) for r in disc.balance_records.all())
        years += [y for y, _ in parity]
        line_datasets.append({
            'slug': disc.slug,
            'label': disc.name,
            'data': [{'x': year, 'y': v} for year, v in parity],
            'borderColor': disc.accent_color,
            'backgroundColor': disc.accent_color,
            'note': notes.get('parity', ''),
        })

        # 4. Perfil para el marcador, el comparador y el simulador
        growth = {g.metric_name: g.pct_change for g in disc.growth_metrics.all()}
        profiles.append({
            'slug': disc.slug,
            'name': disc.name,
            'color': disc.accent_color,
            'risk_level': disc.risk_level,
            'growth': growth.get('crecimiento_anual', 0),
            'volatility': growth.get('volatilidad', 0),
            'scores': scores,
            'parity_avg': round(sum(v for _, v in parity) / len(parity), 1) if parity else 0,
            'top_region': titles[0].region if titles else '',
            'top_share': titles[0].pct_of_total if titles else 0,
            'scale_note': notes.get('scale', ''),
        })

    user = request.user
    return JsonResponse({
        'radar': {'categories': RADAR_AXES, 'notes': AXIS_NOTES, 'datasets': radar_datasets},
        'regional': regional_dict,
        'balance': {'datasets': line_datasets},
        'disciplines': profiles,
        'years': {'min': min(years, default=BALANCE_FROM_YEAR), 'max': max(years, default=BALANCE_FROM_YEAR),
                  'default_from': BALANCE_FROM_YEAR},
        'user': {'authenticated': user.is_authenticated,
                 'name': (user.get_full_name() or user.get_username()) if user.is_authenticated else ''},
    })


def api_discipline(request, slug):
    try:
        disc = Discipline.objects.prefetch_related('series_points').get(slug=slug)
    except Discipline.DoesNotExist:
        raise Http404('Disciplina no encontrada')

    series = defaultdict(list)
    for p in disc.series_points.all():
        series[p.series].append(p)
    kpis = [{'label': p.label, 'value': p.value, 'unit': p.extra} for p in series.pop('kpi', [])]
    titles = [{'year': int(p.label), 'region': p.extra} for p in series.pop('titulos', [])]
    notes = NOTES.get(slug, {})
    return JsonResponse({
        'slug': disc.slug,
        'name': disc.name,
        'color': disc.accent_color,
        'risk_level': disc.risk_level,
        'kpis': kpis,
        'titles': titles,
        'series': {name: [{'label': p.label, 'value': p.value} for p in pts] for name, pts in series.items()},
        'scale_note': notes.get('scale', ''),
        'sources': notes.get('sources', []),
    })


@require_POST
def api_save_portfolio(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Inicia sesión para guardar tu portafolio.'}, status=401)
    try:
        body = json.loads(request.body)
        capital = Decimal(str(body['capital']))
        profile = body['risk_profile']
        allocation = {str(k): round(float(v), 2) for k, v in body['allocation'].items()}
        expected = float(body.get('expected_return', 0))
    except (ValueError, KeyError, TypeError, InvalidOperation, AttributeError):
        return JsonResponse({'error': 'Datos del portafolio inválidos.'}, status=400)

    valid_slugs = set(Discipline.objects.values_list('slug', flat=True))
    if not CAPITAL_RANGE[0] <= capital <= CAPITAL_RANGE[1]:
        return JsonResponse({'error': 'El capital está fuera del rango del simulador.'}, status=400)
    if profile not in dict(Investment.RISK_CHOICES) or not set(allocation) <= valid_slugs:
        return JsonResponse({'error': 'Perfil o disciplinas no reconocidos.'}, status=400)

    inv = Investment.objects.create(user=request.user, capital=capital, risk_profile=profile,
                                    allocation=allocation, expected_return=round(expected, 2))
    return JsonResponse({'id': inv.id, 'message': 'Portafolio guardado.'})
