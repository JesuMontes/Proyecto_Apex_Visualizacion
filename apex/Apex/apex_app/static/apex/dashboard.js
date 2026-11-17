/* APEX · vista de usuario
 * Un solo estado global (disciplinas visibles, rango de años, resaltado) y un render por pestaña
 * que se vuelve a ejecutar cuando ese estado cambia. Los colores siguen a la disciplina, nunca al orden. */

const SHAPES = { 'fifa-wc': 'circle', 'lol-worlds': 'triangle', 'cs2-majors': 'rect', 'starcraft-2': 'rectRot' };
const C = { text: '#e8eaf0', text2: '#9aa3b5', text3: '#6b7385', grid: '#252935', line: '#2c303c', surface: '#1b1e26' };
const SHORT = { 'fifa-wc': 'FIFA', 'lol-worlds': 'LoL', 'cs2-majors': 'CS2', 'starcraft-2': 'SC2' };

// Peso de cada eje del radar según la tolerancia al riesgo
const PROFILE_WEIGHTS = {
    conservador: { Crecimiento: 0.10, Estabilidad: 0.45, Actividad: 0.15, Paridad: 0.15, Accesibilidad: 0.15 },
    balanceado:  { Crecimiento: 0.20, Estabilidad: 0.20, Actividad: 0.20, Paridad: 0.20, Accesibilidad: 0.20 },
    agresivo:    { Crecimiento: 0.45, Estabilidad: 0.05, Actividad: 0.20, Paridad: 0.15, Accesibilidad: 0.15 },
};
// Ajuste según el nivel de riesgo histórico de cada disciplina
const RISK_FIT = {
    conservador: { bajo: 1.0, medio: 0.7, alto: 0.4 },
    balanceado:  { bajo: 1.0, medio: 1.0, alto: 1.0 },
    agresivo:    { bajo: 0.8, medio: 1.0, alto: 1.2 },
};

const state = {
    data: null, enabled: new Set(), from: 0, to: 0, highlight: null, tab: 'panorama',
    regional: 'lol-worlds', detail: 'lol-worlds', cmpA: 'lol-worlds', cmpB: 'fifa-wc',
    risk: 'balanceado', expansion: 'LotV', details: {},
};
const charts = {};

// ---------------------------------------------------------------- utilidades
const $ = sel => document.querySelector(sel);
const nf = (v, d = 0) => Number(v).toLocaleString('es-CL', { minimumFractionDigits: d, maximumFractionDigits: d });
const compact = v => Number(v).toLocaleString('es-CL', { notation: 'compact', maximumFractionDigits: 1 });
const money = v => '$' + nf(Math.round(v));
const moneyCompact = v => '$' + compact(v);
const signed = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + nf(Math.abs(v), d);
const alpha = (hex, a) => hex.slice(0, 7) + Math.round(a * 255).toString(16).padStart(2, '0');
const disc = slug => state.data.disciplines.find(d => d.slug === slug);
const enabledList = () => state.data.disciplines.filter(d => state.enabled.has(d.slug));
const inRange = y => y >= state.from && y <= state.to;
const rangeText = () => state.from === state.to ? `${state.from}` : `${state.from}–${state.to}`;
const markHTML = slug => `<span class="mark mark-${SHAPES[slug]}" style="color:${disc(slug).color}" aria-hidden="true"></span>`;
const esc = s => String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function tableHTML(headers, rows, numeric = []) {
    const th = headers.map((h, i) => `<th class="${numeric.includes(i) ? 'num' : ''}">${esc(h)}</th>`).join('');
    const tr = rows.map(r => '<tr>' + r.map((c, i) => `<td class="${numeric.includes(i) ? 'num' : ''}">${esc(c)}</td>`).join('') + '</tr>').join('');
    return `<table class="data-table"><thead><tr>${th}</tr></thead><tbody>${tr || `<tr><td colspan="${headers.length}">Sin datos en el rango elegido.</td></tr>`}</tbody></table>`;
}
function setTable(card, headers, rows, numeric) {
    const el = document.querySelector(`[data-card="${card}"] .table-view`);
    if (el) el.innerHTML = tableHTML(headers, rows, numeric);
}

function makeChart(key, canvasId, config) {
    if (charts[key]) charts[key].destroy();
    charts[key] = new Chart(document.getElementById(canvasId), config);
    applyHighlight();
    return charts[key];
}

// Atenúa todas las series menos la resaltada, en todos los gráficos a la vez
function applyHighlight() {
    const h = state.highlight;
    Object.values(charts).forEach(chart => {
        let touched = false;
        chart.data.datasets.forEach(ds => {
            if (ds.slugs) {  // dona: un color por segmento
                ds.backgroundColor = ds.slugs.map((s, i) => (!h || s === h) ? ds.baseColors[i] : alpha(ds.baseColors[i], 0.18));
                touched = true;
            } else if (ds.slug && ds.baseColor) {
                const on = !h || ds.slug === h;
                ds.borderColor = on ? ds.baseColor : alpha(ds.baseColor, 0.18);
                ds.pointBackgroundColor = ds.borderColor;
                ds.backgroundColor = ds.fillAlpha != null ? alpha(ds.baseColor, on ? ds.fillAlpha : 0.03) : ds.borderColor;
                ds.borderWidth = on && h ? 3 : 2;
                touched = true;
            }
        });
        if (touched) chart.update('none');
    });
    document.querySelectorAll('.team').forEach(t => t.classList.toggle('dim', !!h && t.dataset.slug !== h));
}
function setHighlight(slug) {
    if (state.highlight === slug) return;
    state.highlight = slug;
    applyHighlight();
}

