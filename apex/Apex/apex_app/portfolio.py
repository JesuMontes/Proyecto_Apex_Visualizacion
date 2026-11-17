"""
Reparto de capital del simulador. Es la misma lógica que `computeAllocation` en static/apex/dashboard.js;
se usa para generar los portafolios de demostración con números coherentes con el dashboard.
"""
import math

CAPITAL_MIN, CAPITAL_MAX = 50_000, 10_000_000

PROFILE_WEIGHTS = {
    'conservador': {'Crecimiento': 0.10, 'Estabilidad': 0.45, 'Actividad': 0.15, 'Paridad': 0.15, 'Accesibilidad': 0.15},
    'balanceado': {'Crecimiento': 0.20, 'Estabilidad': 0.20, 'Actividad': 0.20, 'Paridad': 0.20, 'Accesibilidad': 0.20},
    'agresivo': {'Crecimiento': 0.45, 'Estabilidad': 0.05, 'Actividad': 0.20, 'Paridad': 0.15, 'Accesibilidad': 0.15},
}
RISK_FIT = {
    'conservador': {'bajo': 1.0, 'medio': 0.7, 'alto': 0.4},
    'balanceado': {'bajo': 1.0, 'medio': 1.0, 'alto': 1.0},
    'agresivo': {'bajo': 0.8, 'medio': 1.0, 'alto': 1.2},
}


def allocate(profiles, capital, risk):
    """profiles: [{'slug', 'scores', 'risk_level', 'growth'}] -> ({slug: %}, retorno anual proyectado %)."""
    t = math.log(capital / CAPITAL_MIN) / math.log(CAPITAL_MAX / CAPITAL_MIN)
    concentration = 1 + 3 * (1 - t)
    raw = {}
    for p in profiles:
        score = sum(w * p['scores'].get(axis, 0) / 100 for axis, w in PROFILE_WEIGHTS[risk].items())
        raw[p['slug']] = (score * RISK_FIT[risk][p['risk_level']]) ** concentration
    total = sum(raw.values())
    shares = {slug: v / total for slug, v in raw.items()}
    expected = sum(shares[p['slug']] * max(-25, min(25, p['growth'])) for p in profiles)
    return {slug: round(s * 100, 1) for slug, s in shares.items()}, round(expected, 2)
