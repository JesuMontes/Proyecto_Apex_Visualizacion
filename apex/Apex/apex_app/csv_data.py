"""
Lectura de los CSV de cada disciplina y cálculo de todas las métricas del dashboard.

Cada disciplina se resume en cuatro piezas:
  - serie de escala anual   -> Crecimiento (pendiente log-lineal) y Estabilidad (volatilidad)
  - actividad anual         -> partidos/series por año
  - paridad anual           -> % de enfrentamientos que llegaron al juego decisivo
  - títulos por región      -> Poder Regional y Accesibilidad

Las rutas apuntan a las carpetas de datos que están junto al proyecto Django
(counter/, fifa_dataset/, lol_dataset/, starcraft 2/).
"""
import csv
import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from django.conf import settings

RADAR_AXES = ['Crecimiento', 'Estabilidad', 'Actividad', 'Paridad', 'Accesibilidad']

CIS = {'RU', 'UA', 'KZ', 'BY', 'UZ', 'KG', 'AM', 'AZ', 'GE', 'MD', 'TJ', 'TM'}
CONTINENT_ES = {
    'Europe': 'Europa', 'Asia': 'Asia', 'North America': 'Norteamérica',
    'South America': 'Sudamérica', 'Oceania': 'Oceanía', 'Africa': 'África',
}


def data_dir():
    return Path(getattr(settings, 'APEX_DATA_DIR', Path(settings.BASE_DIR).parent.parent))