function seriesStyle(d, extra = {}) {
    return {
        slug: d.slug, label: d.name, baseColor: d.color, borderColor: d.color, backgroundColor: d.color,
        pointStyle: SHAPES[d.slug], pointRadius: 4, pointHoverRadius: 7, borderWidth: 2,
        pointBorderColor: C.surface, pointBorderWidth: 1, ...extra,
    };
}

// ---------------------------------------------------------------- plugins de Chart.js
// Etiqueta directa al final de cada línea (texto en tinta de texto; la forma y el color van en la línea)
const endLabels = {
    id: 'endLabels',
    afterDatasetsDraw(chart, _args, opts) {
        if (!opts || !opts.enabled) return;
        const { ctx, chartArea } = chart;
        const items = [];
        chart.data.datasets.forEach((ds, i) => {
            const meta = chart.getDatasetMeta(i);
            if (meta.hidden || !meta.data.length) return;
            const last = meta.data[meta.data.length - 1];
            items.push({ x: last.x, y: last.y, text: SHORT[ds.slug] || ds.label, dim: state.highlight && ds.slug !== state.highlight });
        });
        items.sort((a, b) => a.y - b.y);
        for (let i = 1; i < items.length; i++) if (items[i].y - items[i - 1].y < 14) items[i].y = items[i - 1].y + 14;
        ctx.save();
        ctx.font = "600 12px Archivo, 'Segoe UI', sans-serif";
        ctx.textBaseline = 'middle';
        items.forEach(it => {
            ctx.fillStyle = it.dim ? C.text3 : C.text;
            ctx.fillText(it.text, Math.min(it.x + 9, chartArea.right + 6), it.y);
        });
        ctx.restore();
    },
};

const centerText = {
    id: 'centerText',
    afterDraw(chart, _args, opts) {
        if (!opts || !opts.enabled) return;
        const { ctx, chartArea: a } = chart;
        const total = chart.data.datasets[0].data.reduce((x, y) => x + y, 0);
        const cx = (a.left + a.right) / 2, cy = (a.top + a.bottom) / 2;
        ctx.save();
        ctx.textAlign = 'center';
        ctx.fillStyle = C.text2;
        ctx.font = "500 12px Archivo, 'Segoe UI', sans-serif";
        ctx.fillText('Capital total', cx, cy - 14);
        ctx.fillStyle = C.text;
        ctx.font = "750 24px Archivo, 'Segoe UI', sans-serif";
        ctx.fillText(moneyCompact(total), cx, cy + 12);
        ctx.restore();
    },
};

function setupChartDefaults() {
    Chart.register(endLabels, centerText);
    Chart.defaults.color = C.text2;
    Chart.defaults.font.family = "Archivo, 'Segoe UI', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.borderColor = C.grid;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.animation = reduceMotion ? false : { duration: 350 };
    const tt = Chart.defaults.plugins.tooltip;
    Object.assign(tt, { backgroundColor: '#0e1015', borderColor: C.line, borderWidth: 1, padding: 10, titleColor: C.text,
                        bodyColor: C.text, titleFont: { weight: '650' }, usePointStyle: true, boxPadding: 4 });
    Object.assign(Chart.defaults.plugins.legend.labels, { usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 16, color: C.text });
}

// Leyenda: pasar el mouse resalta, hacer clic oculta/muestra la disciplina en todo el dashboard
const legendBehavior = {
    position: 'bottom',
    onHover: (_e, item, legend) => setHighlight(legend.chart.data.datasets[item.datasetIndex].slug),
    onLeave: () => setHighlight(null),
    onClick: (_e, item, legend) => toggleDiscipline(legend.chart.data.datasets[item.datasetIndex].slug),
};
function hoverHighlight(canvasId) {
    const canvas = document.getElementById(canvasId);
    canvas.onmouseleave = () => setHighlight(null);
    return (_e, els, chart) => setHighlight(els.length ? chart.data.datasets[els[0].datasetIndex].slug : null);
}

// ---------------------------------------------------------------- marcador y filtros
function renderTeams() {
    $('#teams').innerHTML = state.data.disciplines.map(d => `
        <button class="team" data-slug="${d.slug}" style="--team:${d.color}" aria-pressed="${state.enabled.has(d.slug)}"
                title="Mostrar u ocultar ${esc(d.name)} en todo el dashboard">
            <span class="mark mark-${SHAPES[d.slug]}" aria-hidden="true"></span>
            <span class="team-name">${esc(d.name)}</span>
            <span class="team-meta">riesgo <span class="risk risk-${d.risk_level}">${d.risk_level}</span></span>
            <span class="team-score">${signed(d.growth)}%<small>por año</small></span>
        </button>`).join('');
    document.querySelectorAll('.team').forEach(btn => {
        btn.addEventListener('click', () => toggleDiscipline(btn.dataset.slug));
        btn.addEventListener('mouseenter', () => setHighlight(btn.dataset.slug));
        btn.addEventListener('mouseleave', () => setHighlight(null));
        btn.addEventListener('focus', () => setHighlight(btn.dataset.slug));
        btn.addEventListener('blur', () => setHighlight(null));
    });
}

function toggleDiscipline(slug) {
    if (state.enabled.has(slug)) {
        if (state.enabled.size === 1) return;  // siempre queda al menos una
        state.enabled.delete(slug);
    } else {
        state.enabled.add(slug);
    }
    document.querySelectorAll('.team').forEach(t => t.setAttribute('aria-pressed', state.enabled.has(t.dataset.slug)));
    state.highlight = null;
    renderActive();
}

