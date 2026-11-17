from collections import defaultdict
from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Max, Sum
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from .csv_data import RADAR_AXES, csv_files, sync_database
from .manager_data import sync_manager_data
from .models import (CompetitiveBalanceRecord, Discipline, GrowthMetric, Investment, PlayerStat, RadarScore,
                     RegionalTitle, SeriesPoint, SyncLog, TeamStat)

ACTIVE_DAYS = 30
SHAPES = {'fifa-wc': 'circle', 'lol-worlds': 'triangle', 'cs2-majors': 'rect', 'starcraft-2': 'rectRot'}


def money(value):
    return '$' + f'{float(value or 0):,.0f}'.replace(',', '.')


def discipline_mark(disc):
    return format_html('<span class="mark mark-{}" style="color:{}" aria-hidden="true"></span>',
                       SHAPES.get(disc.slug, 'circle'), disc.accent_color)


def risk_chip(level):
    return format_html('<span class="risk risk-{}">{}</span>', level, level)


def active_since():
    return timezone.now() - timedelta(days=ACTIVE_DAYS)


# 1. ADMIN SITE PERSONALIZADO: CENTRO DE CONTROL DE DATOS
class ApexAdminSite(admin.AdminSite):
    site_header = "APEX | Capital & Intelligence"
    site_title = "Admin APEX"
    index_title = "Centro de control"
    index_template = "admin/index.html"

    def get_urls(self):
        return [path('sync/', self.admin_view(self.sync_view), name='apex_sync')] + super().get_urls()

    def sync_view(self, request):
        return require_POST(self._sync)(request)

    def _sync(self, request):
        try:
            rows = sync_database()
            sync_manager_data()
        except Exception as exc:  # el error queda en SyncLog y se muestra al usuario
            messages.error(request, f'No se pudo sincronizar: {exc}')
        else:
            log = SyncLog.objects.first()
            messages.success(request, f'Base sincronizada desde los CSV: {len(rows)} disciplinas y '
                                      f'{log.records:,} registros en {log.duration_s:.1f} s.'.replace(',', '.'))
        return redirect('admin:index')

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        disciplines = list(Discipline.objects.prefetch_related('radar_scores', 'balance_records', 'growth_metrics'))
        last_sync = SyncLog.objects.filter(ok=True).first()

        # --- Datos y CSV ---
        files = csv_files()
        for f in files:
            f['stale'] = bool(last_sync and timezone.make_aware(f['modified']) > last_sync.created_at)
        records = (Discipline.objects.count() + RadarScore.objects.count() + RegionalTitle.objects.count()
                   + CompetitiveBalanceRecord.objects.count() + GrowthMetric.objects.count() + SeriesPoint.objects.count())

        # --- Usuarios e inversiones ---
        since = active_since()
        users = list(User.objects.annotate(n_inv=Count('investments'), capital=Sum('investments__capital'),
                                           last_inv=Max('investments__created_at')).order_by('-last_login'))
        active = [u for u in users if u.last_login and u.last_login >= since]
        investors = [u for u in users if u.n_inv]
        total_capital = sum(float(u.capital or 0) for u in users)
        n_investments = sum(u.n_inv for u in users)

        by_discipline = defaultdict(float)
        last_profile = {}
        for inv in Investment.objects.order_by('created_at'):
            last_profile[inv.user_id] = inv.get_risk_profile_display()
            for slug, share in inv.allocation.items():
                by_discipline[slug] += float(inv.capital) * float(share) / 100

        user_rows = [{
            'user': u,
            'name': u.get_full_name() or u.username,
            'active': u in active,
            'n_inv': u.n_inv,
            'capital': money(u.capital) if u.capital else '—',
            'profile': last_profile.get(u.id, '—'),
            'demo': u.groups.filter(name='Demo').exists(),
        } for u in users[:12]]

        extra_context.update({
            'kpis': [
                {'label': 'Disciplinas', 'value': len(disciplines), 'unit': 'calculadas desde CSV'},
                {'label': 'Registros en la base', 'value': f'{records:,}'.replace(',', '.'), 'unit': 'métricas y series'},
                {'label': 'Archivos CSV', 'value': len(files),
                 'unit': f'{sum(f["stale"] for f in files)} con cambios sin sincronizar'},
                {'label': 'Última sincronización',
                 'value': timezone.localtime(last_sync.created_at).strftime('%d-%m %H:%M') if last_sync else 'Nunca',
                 'unit': f'{last_sync.duration_s:.1f} s' if last_sync else 'usa el botón para cargar la base'},
            ],
            'user_kpis': [
                {'label': f'Usuarios activos ({ACTIVE_DAYS} días)', 'value': len(active), 'unit': f'de {len(users)} registrados'},
                {'label': 'Usuarios que invirtieron', 'value': f'{round(100 * len(investors) / len(users)) if users else 0} %',
                 'unit': f'{len(investors)} de {len(users)}'},
                {'label': 'Capital invertido', 'value': money(total_capital), 'unit': f'en {n_investments} portafolios'},
                {'label': 'Ticket promedio', 'value': money(total_capital / n_investments if n_investments else 0),
                 'unit': 'por portafolio'},
            ],
            'csv_files': files,
            'sync_logs': SyncLog.objects.all()[:5],
            'user_rows': user_rows,
            'disciplines': [{
                'obj': d, 'mark': discipline_mark(d), 'risk': risk_chip(d.risk_level),
                'growth': next((g.pct_change for g in d.growth_metrics.all() if g.metric_name == 'crecimiento_anual'), 0),
                'invested': money(by_discipline.get(d.slug, 0)),
            } for d in disciplines],
            'chart_data': {
                'axes': RADAR_AXES,
                'disciplines': [{
                    'slug': d.slug, 'name': d.name, 'color': d.accent_color, 'shape': SHAPES.get(d.slug, 'circle'),
                    'scores': {s.axis: s.normalized_value for s in d.radar_scores.all()},
                    'parity': sorted(([int(r.era_label), r.value] for r in d.balance_records.all())),
                    'invested': round(by_discipline.get(d.slug, 0)),
                } for d in disciplines],
            },
        })
        return super().index(request, extra_context=extra_context)


