from collections import Counter

from .csv_data import read_csv, to_float
from .models import Discipline, PlayerStat, TeamStat


def add_result(table, key, my_score, other_score):
    if key not in table:
        table[key] = {'played': 0, 'won': 0, 'drawn': 0, 'lost': 0}
    table[key]['played'] += 1
    if my_score > other_score:
        table[key]['won'] += 1
    elif my_score < other_score:
        table[key]['lost'] += 1
    else:
        table[key]['drawn'] += 1


def save_teams(discipline, table):
    rows = []
    for (tournament, team), stats in table.items():
        rows.append(TeamStat(discipline=discipline, tournament=tournament, team=team, **stats))
    TeamStat.objects.bulk_create(rows)


def load_cs2(discipline):
    teams = {}
    players = {}
    for r in read_csv('counter', 'cs2_tier1_games.csv'):
        if r['is_total'] == 'True':
            score1 = to_float(r['score1_match'])
            score2 = to_float(r['score2_match'])
            add_result(teams, (r['tournament'], r['team1']), score1, score2)
            add_result(teams, (r['tournament'], r['team2']), score2, score1)
            continue

        # filas de mapas: aquí vienen las estadísticas de cada jugador
        for side in ['team1', 'team2']:
            won_map = (r['team1_win'] == '1') == (side == 'team1')
            for i in range(1, 6):
                text = r[f'{side}_player{i}']
                if not text:
                    continue
                name = text.split(' (')[0].split(',')[0].strip()
                country = ''
                if ', ' in text:
                    country = text.rsplit(', ', 1)[1].strip()

                if name not in players:
                    # el CSV viene del más nuevo al más antiguo: el primer equipo es el actual
                    players[name] = {'country': country, 'team': r[side], 'played': 0, 'won': 0,
                                     'kills': 0, 'deaths': 0, 'assists': 0, 'adr_sum': 0}
                p = players[name]
                p['played'] += 1
                if won_map:
                    p['won'] += 1
                p['kills'] += int(to_float(r[f'{side}_player{i}_kills']))
                p['deaths'] += int(to_float(r[f'{side}_player{i}_deaths']))
                p['assists'] += int(to_float(r[f'{side}_player{i}_assists']))
                p['adr_sum'] += to_float(r[f'{side}_player{i}_adr'])

    save_teams(discipline, teams)
    rows = []
    for name, p in players.items():
        if p['played'] < 5:
            continue
        rows.append(PlayerStat(discipline=discipline, player=name, country=p['country'], team=p['team'],
                               played=p['played'], won=p['won'], kills=p['kills'], deaths=p['deaths'],
                               assists=p['assists'], adr=round(p['adr_sum'] / p['played'], 1)))
    PlayerStat.objects.bulk_create(rows)


def load_lol(discipline):
    teams = {}
    for r in read_csv('lol_dataset', '02_Worlds_Group_Stage_Standings.csv'):
        key = ('Worlds ' + r['Year'], r['Team'])
        if key not in teams:
            teams[key] = {'played': 0, 'won': 0, 'drawn': 0, 'lost': 0}
        teams[key]['won'] += int(r['Wins'])
        teams[key]['lost'] += int(r['Losses'])
        teams[key]['played'] += int(r['Wins']) + int(r['Losses'])
    save_teams(discipline, teams)


def load_fifa(discipline):
    teams = {}
    for r in read_csv('fifa_dataset', 'wc_all_matches.csv'):
        tournament = 'Mundial ' + r['year']
        add_result(teams, (tournament, r['team1']), int(r['score1']), int(r['score2']))
        add_result(teams, (tournament, r['team2']), int(r['score2']), int(r['score1']))
    save_teams(discipline, teams)

    players = {}
    for r in read_csv('fifa_dataset', 'wc_top_scorers.csv'):
        name = r['player']
        if name not in players:
            players[name] = {'country': r['country'], 'position': r['position'], 'played': 0, 'goals': 0, 'assists': 0}
        players[name]['played'] += int(r['matches_played'])
        players[name]['goals'] += int(r['goals'])
        players[name]['assists'] += int(r['assists'])

    rows = []
    for name, p in players.items():
        rows.append(PlayerStat(discipline=discipline, player=name, country=p['country'], team=p['country'],
                               position=p['position'], played=p['played'], goals=p['goals'], assists=p['assists']))
    PlayerStat.objects.bulk_create(rows)


def load_sc2(discipline):
    players = {}
    for r in read_csv('starcraft 2', 'sc2-matches-history.csv'):
        for n in ['1', '2']:
            name = r['player_' + n]
            if name not in players:
                players[name] = {'played': 0, 'won': 0, 'races': Counter()}
            players[name]['played'] += 1
            if r['player_' + n + '_match_status'] == '[winner]':
                players[name]['won'] += 1
            players[name]['races'][r['player_' + n + '_race']] += 1

    races = {'P': 'Protoss', 'T': 'Terran', 'Z': 'Zerg', 'R': 'Random'}
    rows = []
    for name, p in players.items():
        if p['played'] < 50:
            continue
        race = p['races'].most_common(1)[0][0]
        rows.append(PlayerStat(discipline=discipline, player=name, position=races.get(race, race),
                               played=p['played'], won=p['won']))
    PlayerStat.objects.bulk_create(rows)


def sync_manager_data():
    TeamStat.objects.all().delete()
    PlayerStat.objects.all().delete()
    loaders = {'cs2-majors': load_cs2, 'lol-worlds': load_lol, 'fifa-wc': load_fifa, 'starcraft-2': load_sc2}
    for slug, load in loaders.items():
        discipline = Discipline.objects.filter(slug=slug).first()
        if discipline:
            load(discipline)
    return TeamStat.objects.count(), PlayerStat.objects.count()