function setupYearFilter() {
    const { min, max, default_from } = state.data.years;
    const from = $('#year-from'), to = $('#year-to');
    [from, to].forEach(el => { el.min = min; el.max = max; el.step = 1; });
    from.value = state.from = Math.max(min, default_from);
    to.value = state.to = max;
    const sync = (changed) => {
        let a = Number(from.value), b = Number(to.value);
        if (a > b) { if (changed === from) b = a; else a = b; from.value = a; to.value = b; }
        state.from = a; state.to = b;
        $('#year-label').textContent = rangeText();
        const pct = v => (v - min) / (max - min) * 100;
        $('#year-fill').style.left = pct(a) + '%';
        $('#year-fill').style.right = (100 - pct(b)) + '%';
    };
    let pending;
    [from, to].forEach(el => el.addEventListener('input', () => {
        sync(el);
        cancelAnimationFrame(pending);
        pending = requestAnimationFrame(renderActive);
    }));
    sync(from);
}

function disciplinePicker(containerId, current, onPick, { onlyEnabled = true } = {}) {
    const box = document.getElementById(containerId);
    box.innerHTML = state.data.disciplines.map(d => {
        const off = onlyEnabled && !state.enabled.has(d.slug);
        return `<button data-slug="${d.slug}" class="${d.slug === current ? 'active' : ''}" ${off ? 'disabled' : ''}
                 aria-pressed="${d.slug === current}">${markHTML(d.slug)}${SHORT[d.slug]}</button>`;
    }).join('');
    box.querySelectorAll('button').forEach(b => b.addEventListener('click', () => onPick(b.dataset.slug)));
}
function firstEnabled(current) {
    return state.enabled.has(current) ? current : enabledList()[0].slug;
}