# Instancia única de nuestro Admin Personalizado
admin_site = ApexAdminSite(name='apex_admin')


# 2. USUARIOS: ACTIVIDAD E INVERSIONES
class ActivityFilter(admin.SimpleListFilter):
    title = f'actividad ({ACTIVE_DAYS} días)'
    parameter_name = 'activo'

    def lookups(self, request, model_admin):
        return [('si', 'Activos'), ('no', 'Inactivos')]

    def queryset(self, request, queryset):
        if self.value() == 'si':
            return queryset.filter(last_login__gte=active_since())
        if self.value() == 'no':
            return queryset.exclude(last_login__gte=active_since())
        return queryset


class InvestedFilter(admin.SimpleListFilter):
    title = '¿invirtió?'
    parameter_name = 'invirtio'

    def lookups(self, request, model_admin):
        return [('si', 'Sí'), ('no', 'No')]

    def queryset(self, request, queryset):
        if self.value() == 'si':
            return queryset.filter(investments__isnull=False).distinct()
        if self.value() == 'no':
            return queryset.filter(investments__isnull=True)
        return queryset


class InvestmentInline(admin.TabularInline):
    model = Investment
    extra = 0
    fields = ('capital', 'risk_profile', 'expected_return', 'created_at')
    readonly_fields = ('created_at',)


class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'full_name', 'activity', 'invested', 'capital_total', 'last_login', 'is_staff')
    list_filter = (ActivityFilter, InvestedFilter, 'is_staff', 'groups')
    inlines = [InvestmentInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_inv=Count('investments'), capital=Sum('investments__capital'))

    @admin.display(description='Nombre')
    def full_name(self, obj):
        return obj.get_full_name() or '—'

    @admin.display(description=f'Activo ({ACTIVE_DAYS} días)', ordering='last_login')
    def activity(self, obj):
        if obj.last_login and obj.last_login >= active_since():
            return mark_safe('<span class="ok-text">Activo</span>')
        return mark_safe('<span class="off-text">Inactivo</span>')

    @admin.display(description='¿Invirtió?', ordering='n_inv')
    def invested(self, obj):
        if obj.n_inv:
            return format_html('<span class="ok-text">Sí, {} {}</span>', obj.n_inv,
                               'portafolio' if obj.n_inv == 1 else 'portafolios')
        return mark_safe('<span class="off-text">No</span>')

    @admin.display(description='Capital invertido', ordering='capital')
    def capital_total(self, obj):
        return money(obj.capital) if obj.capital else '—'


# 3. MODELOS DE DATOS
class RadarScoreInline(admin.TabularInline):
    model = RadarScore
    extra = 0
    verbose_name_plural = 'puntajes del radar'


class RegionalTitleInline(admin.TabularInline):
    model = RegionalTitle
    extra = 0