def read_csv(*parts):
    with open(data_dir().joinpath(*parts), encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def series_score(text):
    """'3-1', '2–1' -> (3, 1). Devuelve None si no se puede leer."""
    nums = re.findall(r'\d+', text or '')
    if len(nums) != 2:
        return None
    return int(nums[0]), int(nums[1])


def is_decider(a, b):
    """Serie al mejor de 3 o más que se definió en el último juego (2-1, 3-2, 4-3)."""
    hi, lo = max(a, b), min(a, b)
    return hi >= 2 and lo == hi - 1


def pct(part, total):
    return round(100 * part / total, 1) if total else 0.0


def log_trend(points):
    """Ajuste log-lineal sobre [(año, valor)]: crecimiento anual % y volatilidad (desv. de residuos)."""
    pts = [(x, math.log(y)) for x, y in points if y > 0]
    n = len(pts)
    if n < 3:
        return 0.0, 0.0
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    slope = sum((x - mx) * (y - my) for x, y in pts) / sxx
    resid = [y - (my + slope * (x - mx)) for x, y in pts]
    sigma = math.sqrt(sum(r * r for r in resid) / (n - 2))
    return round((math.exp(slope) - 1) * 100, 2), round(sigma * 100, 2)


def regional_shares(counter):
    total = sum(counter.values())
    return [{'region': r, 'count': c, 'pct': pct(c, total)} for r, c in counter.most_common()]


def minutes(text):
    """'32:06' -> 32.1 minutos."""
    m, _, sec = (text or '').partition(':')
    return round(int(m) + int(sec or 0) / 60, 1) if m.isdigit() else 0.0


def country_continents():
    mapping = {}
    for row in read_csv('starcraft 2', 'country-and-continent-codes-list.csv'):
        code = (row['Two_Letter_Country_Code'] or '').upper()
        mapping.setdefault(code, row['Continent_Name'])
    return mapping


# ---------------------------------------------------------------------------
# League of Legends Worlds
# ---------------------------------------------------------------------------
LOL_REGIONS = {
    'Korea': 'Corea (KR)', 'China': 'China (CN)', 'Europe': 'Europa (EU)',
    'North America': 'Norteamérica (NA)', 'Taiwan/HK/Macau (GPL)': 'Taiwán/HK/Macao',
}


def load_lol():
    summary = list(read_csv('lol_dataset', '01_Worlds_Event_Tournament_Summary.csv'))
    scale = [(int(r['Year']), to_float(r['Prize_Pool_USD'])) for r in summary]

    stats = list(read_csv('lol_dataset', '09_Worlds_Match_Statistics_golgg.csv'))
    games = [to_float(r['Games_Played']) for r in stats]
    activity = sum(games) / len(games) if games else 0

    parity = defaultdict(lambda: [0, 0])
    for r in read_csv('lol_dataset', '03_Worlds_Knockout_Bracket_Results.csv'):
        sc = series_score(r['Score'])
        if sc:
            parity[int(r['Year'])][0] += is_decider(*sc)
            parity[int(r['Year'])][1] += 1

    titles = Counter(LOL_REGIONS.get(r['Winner_Region'], r['Winner_Region']) for r in summary)
    best = max(summary, key=lambda r: to_float(r['Prize_Pool_USD']))
    leader, leader_n = titles.most_common(1)[0]
    return {
        'scale': scale,
        'activity': activity,
        'parity': {y: pct(d, t) for y, (d, t) in parity.items()},
        'regional': regional_shares(titles),
        'titles_by_year': [(int(r['Year']), LOL_REGIONS.get(r['Winner_Region'], r['Winner_Region']), r['Winner'])
                           for r in summary],
        'details': {
            'premios': [(r['Year'], to_float(r['Prize_Pool_USD'])) for r in summary],
            'duracion': [(r['Year'], minutes(r['Avg_Game_Duration'])) for r in stats],
            'kills': [(r['Year'], to_float(r['Avg_Kills_Per_Game'])) for r in stats],
        },
        'kpis': [
            ('Mundiales disputados', len(summary), ''),
            (f'Títulos de {leader}', leader_n, f'de {len(summary)}'),
            (f'Mayor bolsa ({best["Year"]})', to_float(best['Prize_Pool_USD']), 'USD'),
            ('Partidas por Mundial', round(activity), 'promedio'),
        ],
    }


# ---------------------------------------------------------------------------
# FIFA World Cup
# ---------------------------------------------------------------------------
CONFED_ES = {
    'UEFA': 'Europa', 'CONMEBOL': 'Sudamérica', 'CONCACAF': 'Norte y Centroamérica',
    'CAF': 'África', 'AFC': 'Asia', 'OFC': 'Oceanía',
}
# Campeones que no aparecen en el listado 2026 (nombre histórico o no clasificado)
CONFED_FALLBACK = {'West Germany': 'UEFA', 'Italy': 'UEFA'}


def load_fifa():
    editions = list(read_csv('fifa_dataset', 'wc_all_editions.csv'))
    scale = [(int(r['year']), to_float(r['attendance'])) for r in editions]
    latest = max(editions, key=lambda r: int(r['year']))
    activity = to_float(latest['matches']) / 4  # un Mundial cada 4 años

    parity = defaultdict(lambda: [0, 0])
    for r in read_csv('fifa_dataset', 'wc_all_matches.csv'):
        diff = abs(int(to_float(r['score1'])) - int(to_float(r['score2'])))
        parity[int(r['year'])][0] += diff <= 1
        parity[int(r['year'])][1] += 1

    confed = {r['team']: r['confederation'] for r in read_csv('fifa_dataset', 'wc_2026_teams.csv')}
    confed.update({k: v for k, v in CONFED_FALLBACK.items() if k not in confed})
    def region_of(team):
        return CONFED_ES.get(confed.get(team, ''), 'Otras')

    titles = Counter(region_of(r['champion']) for r in editions)
    host_wins = sum(r['host_won'] == 'Yes' for r in editions)
    return {
        'scale': scale,
        'activity': activity,
        'parity': {y: pct(d, t) for y, (d, t) in parity.items()},
        'regional': regional_shares(titles),
        'titles_by_year': [(int(r['year']), region_of(r['champion']), r['champion']) for r in editions],
        'details': {
            'asistencia': [(r['year'], to_float(r['attendance'])) for r in editions],
            'goles': [(r['year'], to_float(r['goals_per_match'])) for r in editions],
            'equipos': [(r['year'], to_float(r['teams'])) for r in editions],
        },
        'kpis': [
            ('Mundiales disputados', len(editions), ''),
            (f'Asistencia en {latest["year"]}', to_float(latest['attendance']), 'personas'),
            ('Anfitriones campeones', host_wins, f'de {len(editions)}'),
            ('Goles por partido', round(sum(to_float(r['goals_per_match']) for r in editions) / len(editions), 2),
             'promedio histórico'),
        ],
    }


# ---------------------------------------------------------------------------
# Counter-Strike 2 (tier 1)
# ---------------------------------------------------------------------------
NOT_MAIN_EVENT = ('qualifier', 'rmr', 'decider', 'open qualifiers')


def player_country(text):
    m = re.search(r',\s*([A-Z]{2})\s*$', text or '')
    return m.group(1) if m else None


def team_region(countries, continents):
    regions = Counter()
    for code in countries:
        if code in CIS:
            regions['CIS'] += 1
        elif code in continents:
            regions[CONTINENT_ES.get(continents[code], continents[code])] += 1
    return regions.most_common(1)[0][0] if regions else 'Sin dato'


def load_cs2():
    continents = country_continents()
    matches = {}
    finals = {}
    monthly = Counter()
    maps, overtime = Counter(), Counter()
    for r in read_csv('counter', 'cs2_tier1_games.csv'):
        if r['is_total'] == 'False' and r['map_name']:
            maps[r['map_name']] += 1
            overtime[r['map_name']] += max(to_float(r['score1_game']), to_float(r['score2_game'])) > 13
        if r['match_id'] in matches:
            continue
        when = datetime.strptime(r['datetime'][:10], '%Y-%m-%d')
        matches[r['match_id']] = (when, int(to_float(r['score1_match'])), int(to_float(r['score2_match'])),
                                  int(to_float(r['bestOf'], 1)))
        monthly[(when.year, when.month)] += 1
        name = r['tournament']
        if any(k in name.lower() for k in NOT_MAIN_EVENT):
            continue
        if name not in finals or r['datetime'] > finals[name]['datetime']:
            finals[name] = r

    # Escala: series por mes, sólo meses completos del dataset
    months = sorted(monthly)
    full = months[1:-1] if len(months) > 2 else months
    scale = [(y + (m - 1) / 12, monthly[(y, m)]) for y, m in full]
    per_year = Counter(when.year for when, *_ in matches.values())
    full_years = [y for y in per_year if (y, 1) in monthly and (y, 12) in monthly]
    activity = sum(per_year[y] for y in full_years) / len(full_years) if full_years else len(matches)

    parity = defaultdict(lambda: [0, 0])
    for when, s1, s2, best_of in matches.values():
        if best_of >= 3 and max(s1, s2) > 0:
            parity[when.year][0] += is_decider(s1, s2)
            parity[when.year][1] += 1

    titles = Counter()
    titles_by_year = []
    for name, r in finals.items():
        side = 'team1' if r['team1_win'] in ('1', '1.0', 'True') else 'team2'
        codes = [player_country(r[f'{side}_player{i}']) for i in range(1, 6)]
        region = team_region([c for c in codes if c], continents)
        titles[region] += 1
        titles_by_year.append((int(r['datetime'][:4]), region, f"{r[side]} · {name}"))

    top_maps = maps.most_common()
    deciders = sum(d for d, _ in parity.values())
    series = sum(t for _, t in parity.values())
    return {
        'scale': scale,
        'activity': activity,
        'parity': {y: pct(d, t) for y, (d, t) in parity.items()},
        'regional': regional_shares(titles),
        'titles_by_year': sorted(titles_by_year),
        'details': {
            'series_mes': [(f'{y}-{m:02d}', monthly[(y, m)]) for y, m in months],
            'mapas': top_maps,
            'mapas_ot': [(name, pct(overtime[name], n)) for name, n in top_maps],
        },
        'kpis': [
            ('Series tier 1 analizadas', len(matches), f'{months[0][0]}–{months[-1][0]}'),
            ('Torneos con campeón', len(finals), ''),
            (f'Mapa más jugado: {top_maps[0][0]}', pct(top_maps[0][1], sum(maps.values())), '% de los mapas'),
            ('Series al mapa decisivo', pct(deciders, series), '% de las Bo3/Bo5'),
        ],
    }


# ---------------------------------------------------------------------------
# StarCraft II
# ---------------------------------------------------------------------------
SC2_RACES = {'P': 'Protoss', 'T': 'Terran', 'Z': 'Zerg'}
SC2_REGIONS = {'South Korea': 'Corea (KR)', 'Finland': 'Europa', 'Italy': 'Europa'}


def load_sc2():
    per_year = Counter()
    parity = defaultdict(lambda: [0, 0])
    matchup = defaultdict(lambda: [0, 0])  # (expansión, raza A, raza B) -> [victorias de A, partidas]
    races = Counter()
    for r in read_csv('starcraft 2', 'sc2-matches-history.csv'):
        year = int(r['match_date'][-4:])
        per_year[year] += 1
        a, b = r['player_1_race'], r['player_2_race']
        races[a] += 1
        if a in SC2_RACES and b in SC2_RACES and a != b:
            won = r['player_1_match_status'] == '[winner]'
            for key, win in (((r['addon'], a, b), won), ((r['addon'], b, a), not won)):
                matchup[key][0] += win
                matchup[key][1] += 1
        sc = series_score(r['score'])
        if sc and max(sc) >= 2:
            parity[year][0] += is_decider(*sc)
            parity[year][1] += 1

    years = sorted(per_year)
    full = years[1:-1] if len(years) > 2 else years  # primer y último año vienen incompletos
    scale = [(y, per_year[y]) for y in full]
    activity = sum(per_year[y] for y in full) / len(full) if full else 0

    titles_by_year = []
    for r in read_csv('starcraft 2', 'sc2_wcs_global_finals.csv'):
        region = SC2_REGIONS.get(r['winner_country'], 'Otras')
        titles_by_year.append((int(r['year']), region, r['winner']))
    titles = Counter(region for _, region, _ in titles_by_year)

    prizes = 0
    for r in read_csv('starcraft 2', 'highest_earning_players.csv'):
        if r['Game'] == 'Starcraft II':
            prizes += to_float(r['TotalUSDPrize'])
    total_races = sum(races[r] for r in SC2_RACES)
    top_race = max(SC2_RACES, key=lambda r: races[r])
    return {
        'scale': scale,
        'activity': activity,
        'parity': {y: pct(d, t) for y, (d, t) in parity.items()},
        'regional': regional_shares(titles),
        'titles_by_year': titles_by_year,
        'details': {
            'partidas': [(str(y), per_year[y]) for y in years],
            'matchup': [(f'{exp}|{a}v{b}', pct(w, n)) for (exp, a, b), (w, n) in sorted(matchup.items())],
            'razas': [(SC2_RACES[r], pct(races[r], total_races)) for r in SC2_RACES],
        },
        'kpis': [
            ('Partidas registradas', sum(per_year.values()), f'{years[0]}–{years[-1]}'),
            ('Premios del top 100', round(prizes), 'USD'),
            (f'Raza más jugada: {SC2_RACES[top_race]}', pct(races[top_race], total_races), '% de las partidas'),
            ('Año con más partidas', max(per_year.values()), f'en {max(per_year, key=per_year.get)}'),
        ],
    }


# ---------------------------------------------------------------------------
# Ensamblado final
# ---------------------------------------------------------------------------
DISCIPLINES = [
    # slug, nombre, color, cargador
    # Paleta validada para daltonismo (todos los pares, fondo oscuro): ΔE CVD >= 8,8 y normal >= 21,2
    ('fifa-wc', 'FIFA World Cup', '#1fa37a', load_fifa),
    ('lol-worlds', 'LoL Worlds', '#e0563b', load_lol),
    ('cs2-majors', 'CS2 Majors', '#e8c547', load_cs2),
    ('starcraft-2', 'StarCraft II', '#3d84e8', load_sc2),
]


# Qué mide cada métrica y de qué archivo sale (se muestra bajo los gráficos)
NOTES = {
    'fifa-wc': {
        'scale': 'asistencia total por Mundial',
        'parity': 'partidos definidos por 1 gol o empate',
        'regional': 'Copas del Mundo ganadas por confederación',
        'sources': ['wc_all_editions.csv', 'wc_all_matches.csv', 'wc_2026_teams.csv'],
    },
    'lol-worlds': {
        'scale': 'bolsa de premios del Mundial (USD)',
        'parity': 'series eliminatorias que llegaron al juego decisivo',
        'regional': 'Mundiales ganados por región',
        'sources': ['01_Worlds_Event_Tournament_Summary.csv', '03_Worlds_Knockout_Bracket_Results.csv',
                    '09_Worlds_Match_Statistics_golgg.csv'],
    },
    'cs2-majors': {
        'scale': 'series tier 1 jugadas por mes',
        'parity': 'series Bo3/Bo5 que llegaron al mapa decisivo',
        'regional': 'torneos tier 1 ganados, según la nacionalidad de los jugadores',
        'sources': ['cs2_tier1_games.csv', 'country-and-continent-codes-list.csv'],
    },
    'starcraft-2': {
        'scale': 'partidas registradas por año',
        'parity': 'series Bo3+ que llegaron al juego decisivo',
        'regional': 'WCS Global Finals ganadas por región del campeón',
        'sources': ['sc2-matches-history.csv', 'sc2_wcs_global_finals.csv'],
    },
}

AXIS_NOTES = {
    'Crecimiento': 'Tendencia anual de la escala del evento (ajuste log-lineal)',
    'Estabilidad': 'Inverso de la volatilidad alrededor de esa tendencia',
    'Actividad': 'Partidos o series disputados por año (escala log)',
    'Paridad': '% promedio de enfrentamientos que llegaron al juego decisivo',
    'Accesibilidad': '100 − % de títulos de la región dominante',
}


def scale_0_100(values, invert=False, floor=20):
    """Escala relativa entre disciplinas: la peor queda en `floor`, la mejor en 100."""
    lo, hi = min(values), max(values)
    out = []
    for v in values:
        t = (v - lo) / (hi - lo) if hi > lo else 1
        if invert:
            t = 1 - t
        out.append(round(floor + (100 - floor) * t, 1))
    return out


def build_dataset():
    rows = []
    for slug, name, color, loader in DISCIPLINES:
        d = loader()
        growth, volatility = log_trend(d['scale'])
        parity_values = list(d['parity'].values())
        top_share = d['regional'][0]['pct'] if d['regional'] else 100
        rows.append({
            'slug': slug, 'name': name, 'color': color, **d,
            'growth': growth, 'volatility': volatility,
            'parity_avg': sum(parity_values) / len(parity_values) if parity_values else 0,
            'openness': round(100 - top_share, 1),
        })

    raw = {
        'Crecimiento': scale_0_100([r['growth'] for r in rows]),
        'Estabilidad': scale_0_100([r['volatility'] for r in rows], invert=True),
        'Actividad': scale_0_100([math.log10(max(r['activity'], 1)) for r in rows]),
        'Paridad': scale_0_100([r['parity_avg'] for r in rows]),
        'Accesibilidad': scale_0_100([r['openness'] for r in rows]),
    }
    for i, r in enumerate(rows):
        r['radar'] = {axis: raw[axis][i] for axis in RADAR_AXES}
        stab = r['radar']['Estabilidad']
        r['risk_level'] = 'bajo' if stab >= 70 else 'medio' if stab >= 45 else 'alto'
    return rows


def sync_database():
    """Borra y vuelve a cargar los modelos con lo calculado desde los CSV."""
    from django.db import transaction
    from .models import (Discipline, GrowthMetric, RadarScore, RegionalTitle, CompetitiveBalanceRecord,
                         SeriesPoint, SyncLog)

    started = time.monotonic()
    try:
        rows = build_dataset()
    except Exception as exc:
        SyncLog.objects.create(ok=False, duration_s=round(time.monotonic() - started, 2), message=str(exc))
        raise
    with transaction.atomic():
        Discipline.objects.all().delete()  # cascada sobre el resto de los modelos
        for r in rows:
            disc = Discipline.objects.create(name=r['name'], slug=r['slug'], accent_color=r['color'],
                                             risk_level=r['risk_level'], is_preliminary=False)
            GrowthMetric.objects.bulk_create([
                GrowthMetric(discipline=disc, metric_name='crecimiento_anual', pct_change=r['growth']),
                GrowthMetric(discipline=disc, metric_name='volatilidad', pct_change=r['volatility']),
            ])
            RadarScore.objects.bulk_create(
                RadarScore(discipline=disc, axis=axis, normalized_value=v) for axis, v in r['radar'].items())
            RegionalTitle.objects.bulk_create(
                RegionalTitle(discipline=disc, region=t['region'], title_count=t['count'], pct_of_total=t['pct'])
                for t in r['regional'])
            CompetitiveBalanceRecord.objects.bulk_create(
                CompetitiveBalanceRecord(discipline=disc, era_label=str(year), value=v)
                for year, v in sorted(r['parity'].items()))

            points = [SeriesPoint(discipline=disc, series='titulos', label=str(year), value=1, extra=region[:100],
                                  order=i)
                      for i, (year, region, _) in enumerate(r['titles_by_year'])]
            for series, values in r['details'].items():
                points += [SeriesPoint(discipline=disc, series=series, label=str(label)[:100], value=v, order=i)
                           for i, (label, v) in enumerate(values)]
            points += [SeriesPoint(discipline=disc, series='kpi', label=label[:100], value=v, extra=unit, order=i)
                       for i, (label, v, unit) in enumerate(r['kpis'])]
            SeriesPoint.objects.bulk_create(points)

        SyncLog.objects.create(duration_s=round(time.monotonic() - started, 2),
                               records=sum(m.objects.count() for m in (
                                   Discipline, GrowthMetric, RadarScore, RegionalTitle, CompetitiveBalanceRecord,
                                   SeriesPoint)),
                               message=f'{len(csv_files())} archivos CSV leídos')
    return rows


def csv_files():
    """Archivos CSV de cada carpeta de datos con sus filas, tamaño y fecha de modificación."""
    files = []
    for folder in ('counter', 'fifa_dataset', 'lol_dataset', 'starcraft 2'):
        for path in sorted(data_dir().joinpath(folder).glob('*.csv')):
            stat = path.stat()
            with open(path, 'rb') as f:
                rows = max(sum(1 for _ in f) - 1, 0)
            files.append({'folder': folder, 'name': path.name, 'rows': rows, 'size': stat.st_size,
                          'modified': datetime.fromtimestamp(stat.st_mtime)})
    return files