// ---------------------------------------------------------------- pestaña Panorama
function renderPanorama() {
    const { radar } = state.data;
    const visible = radar.datasets.filter(ds => state.enabled.has(ds.slug));
    const byAxis = axis => visible.map(ds => ({ ds, v: ds.data[radar.categories.indexOf(axis)] })).sort((a, b) => b.v - a.v)[0];
    const g = byAxis('Crecimiento'), s = byAxis('Estabilidad');
    $('#panorama-title').textContent = g.ds.slug === s.ds.slug
        ? `${g.ds.label} lidera en crecimiento y estabilidad`
        : `${g.ds.label} es la que más crece; ${s.ds.label}, la más estable`;

    makeChart('radar', 'radarChart', {
        type: 'radar',
        data: { labels: radar.categories, datasets: visible.map(ds => seriesStyle(disc(ds.slug), { data: ds.data, fillAlpha: 0.12, fill: true })) },
        options: {
            scales: { r: { min: 0, max: 100, grid: { color: C.grid }, angleLines: { color: C.grid },
                           ticks: { display: false, stepSize: 20 },
                           pointLabels: { color: C.text, font: { size: 13, weight: '600' } } } },
            plugins: { legend: legendBehavior,
                       tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${nf(c.parsed.r, 0)} / 100` } } },
            onHover: hoverHighlight('radarChart'),
        },
    });
    setTable('radar', ['Disciplina', ...radar.categories],
        visible.map(ds => [ds.label, ...ds.data.map(v => nf(v, 0))]), [1, 2, 3, 4, 5]);

    $('#axis-list').innerHTML = radar.categories
        .map(a => `<div><dt>${a}</dt><dd>${esc(radar.notes[a])}</dd></div>`).join('');

    state.regional = firstEnabled(state.regional);
    disciplinePicker('regional-picker', state.regional, slug => { state.regional = slug; renderPanorama(); });
    renderRegional();
}

function renderRegional() {
    const reg = state.data.regional[state.regional];
    const d = disc(state.regional);

    // Títulos por región dentro del rango de años elegido
    const counter = {};
    reg.by_year.filter(t => inRange(t.year)).forEach(t => { counter[t.region] = (counter[t.region] || 0) + 1; });
    const entries = Object.entries(counter).sort((a, b) => b[1] - a[1]);
    const labels = entries.map(e => e[0]);
    const counts = entries.map(e => e[1]);
    const total = counts.reduce((a, b) => a + b, 0);
    const pcts = counts.map(n => Math.round(n / total * 1000) / 10);

    // El eje llega al máximo de toda la historia, así las barras crecen al ampliar el rango
    const allTimes = {};
    reg.by_year.forEach(t => { allTimes[t.region] = (allTimes[t.region] || 0) + 1; });
    const maxTitles = Math.max(1, ...Object.values(allTimes));

    const unit = { 'lol-worlds': 'Mundiales', 'fifa-wc': 'Copas del Mundo', 'cs2-majors': 'torneos tier 1',
                   'starcraft-2': 'WCS Global Finals' }[state.regional];
    if (!labels.length) {
        $('#regional-title').textContent = `${d.name} no tiene títulos entre ${rangeText()}`;
    } else {
        $('#regional-title').textContent = `${labels[0]} ganó ${counts[0]} de ${total} ${unit} de ${SHORT[d.slug]} (${rangeText()})`;
    }
    $('#regional-note').textContent = reg.note;
    $('#regional-source').innerHTML = 'Fuente: ' + reg.sources.map(s => `<code>${esc(s)}</code>`).join(' ');

    makeChart('regional', 'regionalChart', {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Títulos', data: counts, backgroundColor: d.color, borderRadius: 4,
                                     borderSkipped: 'start', maxBarThickness: 26 }] },
        options: {
            indexAxis: 'y',
            plugins: { legend: { display: false },
                       tooltip: { callbacks: { label: c => {
                           const n = c.parsed.x;
                           return ` ${n} ${n === 1 ? 'título' : 'títulos'} (${nf(pcts[c.dataIndex], 1)} % del rango)`;
                       } } } },
            scales: { x: { min: 0, max: maxTitles, grid: { color: C.grid }, ticks: { precision: 0 },
                           title: { display: true, text: 'Títulos ganados', color: C.text2 } },
                      y: { grid: { display: false }, ticks: { color: C.text, font: { size: 13 } } } },
        },
    });
    setTable('regional', ['Región', 'Títulos', '% del total'],
        labels.map((l, i) => [l, counts[i], nf(pcts[i], 1) + ' %']), [1, 2]);
}

// ---------------------------------------------------------------- pestaña Paridad
function parityInRange(slug) {
    const ds = state.data.balance.datasets.find(d => d.slug === slug);
    return ds.data.filter(p => inRange(p.x));
}

function renderParity() {
    const visible = enabledList();
    const avgs = visible.map(d => {
        const pts = parityInRange(d.slug);
        return { d, n: pts.length, avg: pts.length ? pts.reduce((s, p) => s + p.y, 0) / pts.length : null };
    });
    const withData = avgs.filter(a => a.avg != null).sort((a, b) => b.avg - a.avg);
    $('#parity-title').textContent = withData.length
        ? `${withData[0].d.name} es la más pareja: ${nf(withData[0].avg, 0)} % de sus duelos se definen al límite`
        : `Ninguna disciplina visible tiene datos entre ${rangeText()}`;

    $('#parity-stats').innerHTML = avgs.map(a => `
        <div class="stat">
            <div class="stat-label">${markHTML(a.d.slug)}${esc(a.d.name)}</div>
            <div class="stat-value">${a.avg == null ? '—' : nf(a.avg, 1) + ' %'}</div>
            <div class="stat-unit">${a.avg == null ? 'sin datos en ' + rangeText() : `promedio de ${a.n} ${a.n === 1 ? 'año' : 'años'} (${rangeText()})`}</div>
        </div>`).join('');

    makeChart('parity', 'lineChart', {
        type: 'line',
        data: { datasets: visible.map(d => seriesStyle(d, { data: parityInRange(d.slug), cubicInterpolationMode: 'monotone' })) },
        options: {
            layout: { padding: { right: 36, top: 10 } },
            datasets: { line: { clip: false } },
            interaction: { mode: 'nearest', intersect: false },
            scales: {
                x: { type: 'linear', min: state.from, max: state.to, grid: { color: C.grid },
                     ticks: { stepSize: 1, autoSkip: true, maxTicksLimit: 14, callback: v => String(v) } },
                y: { min: 0, max: 100, grid: { color: C.grid }, ticks: { callback: v => v + ' %', stepSize: 25 },
                     title: { display: true, text: 'Índice de paridad', color: C.text2 } },
            },
            plugins: {
                legend: legendBehavior, endLabels: { enabled: true },
                tooltip: { callbacks: { title: items => String(items[0].parsed.x),
                                        label: c => ` ${c.dataset.label}: ${nf(c.parsed.y, 1)} %` } },
            },
            onHover: hoverHighlight('lineChart'),
        },
    });

    const years = [...new Set(visible.flatMap(d => parityInRange(d.slug).map(p => p.x)))].sort((a, b) => a - b);
    setTable('parity', ['Año', ...visible.map(d => d.name)],
        years.map(y => [y, ...visible.map(d => { const p = parityInRange(d.slug).find(q => q.x === y); return p ? nf(p.y, 1) + ' %' : '—'; })]),
        visible.map((_, i) => i + 1));

    $('#parity-defs').innerHTML = state.data.balance.datasets.filter(ds => state.enabled.has(ds.slug))
        .map(ds => `<li>${markHTML(ds.slug)}<span><b>${esc(ds.label)}</b>: ${esc(ds.note)}</span></li>`).join('');
}

// ---------------------------------------------------------------- pestaña Disciplinas
const yearOf = label => Number(String(label).slice(0, 4));
const byYear = pts => pts.filter(p => inRange(yearOf(p.label)));

const DETAIL = {
    'lol-worlds': {
        scale: { series: 'premios', title: 'Bolsa de premios por Mundial', unit: 'USD', fmt: moneyCompact },
        a: { series: 'duracion', title: 'Duración media de partida', sub: 'Minutos por partida en cada Mundial', fmt: v => nf(v, 1) + ' min', type: 'line', yearly: true },
        b: { series: 'kills', title: 'Kills por partida', sub: 'Promedio de asesinatos por partida', fmt: v => nf(v, 0), type: 'line', yearly: true },
        title: s => { const p = s.premios; return `La bolsa de LoL pasó de ${moneyCompact(p[0].value)} en ${p[0].label} a ${moneyCompact(p[p.length - 1].value)} en ${p[p.length - 1].label}`; },
    },
    'fifa-wc': {
        scale: { series: 'asistencia', title: 'Asistencia total por Mundial', unit: 'personas', fmt: compact },
        a: { series: 'goles', title: 'Goles por partido', sub: 'Promedio de cada edición', fmt: v => nf(v, 2), type: 'line', yearly: true },
        b: { series: 'equipos', title: 'Selecciones participantes', sub: 'Equipos en la fase final', fmt: v => nf(v, 0), type: 'step', yearly: true },
        title: s => { const p = s.asistencia; return `El Mundial pasó de ${compact(p[0].value)} a ${compact(p[p.length - 1].value)} asistentes entre ${p[0].label} y ${p[p.length - 1].label}`; },
    },
    'cs2-majors': {
        scale: { series: 'series_mes', title: 'Series tier 1 por mes', unit: 'series', fmt: v => nf(v, 0) },
        a: { series: 'mapas', title: 'Mapas más jugados', sub: 'Mapas disputados en series tier 1', fmt: v => nf(v, 0) + ' mapas', type: 'hbar' },
        b: { series: 'mapas_ot', title: 'Mapas que llegaron a tiempo extra', sub: '% de los mapas con más de 13 rondas para el ganador', fmt: v => nf(v, 1) + ' %', type: 'hbar', max: null },
        title: s => `${s.mapas[0].label} es el mapa más jugado del circuito tier 1 de CS2`,
    },
    'starcraft-2': {
        scale: { series: 'partidas', title: 'Partidas registradas por año', unit: 'partidas', fmt: compact },
        a: { series: 'matchup', title: 'Enfrentamientos por raza', sub: '% de victorias de la raza de la fila contra la de la columna', type: 'heatmap' },
        b: { series: 'razas', title: 'Popularidad de cada raza', sub: '% de las partidas jugadas con cada raza', fmt: v => nf(v, 1) + ' %', type: 'hbar' },
        title: s => { const top = [...s.razas].sort((a, b) => b.value - a.value)[0]; return `${top.label} es la raza más jugada de StarCraft II, con el ${nf(top.value, 0)} % de las partidas`; },
    },
};

async function loadDetail(slug) {
    if (!state.details[slug]) {
        const res = await fetch(`/api/discipline/${slug}/`);
        if (!res.ok) throw new Error(`No se pudo cargar la ficha (${res.status})`);
        state.details[slug] = await res.json();
    }
    return state.details[slug];
}

function kpiHTML(k) {
    let value, unit = k.unit;
    if (unit === 'USD') { value = moneyCompact(k.value); unit = 'dólares'; }
    else if (unit === 'personas') value = compact(k.value);
    else if (unit.startsWith('%')) { value = nf(k.value, 1) + ' %'; unit = unit.slice(1).trim(); }
    else value = nf(k.value, Number.isInteger(k.value) ? 0 : 1);
    return `<div class="stat"><div class="stat-label">${esc(k.label)}</div><div class="stat-value">${value}</div><div class="stat-unit">${esc(unit) || '&nbsp;'}</div></div>`;
}

async function renderDetail() {
    state.detail = firstEnabled(state.detail);
    disciplinePicker('detail-picker', state.detail, slug => { state.detail = slug; renderDetail(); });
    const slug = state.detail, d = disc(slug), cfg = DETAIL[slug];
    let det;
    try { det = await loadDetail(slug); } catch (err) { $('#detail-title').textContent = err.message; return; }
    if (slug !== state.detail) return;  // el usuario cambió de ficha mientras cargaba

    const s = det.series;
    $('#detail-title').textContent = cfg.title(s);
    $('#detail-lede').innerHTML = `${markHTML(slug)} ${esc(d.name)} tiene riesgo <span class="risk risk-${d.risk_level}">${d.risk_level}</span> y una tendencia de ${signed(d.growth)} % por año en su ${esc(det.scale_note)}.`;
    $('#detail-kpis').innerHTML = det.kpis.map(kpiHTML).join('');
    $('#detail-source').innerHTML = 'Fuente: ' + det.sources.map(f => `<code>${esc(f)}</code>`).join(' ');

    // Escala en el tiempo (filtrada por años)
    const scalePts = byYear(s[cfg.scale.series]);
    $('#scale-title').textContent = cfg.scale.title;
    $('#scale-sub').textContent = `${scalePts.length} ${slug === 'cs2-majors' ? 'meses con datos' : 'registros'} en ${rangeText()}`;
    makeChart('scale', 'scaleChart', {
        type: 'bar',
        data: { labels: scalePts.map(p => p.label),
                datasets: [{ label: cfg.scale.title, data: scalePts.map(p => p.value), backgroundColor: d.color,
                             borderRadius: 4, borderSkipped: 'start', maxBarThickness: 34 }] },
        options: {
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${cfg.scale.fmt(c.parsed.y)} ${cfg.scale.unit}` } } },
            scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true } },
                      y: { grid: { color: C.grid }, ticks: { callback: v => cfg.scale.fmt(v) } } },
        },
    });
    setTable('scale', ['Periodo', cfg.scale.title], scalePts.map(p => [p.label, cfg.scale.fmt(p.value)]), [1]);

    renderDetailPanel('detailA', cfg.a, s, d);
    renderDetailPanel('detailB', cfg.b, s, d);
}