class DisciplineAdmin(admin.ModelAdmin):
    list_display = ('identity', 'slug', 'risk_badge', 'growth', 'color_swatch', 'points')
    search_fields = ('name', 'slug')
    list_filter = ('risk_level',)
    inlines = [RadarScoreInline, RegionalTitleInline]
    readonly_fields = ('summary',)
    fieldsets = ((None, {'fields': ('summary', 'name', 'slug', 'accent_color', 'risk_level', 'is_preliminary')}),)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_points=Count('series_points', distinct=True))

    @admin.display(description='Disciplina', ordering='name')
    def identity(self, obj):
        return format_html('{} <b>{}</b>', discipline_mark(obj), obj.name)

    @admin.display(description='Nivel de riesgo', ordering='risk_level')
    def risk_badge(self, obj):
        return risk_chip(obj.risk_level)

    @admin.display(description='Crecimiento anual')
    def growth(self, obj):
        g = obj.growth_metrics.filter(metric_name='crecimiento_anual').first()
        return f'{g.pct_change:+.1f} %'.replace('.', ',') if g else '—'

    @admin.display(description='Color')
    def color_swatch(self, obj):
        return format_html('<span class="swatch" style="background:{}"></span> <code>{}</code>', obj.accent_color, obj.accent_color)

    @admin.display(description='Puntos de detalle', ordering='n_points')
    def points(self, obj):
        return obj.n_points

    @admin.display(description='Resumen')
    def summary(self, obj):
        if not obj.pk:
            return '—'
        scores = format_html_join('', '<span class="chip">{}: <b>{}</b></span> ',
                                  ((s.axis, f'{s.normalized_value:.0f}') for s in obj.radar_scores.all()))
        return format_html('<div class="summary">{} {} {}</div>', discipline_mark(obj), risk_chip(obj.risk_level), scores)


class GrowthMetricAdmin(admin.ModelAdmin):
    list_display = ('discipline', 'metric_name', 'pct_change')
    list_filter = ('discipline', 'metric_name')


class RadarScoreAdmin(admin.ModelAdmin):
    list_display = ('discipline', 'axis', 'score_bar')
    list_filter = ('discipline', 'axis')

    @admin.display(description='Puntaje (20–100)', ordering='normalized_value')
    def score_bar(self, obj):
        return format_html('<span class="bar"><span style="width:{}%;background:{}"></span></span> {}',
                           round(obj.normalized_value), obj.discipline.accent_color, round(obj.normalized_value))


class RegionalTitleAdmin(admin.ModelAdmin):
    list_display = ('discipline', 'region', 'title_count', 'pct_of_total')
    list_filter = ('discipline',)
    search_fields = ('region',)


class CompetitiveBalanceRecordAdmin(admin.ModelAdmin):
    list_display = ('discipline', 'era_label', 'value')
    list_filter = ('discipline',)
    ordering = ('discipline', 'era_label')


class SeriesPointAdmin(admin.ModelAdmin):
    list_display = ('discipline', 'series', 'label', 'value', 'extra')
    list_filter = ('discipline', 'series')
    search_fields = ('label', 'extra')


class SyncLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'status', 'records', 'duration_s', 'message')
    list_filter = ('ok',)

    @admin.display(description='Estado', ordering='ok')
    def status(self, obj):
        return mark_safe('<span class="ok-text">Correcta</span>') if obj.ok else mark_safe('<span class="bad-text">Falló</span>')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'capital_fmt', 'risk_profile', 'return_fmt', 'allocation_chips', 'created_at')
    list_filter = ('risk_profile', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    @admin.display(description='Capital', ordering='capital')
    def capital_fmt(self, obj):
        return money(obj.capital)

    @admin.display(description='Retorno proyectado', ordering='expected_return')
    def return_fmt(self, obj):
        return f'{obj.expected_return:+.1f} %'.replace('.', ',')

    @admin.display(description='Asignación')
    def allocation_chips(self, obj):
        colors = dict(Discipline.objects.values_list('slug', 'accent_color'))
        return format_html_join('', '<span class="chip"><span class="dot" style="background:{}"></span>{} {} %</span> ',
                                ((colors.get(slug, '#6b7385'), slug.split('-')[0].upper(), f'{share:.0f}')
                                 for slug, share in sorted(obj.allocation.items(), key=lambda kv: -kv[1])))


class TeamStatAdmin(admin.ModelAdmin):
    list_display = ('team', 'tournament', 'discipline', 'played', 'won', 'drawn', 'lost')
    list_filter = ('discipline',)
    search_fields = ('team', 'tournament')


class PlayerStatAdmin(admin.ModelAdmin):
    list_display = ('player', 'discipline', 'team', 'country', 'played', 'won')
    list_filter = ('discipline',)
    search_fields = ('player', 'team')


# Registrar modelos en el sitio de administración customizado
admin_site.register(User, CustomUserAdmin)
admin_site.register(Group, GroupAdmin)
admin_site.register(Discipline, DisciplineAdmin)
admin_site.register(Investment, InvestmentAdmin)
admin_site.register(SyncLog, SyncLogAdmin)
admin_site.register(GrowthMetric, GrowthMetricAdmin)
admin_site.register(RadarScore, RadarScoreAdmin)
admin_site.register(RegionalTitle, RegionalTitleAdmin)
admin_site.register(CompetitiveBalanceRecord, CompetitiveBalanceRecordAdmin)
admin_site.register(SeriesPoint, SeriesPointAdmin)
admin_site.register(TeamStat, TeamStatAdmin)
admin_site.register(PlayerStat, PlayerStatAdmin)
