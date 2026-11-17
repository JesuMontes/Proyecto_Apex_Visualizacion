from django.conf import settings
from django.db import models

class Discipline(models.Model):
    class Meta:
        verbose_name = 'disciplina'
        verbose_name_plural = 'disciplinas'

    name = models.CharField('nombre', max_length=100)
    slug = models.SlugField(unique=True)
    accent_color = models.CharField('color', max_length=7)  # Ej: #FF5733
    risk_level = models.CharField('nivel de riesgo', max_length=20)   # bajo / medio / alto
    is_preliminary = models.BooleanField('preliminar', default=False)

    def __str__(self):
        return self.name


class GrowthMetric(models.Model):
    class Meta:
        verbose_name = 'métrica de crecimiento'
        verbose_name_plural = 'métricas de crecimiento'

    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name='growth_metrics')
    metric_name = models.CharField('métrica', max_length=50)  # crecimiento_anual / volatilidad
    pct_change = models.FloatField('valor (%)')

    def __str__(self):
        return f"{self.discipline.name} - {self.metric_name}: {self.pct_change}%"


class RadarScore(models.Model):
    class Meta:
        verbose_name = 'puntaje del radar'
        verbose_name_plural = 'puntajes del radar'

    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name='radar_scores')
    axis = models.CharField('eje', max_length=50)        # Crecimiento, Estabilidad, ...
    normalized_value = models.FloatField('puntaje (20–100)')

    def __str__(self):
        return f"{self.discipline.name} [Radar]: {self.axis}"


class RegionalTitle(models.Model):
    class Meta:
        verbose_name = 'título regional'
        verbose_name_plural = 'títulos regionales'

    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name='regional_titles')
    region = models.CharField('región', max_length=100)
    title_count = models.PositiveIntegerField('títulos o monto')
    pct_of_total = models.FloatField('% del total')

    def __str__(self):
        return f"{self.discipline.name} - {self.region} ({self.title_count})"


class CompetitiveBalanceRecord(models.Model):
    class Meta:
        verbose_name = 'registro de paridad'
        verbose_name_plural = 'registros de paridad'

    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name='balance_records')
    era_label = models.CharField('año', max_length=50)
    value = models.FloatField('índice de paridad (%)')

    def __str__(self):
        return f"{self.discipline.name} [Paridad] - {self.era_label}"


class SeriesPoint(models.Model):
    """Punto genérico de una serie de detalle (fichas por disciplina, títulos por año)."""
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name='series_points')
    series = models.CharField(max_length=50)       # Ej: premios, asistencia, titulos, matchup
    label = models.CharField(max_length=100)       # Ej: año, mapa, enfrentamiento
    value = models.FloatField()
    extra = models.CharField(max_length=100, blank=True)  # Ej: región del campeón
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['discipline', 'series', 'order']
        verbose_name = 'punto de serie'
        verbose_name_plural = 'puntos de series'

    def __str__(self):
        return f"{self.discipline.name} [{self.series}] {self.label}: {self.value}"


class SyncLog(models.Model):
    """Registro de cada carga de la base desde los CSV."""
    created_at = models.DateTimeField(auto_now_add=True)
    duration_s = models.FloatField(default=0)
    records = models.PositiveIntegerField(default=0)
    ok = models.BooleanField(default=True)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'sincronización'
        verbose_name_plural = 'sincronizaciones'

    def __str__(self):
        return f"Sincronización {self.created_at:%Y-%m-%d %H:%M}"


class Investment(models.Model):
    """Portafolio guardado desde el simulador."""
    RISK_CHOICES = [('conservador', 'Conservador'), ('balanceado', 'Balanceado'), ('agresivo', 'Agresivo')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='investments',
                             verbose_name='usuario')
    capital = models.DecimalField(max_digits=14, decimal_places=2)
    risk_profile = models.CharField('perfil de riesgo', max_length=20, choices=RISK_CHOICES)
    allocation = models.JSONField('asignación', default=dict)    # {slug: porcentaje}
    expected_return = models.FloatField('retorno proyectado', default=0)  # % anual
    created_at = models.DateTimeField('fecha', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'inversión'
        verbose_name_plural = 'inversiones'

    def __str__(self):
        return f"{self.user} · ${self.capital:,.0f} ({self.get_risk_profile_display()})"