function renderDetailPanel(key, cfg, s, d) {
    $(`#${key}-title`).textContent = cfg.title;
    $(`#${key}-sub`).textContent = cfg.sub + (cfg.yearly ? ` (${rangeText()})` : '');
    const box = document.querySelector(`[data-card="${key}"] .chart-box`);
    const heat = $('#heatmap'), picker = $('#expansion-picker');
    if (key === 'detailA') { heat.hidden = cfg.type !== 'heatmap'; picker.hidden = cfg.type !== 'heatmap'; }
    box.hidden = cfg.type === 'heatmap';
    if (cfg.type === 'heatmap') { if (charts[key]) { charts[key].destroy(); delete charts[key]; } renderHeatmap(s.matchup); return; }

    const pts = cfg.yearly ? byYear(s[cfg.series]) : s[cfg.series];
    const canvasId = key + 'Chart';
    const isBar = cfg.type === 'hbar';
    makeChart(key, canvasId, {
        type: isBar ? 'bar' : 'line',
        data: { labels: pts.map(p => p.label), datasets: [isBar
            ? { label: cfg.title, data: pts.map(p => p.value), backgroundColor: d.color, borderRadius: 4, borderSkipped: 'start', maxBarThickness: 22 }
            // eje de años numérico: los huecos entre años (2018 → 2023) se ven como huecos
            : { label: cfg.title, data: pts.map(p => ({ x: yearOf(p.label), y: p.value })), borderColor: d.color, backgroundColor: d.color,
                borderWidth: 2, pointStyle: SHAPES[d.slug], pointRadius: 4, pointHoverRadius: 7,
                stepped: cfg.type === 'step' ? 'after' : false, cubicInterpolationMode: 'monotone' }] },
        options: {
            indexAxis: isBar ? 'y' : 'x',
            plugins: { legend: { display: false },
                       tooltip: { callbacks: { title: items => isBar ? items[0].label : String(items[0].parsed.x),
                                               label: c => ' ' + cfg.fmt(isBar ? c.parsed.x : c.parsed.y) } } },
            scales: isBar
                ? { x: { grid: { color: C.grid }, beginAtZero: true }, y: { grid: { display: false }, ticks: { color: C.text } } }
                : { x: { type: 'linear', grid: { display: false }, ticks: { maxTicksLimit: 10, callback: v => Number.isInteger(v) ? String(v) : '' } },
                    y: { grid: { color: C.grid }, grace: '10%' } },
        },
    });
    setTable(key, [cfg.yearly ? 'Año' : 'Categoría', cfg.title], pts.map(p => [p.label, cfg.fmt(p.value)]), [1]);
}

// Mapa de calor divergente: rojo (pierde) ↔ gris (50 %) ↔ azul (gana)
function heatColor(v) {
    const t = Math.max(-1, Math.min(1, (v - 50) / 8));
    const mix = (a, b, k) => a.map((x, i) => Math.round(x + (b[i] - x) * k));
    const gray = [56, 56, 53], pos = [57, 135, 229], neg = [208, 59, 59];
    const [r, g, b] = mix(gray, t >= 0 ? pos : neg, Math.abs(t));
    return `rgb(${r},${g},${b})`;
}

function renderHeatmap(points) {
    const races = { P: 'Protoss', T: 'Terran', Z: 'Zerg' };
    const expansions = [...new Set(points.map(p => p.label.split('|')[0]))];
    const order = ['WoL', 'HotS', 'LotV'].filter(e => expansions.includes(e));
    const names = { WoL: 'Wings of Liberty', HotS: 'Heart of the Swarm', LotV: 'Legacy of the Void' };
    if (!order.includes(state.expansion)) state.expansion = order[order.length - 1];
    const picker = $('#expansion-picker');
    picker.innerHTML = order.map(e => `<button data-exp="${e}" class="${e === state.expansion ? 'active' : ''}" title="${names[e]}">${e}</button>`).join('');
    picker.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { state.expansion = b.dataset.exp; renderHeatmap(points); }));

    const val = {};
    points.forEach(p => { const [exp, m] = p.label.split('|'); if (exp === state.expansion) val[m] = p.value; });
    let html = '<div></div>' + Object.values(races).map(r => `<div class="hm-head">vs ${r}</div>`).join('');
    const rows = [];
    Object.entries(races).forEach(([a, an]) => {
        html += `<div class="hm-row">${an}</div>`;
        Object.keys(races).forEach(b => {
            if (a === b) { html += '<div class="hm-cell hm-mirror">espejo</div>'; return; }
            const v = val[`${a}v${b}`];
            rows.push([`${an} vs ${races[b]}`, nf(v, 1) + ' %']);
            html += `<div class="hm-cell" style="background:${heatColor(v)}" title="${an} vs ${races[b]}: ${nf(v, 1)} % de victorias">${nf(v, 1)} %<small>${v >= 50 ? 'gana' : 'pierde'}</small></div>`;
        });
    });
    html += `<div class="hm-legend"><span>Pierde más</span><span class="hm-scale" aria-hidden="true"></span><span>Gana más</span><span>Expansión: ${names[state.expansion]}</span></div>`;
    $('#heatmap').innerHTML = html;
    setTable('detailA', ['Enfrentamiento', '% de victorias'], rows, [1]);
}

// ---------------------------------------------------------------- pestaña Comparar
function renderCompare() {
    const a = disc(state.cmpA), b = disc(state.cmpB);
    const opts = sel => state.data.disciplines.map(d => `<option value="${d.slug}" ${d.slug === sel ? 'selected' : ''}>${esc(d.name)}</option>`).join('');
    $('#cmp-a').innerHTML = opts(a.slug);
    $('#cmp-b').innerHTML = opts(b.slug);

    const axes = state.data.radar.categories;
    makeChart('butterfly', 'butterflyChart', {
        type: 'bar',
        data: { labels: axes, datasets: [
            { slug: a.slug, baseColor: a.color, label: a.name, data: axes.map(x => -a.scores[x]), backgroundColor: a.color, borderRadius: 4, maxBarThickness: 22 },
            { slug: b.slug, baseColor: b.color, label: b.name, data: axes.map(x => b.scores[x]), backgroundColor: b.color, borderRadius: 4, maxBarThickness: 22 },
        ] },
        options: {
            indexAxis: 'y',
            scales: { x: { min: -100, max: 100, grid: { color: C.grid }, ticks: { callback: v => Math.abs(v) } },
                      y: { stacked: true, grid: { display: false }, ticks: { color: C.text, font: { size: 13 } } } },
            plugins: { legend: { position: 'bottom', onClick: null },
                       tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${nf(Math.abs(c.parsed.x), 0)} / 100` } } },
        },
    });
    setTable('butterfly', ['Dimensión', a.name, b.name], axes.map(x => [x, nf(a.scores[x], 0), nf(b.scores[x], 0)]), [1, 2]);

    // Tabla cara a cara: cada fila sabe si gana el mayor o el menor
    const pa = parityInRange(a.slug), pb = parityInRange(b.slug);
    const avg = pts => pts.length ? pts.reduce((s, p) => s + p.y, 0) / pts.length : null;
    const riskRank = { bajo: 0, medio: 1, alto: 2 };
    const metrics = [
        { name: 'Crecimiento anual', va: a.growth, vb: b.growth, fmt: v => signed(v) + ' %', better: 'high' },
        { name: 'Volatilidad', va: a.volatility, vb: b.volatility, fmt: v => nf(v, 1) + ' %', better: 'low' },
        { name: `Paridad promedio (${rangeText()})`, va: avg(pa), vb: avg(pb), fmt: v => v == null ? 'sin datos' : nf(v, 1) + ' %', better: 'high' },
        { name: 'Peso de la región dominante', va: a.top_share, vb: b.top_share, fmt: v => nf(v, 0) + ' %', better: 'low' },
        { name: 'Riesgo', va: riskRank[a.risk_level], vb: riskRank[b.risk_level], fmt: v => ['bajo', 'medio', 'alto'][v], better: 'low' },
    ];
    let winsA = 0, winsB = 0;
    const rows = metrics.map(m => {
        let wa = false, wb = false;
        if (m.va != null && m.vb != null && m.va !== m.vb) {
            wa = m.better === 'high' ? m.va > m.vb : m.va < m.vb;
            wb = !wa;
        }
        winsA += wa; winsB += wb;
        return `<tr><td>${esc(m.name)}</td><td class="num ${wa ? 'win' : 'lose'}">${m.fmt(m.va)}</td><td class="num ${wb ? 'win' : 'lose'}">${m.fmt(m.vb)}</td></tr>`;
    }).join('');
    $('#h2h').innerHTML = `<table class="data-table"><thead><tr><th>Métrica</th><th class="num">${markHTML(a.slug)} ${esc(SHORT[a.slug])}</th><th class="num">${markHTML(b.slug)} ${esc(SHORT[b.slug])}</th></tr></thead><tbody>${rows}</tbody></table>
        <p class="h2h-summary">El ✓ marca el mejor valor para un inversionista: más crecimiento y paridad, menos volatilidad, concentración y riesgo.</p>`;
    $('#compare-title').textContent = winsA === winsB
        ? `${a.name} y ${b.name} empatan ${winsA} a ${winsB}`
        : `${winsA > winsB ? a.name : b.name} gana ${Math.max(winsA, winsB)} de las ${metrics.length} métricas frente a ${winsA > winsB ? b.name : a.name}`;

    $('#cmp-line-title').textContent = `Paridad en el tiempo (${rangeText()})`;
    makeChart('cmpLine', 'cmpLineChart', {
        type: 'line',
        data: { datasets: [a, b].map(d => seriesStyle(d, { data: parityInRange(d.slug), cubicInterpolationMode: 'monotone' })) },
        options: {
            layout: { padding: { right: 36, top: 10 } },
            datasets: { line: { clip: false } },
            interaction: { mode: 'nearest', intersect: false },
            scales: { x: { type: 'linear', min: state.from, max: state.to, grid: { color: C.grid }, ticks: { stepSize: 1, maxTicksLimit: 14, callback: v => String(v) } },
                      y: { min: 0, max: 100, grid: { color: C.grid }, ticks: { callback: v => v + ' %', stepSize: 25 } } },
            plugins: { legend: { position: 'bottom', onClick: null }, endLabels: { enabled: true },
                       tooltip: { callbacks: { title: items => String(items[0].parsed.x), label: c => ` ${c.dataset.label}: ${nf(c.parsed.y, 1)} %` } } },
            onHover: hoverHighlight('cmpLineChart'),
        },
    });
    const years = [...new Set([...pa, ...pb].map(p => p.x))].sort((x, y) => x - y);
    const at = (pts, y) => { const p = pts.find(q => q.x === y); return p ? nf(p.y, 1) + ' %' : '—'; };
    setTable('cmpLine', ['Año', a.name, b.name], years.map(y => [y, at(pa, y), at(pb, y)]), [1, 2]);
}

// ---------------------------------------------------------------- pestaña Simulador
function computeAllocation(capital, profile) {
    const slider = $('#capital-slider');
    const min = Number(slider.min), max = Number(slider.max);
    const t = Math.log(capital / min) / Math.log(max / min);  // 0 con el mínimo, 1 con el máximo
    const concentration = 1 + 3 * (1 - t);
    const weights = PROFILE_WEIGHTS[profile];
    const list = enabledList();
    const raw = list.map(d => {
        const score = Object.entries(weights).reduce((s, [axis, w]) => s + w * (d.scores[axis] || 0) / 100, 0);
        return Math.pow(score * RISK_FIT[profile][d.risk_level], concentration);
    });
    const total = raw.reduce((x, y) => x + y, 0);
    return list.map((d, i) => ({ ...d, share: raw[i] / total, amount: capital * raw[i] / total }));
}

function renderSim() {
    const slider = $('#capital-slider');
    const capital = Number(slider.value);
    slider.style.setProperty('--fill', ((capital - slider.min) / (slider.max - slider.min) * 100) + '%');
    $('#amount-display').textContent = money(capital);

    const alloc = computeAllocation(capital, state.risk);
    state.lastAlloc = alloc;
    // Tendencia limitada a ±25 % anual para no extrapolar valores extremos
    const ret = alloc.reduce((s, x) => s + x.share * Math.max(-25, Math.min(25, x.growth)), 0);
    const vol = alloc.reduce((s, x) => s + x.share * x.volatility, 0);
    state.lastReturn = ret;

    const r = $('#kpi-return'), g = $('#kpi-gain');
    r.textContent = signed(ret) + ' %';
    g.textContent = (ret >= 0 ? '+' : '−') + moneyCompact(Math.abs(capital * ret / 100));
    r.className = g.className = 'stat-value ' + (ret >= 0 ? 'pos' : 'neg');
    $('#kpi-vol').textContent = '±' + nf(vol, 1) + ' %';

    const data = alloc.map(x => Math.round(x.amount));
    if (charts.portfolio && charts.portfolio.data.datasets[0].slugs.join() === alloc.map(x => x.slug).join()) {
        charts.portfolio.data.datasets[0].data = data;  // mismo set de disciplinas: animar en vez de recrear
        charts.portfolio.update();
    } else {
        makeChart('portfolio', 'doughnutChart', {
            type: 'doughnut',
            data: { labels: alloc.map(x => x.name), datasets: [{
                data, slugs: alloc.map(x => x.slug), baseColors: alloc.map(x => x.color), backgroundColor: alloc.map(x => x.color),
                borderColor: C.surface, borderWidth: 3, hoverOffset: 6 }] },
            options: {
                cutout: '70%',
                plugins: { legend: { display: false }, centerText: { enabled: true },
                           tooltip: { callbacks: { label: c => {
                               const total = c.dataset.data.reduce((x, y) => x + y, 0);
                               return ` ${money(c.parsed)} (${nf(c.parsed / total * 100, 1)} %)`;
                           } } } },
                onHover: (_e, els, chart) => setHighlight(els.length ? chart.data.datasets[0].slugs[els[0].index] : null),
            },
        });
        $('#doughnutChart').onmouseleave = () => setHighlight(null);
    }
    const sorted = alloc.slice().sort((x, y) => y.share - x.share);
    $('#alloc-list').innerHTML = sorted.map(x => `<li>${markHTML(x.slug)}
        <span>${esc(x.name)}<span class="risk risk-${x.risk_level}">${x.risk_level}</span></span>
        <span class="pct">${nf(x.share * 100, 1)} %</span><span class="usd">${money(x.amount)}</span></li>`).join('');
    setTable('portfolio', ['Disciplina', 'Riesgo', '% del capital', 'Monto'],
        sorted.map(x => [x.name, x.risk_level, nf(x.share * 100, 1) + ' %', money(x.amount)]), [2, 3]);
}

function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '=([^;]*)');
    return m ? decodeURIComponent(m[2]) : '';
}

async function savePortfolio() {
    const btn = $('#save-portfolio'), msg = $('#save-msg');
    btn.disabled = true;
    msg.className = 'save-msg';
    msg.textContent = 'Guardando…';
    try {
        const res = await fetch('/api/portfolio/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({
                capital: Number($('#capital-slider').value),
                risk_profile: state.risk,
                allocation: Object.fromEntries(state.lastAlloc.map(x => [x.slug, Math.round(x.share * 1000) / 10])),
                expected_return: state.lastReturn,
            }),
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.error || 'No se pudo guardar.');
        msg.className = 'save-msg ok';
        msg.textContent = `✓ Portafolio guardado: ${money(Number($('#capital-slider').value))}, perfil ${state.risk}.`;
    } catch (err) {
        msg.className = 'save-msg err';
        msg.textContent = '✕ ' + err.message;
    } finally {
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------- navegación
const RENDER = { panorama: renderPanorama, paridad: renderParity, disciplinas: renderDetail, comparar: renderCompare, simulador: renderSim };

function renderActive() {
    RENDER[state.tab]();
}

function showTab(tab) {
    if (!RENDER[tab]) tab = 'panorama';
    state.tab = tab;
    document.querySelectorAll('.tab').forEach(b => {
        const on = b.dataset.tab === tab;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on);
    });
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + tab));
    history.replaceState(null, '', '#' + tab);
    state.highlight = null;
    renderActive();
}

function setupEvents() {
    document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
    window.addEventListener('hashchange', () => { if (location.hash.slice(1) !== state.tab) showTab(location.hash.slice(1)); });
    document.addEventListener('click', e => {
        const btn = e.target.closest('.table-toggle');
        if (!btn) return;
        const card = btn.closest('.card');
        const table = card.querySelector('.table-view');
        const showing = table.hidden;
        table.hidden = !showing;
        card.querySelectorAll('.chart-box, .heatmap').forEach(el => {
            if (showing) { el.dataset.wasHidden = el.hidden; el.hidden = true; }
            else el.hidden = el.dataset.wasHidden === 'true';
        });
        btn.setAttribute('aria-expanded', showing);
        btn.textContent = showing ? 'Ver gráfico' : 'Ver tabla';
    });
    $('#capital-slider').addEventListener('input', renderSim);
    document.querySelectorAll('#risk-select button').forEach(b => b.addEventListener('click', () => {
        document.querySelectorAll('#risk-select button').forEach(x => { x.classList.toggle('active', x === b); x.setAttribute('aria-checked', x === b); });
        state.risk = b.dataset.risk;
        renderSim();
    }));
    $('#cmp-a').addEventListener('change', e => {
        state.cmpA = e.target.value;
        if (state.cmpA === state.cmpB) state.cmpB = state.data.disciplines.find(d => d.slug !== state.cmpA).slug;
        renderCompare();
    });
    $('#cmp-b').addEventListener('change', e => {
        state.cmpB = e.target.value;
        if (state.cmpA === state.cmpB) state.cmpA = state.data.disciplines.find(d => d.slug !== state.cmpB).slug;
        renderCompare();
    });
    const save = $('#save-portfolio');
    if (save) save.addEventListener('click', savePortfolio);
}

// ---------------------------------------------------------------- inicio
async function init() {
    setupChartDefaults();
    try {
        const res = await fetch('/api/chart-data/');
        if (!res.ok) throw new Error(`la API respondió ${res.status}`);
        state.data = await res.json();
    } catch (err) {
        $('#panorama-title').textContent = 'No se pudieron cargar los datos';
        $('.lede').textContent = `Revisa que el servidor esté corriendo y que la base esté poblada (python populate_db.py). Detalle: ${err.message}`;
        return;
    }
    state.data.disciplines.forEach(d => state.enabled.add(d.slug));
    renderTeams();
    setupYearFilter();
    setupEvents();
    if (document.fonts) await document.fonts.ready;  // los gráficos miden texto con la fuente final
    showTab(location.hash.slice(1) || 'panorama');
}

init();
