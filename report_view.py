"""Escaped, self-contained report HTML for the app and browser printing."""
from html import escape
from urllib.parse import urlsplit
import pandas as pd
from branding import font_css
from monthly import PLATFORM_NAMES, competitors, key_post

CSS = font_css()+'''
:root{--accent:#EB4247;--ink:#092433;--muted:#596974;--line:#CDD2D5;--surface:#E3E6E7}
*{box-sizing:border-box}body{margin:0;background:white;color:var(--ink);font-family:Manrope,sans-serif}
.report{max-width:1500px;margin:0 auto;padding:34px 28px;background:#fff;color:var(--ink);font:14px/1.45 Manrope,sans-serif}
.report .masthead{display:flex;justify-content:space-between;align-items:center;border-top:5px solid var(--accent);padding-top:16px;margin-bottom:25px}
.report .brand{font-size:25px;font-weight:600;letter-spacing:-1px}.report .eyebrow{font-size:11px;letter-spacing:1.4px;text-transform:uppercase;color:var(--muted)}
.report h1{font-size:38px;line-height:1.1;font-weight:300;margin:0 0 14px;letter-spacing:-1.2px}.report h2{font-size:24px;font-weight:400;margin:30px 0 17px}
.report .badge{display:inline-block;border:1px solid var(--line);border-radius:5px;padding:7px 12px;font-size:16px}.report .subtitle{color:var(--muted);margin:12px 0 24px}
.report .band{background:#092433;color:white;padding:9px 12px;font-weight:600;font-size:16px}.report .scroll{overflow-x:auto;padding:2px 0 8px}
.report table{border-collapse:collapse;width:100%;min-width:1000px;font-size:12px;table-layout:fixed}.report th,.report td{padding:12px 6px;text-align:center;border-bottom:1px solid #CDD2D5;border-right:1px dashed #CDD2D5;vertical-align:middle;overflow-wrap:anywhere}
.report th:first-child,.report td:first-child{text-align:left;width:120px;font-weight:600}.report th:last-child,.report td:last-child{border-right:0}
.report .baseline{background:#FFF4F4;border-left:1px dashed var(--accent);border-right:1px dashed var(--accent)}.report thead .baseline{border-top:1px dashed var(--accent)}.report tbody tr:last-child .baseline{border-bottom:1px dashed var(--accent)}
.report .total td{font-weight:600;border-bottom:0}.report .delta{white-space:nowrap}.report .unknown{font-size:11px;color:var(--muted)}.report .notes{font-size:12px;color:var(--muted);margin-top:12px}
.report .cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:30px}.report .card{min-width:0}.report .card-title{background:var(--surface);border-radius:12px;padding:18px;text-align:center;font-size:19px;margin-bottom:14px}
.report .post-count{font-size:16px;font-weight:600}.report .breakdown{font-size:13px;margin:3px 0 16px}.report a{color:#092433;text-decoration:underline;text-underline-offset:3px;word-break:break-word}.report .post-title{font-weight:600;font-size:15px;display:block;margin:0 0 12px}
.report .metrics{color:var(--muted);font-size:13px}.report .warning{border-left:3px solid var(--accent);padding:10px 14px;background:#fff5f5;margin:16px 0}
.report footer{border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;margin-top:32px;padding-top:14px;font-size:12px;color:var(--muted)}
@media(max-width:800px){.report{padding:20px 12px}.report h1{font-size:29px}.report .cards{grid-template-columns:1fr}.report footer{display:block}}
@media print{@page{size:A4 landscape;margin:10mm}.report{max-width:none;padding:0}.report .scroll{overflow:visible}.report table{min-width:0;font-size:9px}.report th,.report td{padding:8px 4px}.report .cards{gap:20px;grid-template-columns:repeat(3,1fr)}.report .card{break-inside:avoid}.report h1{font-size:28px}.report h2{font-size:20px}.report .card-title{padding:10px;font-size:16px}a{color:inherit!important}.report footer{font-size:10px}}
'''


def integer(value):
    return 'нет данных' if value is None or pd.isna(value) else f'{int(value):,}'.replace(',', ' ')


def percent(value):
    if value is None or pd.isna(value):
        return 'нет динамики'
    return f'{value:+.1f}%'.replace('.', ',')


def cell(row):
    if row is None or row.provided_accounts == 0:
        return '<span class="unknown">—</span>'
    if pd.isna(row.followers):
        return '<span class="unknown">нет данных</span>'
    return f'{integer(row.followers)} <span class="delta">({percent(row.delta_pct)})</span>'


def safe_link(value):
    value = str(value)
    return escape(value, quote=True) if urlsplit(value).scheme in ('http', 'https') else '#'


def fragment(window, audience, details, posts, company_names, platforms, activity, ranking_platform, metric, minimum_age, dataset, generated_at, now=None):
    current_time = pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    if current_time.tzinfo is None:
        current_time = current_time.tz_localize('UTC')
    company_ids = list(dict.fromkeys(audience.company_id))
    company_ids.sort(key=lambda c: (c != 'selectel', list(company_names).index(c)))
    warnings = []
    if dataset == 'demo':
        warnings.append('DEMO — синтетические данные. Не являются фактической статистикой компаний.')
    if window.report_start > current_time:
        warnings.append('Период ещё не завершён: итоговые данные на конец месяца пока недоступны. Отчёт предварительный.')
    rows = audience.loc[audience.platform != 'total']
    expected = int(rows.provided_accounts.sum()) if not rows.empty else 0
    observed = int(rows.observed_accounts.sum()) if not rows.empty else 0
    previous = int(rows.previous_observed_accounts.sum()) if not rows.empty else 0
    if observed < expected or previous < expected:
        warnings.append(f'Неполные снимки аудитории: на {window.snapshot_date:%d.%m.%Y} — {observed}/{expected} аккаунтов; на {window.previous_snapshot_date:%d.%m.%Y} — {previous}/{expected}. Ранние замеры не подставляются.')
    html = '<article class="report"><header class="masthead"><span class="brand">Selectel</span><span class="eyebrow">Инвестиционные коммуникации · аналитика</span></header>'
    html += f'<h1>Инвестиционные каналы</h1><div class="badge">Отчёт: {window.label} · данные: {window.data_label}</div>'
    html += f'<p class="subtitle">Аудитория на {window.snapshot_date:%d.%m.%Y} в сравнении с {window.previous_snapshot_date:%d.%m.%Y} · часовой пояс Москва</p>'
    for warning in warnings:
        html += f'<div class="warning">{escape(warning)}</div>'
    html += '<div class="band">Аудитория инвестиционных каналов</div><div class="scroll"><table><thead><tr><th>Площадка</th>'
    for company in company_ids:
        cls = ' class="baseline"' if company == 'selectel' else ''
        html += f'<th{cls}>{escape(company_names[company])}</th>'
    html += '</tr></thead><tbody>'
    for platform in [*platforms, 'total']:
        row_class = ' class="total"' if platform == 'total' else ''
        html += f'<tr{row_class}><td>{"Итого" if platform == "total" else escape(PLATFORM_NAMES[platform])}</td>'
        for company in company_ids:
            subset = audience.loc[(audience.company_id == company) & (audience.platform == platform)]
            row = subset.iloc[0] if not subset.empty else None
            cls = ' class="baseline"' if company == 'selectel' else ''
            html += f'<td{cls}>{cell(row)}</td>'
        html += '</tr>'
    html += '</tbody></table></div><p class="notes">В скобках — изменение к предыдущей дате. «—» — канал не предоставлен; «нет данных» — отсутствует снимок в нужный день. Итого — сумма аудитории предоставленных каналов на выбранных площадках, не уникальные люди. При отсутствии хотя бы одного нужного снимка сумма не рассчитывается.</p>'
    html += '<h2>Ключевые публикации топ-3 конкурентов</h2>'
    metric_name = {'reactions': 'Реакции', 'interactions': 'Взаимодействия', 'per_1000_followers': 'Взаимодействия на 1000 подписчиков', 'per_1000_views': 'Взаимодействия на 1000 просмотров'}[metric]
    html += f'<p class="notes">Компании выбраны по суммарной аудитории среди компаний с полными текущими снимками. Ключевой пост — по метрике «{escape(metric_name)}» только на площадке {escape(PLATFORM_NAMES[ranking_platform])}; метрики разных площадок не смешиваются. Минимальный возраст при замере: {minimum_age:g} дн.</p>'
    leaders = competitors(audience)
    if leaders.empty:
        html += '<div class="warning">Недостаточно данных аудитории на конец месяца, чтобы определить топ-3. Компании не выбираются произвольно.</div>'
    else:
        html += '<div class="cards">'
        for leader in leaders.itertuples():
            company_posts = posts.loc[posts.company_id == leader.company_id]
            previous_row = activity.loc[activity.company_id == leader.company_id]
            count = len(company_posts)
            previous_count = int(previous_row.iloc[0].previous_posts) if not previous_row.empty else 0
            breakdown = ', '.join(f'{PLATFORM_NAMES[p]}: {int((company_posts.platform == p).sum())}' for p in platforms)
            html += f'<section class="card"><div class="card-title">{escape(company_names[leader.company_id])}</div><div class="post-count">{count} публикаций в выборке за месяц</div><div class="breakdown">{escape(breakdown)}<br>Предыдущий месяц: {previous_count}; изменение выборки: {count-previous_count:+d}</div>'
            selected = key_post(posts, leader.company_id, ranking_platform, metric, minimum_age)
            if selected is None:
                html += '<p class="metrics">Нет поста с подходящим возрастом и известной выбранной метрикой, измеренной в последний день месяца.</p>'
            else:
                title = selected.text[:200] + ('…' if len(selected.text) > 200 else '')
                measured = pd.Timestamp(selected.observed_at).tz_convert('Europe/Moscow')
                html += f'<a class="post-title" href="{safe_link(selected.source_url)}" target="_blank" rel="noopener noreferrer">{escape(title)}</a><div class="metrics">'
                for key, label in [('views', 'Просмотры'), ('reactions', 'Реакции'), ('comments_count', 'Комментарии')]:
                    html += f'{label}: {integer(selected[key])}<br>'
                html += f'Возраст при замере: {selected.metric_age_days:.1f} дн.<br>Замер: {measured:%d.%m.%Y %H:%M} МСК</div>'
            html += '</section>'
        html += '</div>'
    if len(leaders) < 3 and len(leaders) > 0:
        html += f'<p class="notes">Полных снимков достаточно только для {len(leaders)} конкурентов; остальные карточки не выдумываются.</p>'
    html += '<p class="notes">Числа публикаций отражают импортированную выборку. Без подтверждённого покрытия они не означают полную активность компании. Посты опубликованы в отчётном периоде; поздние замеры метрик исключены.</p>'
    collected = pd.to_datetime(details.collected_at, utc=True).dropna() if not details.empty else pd.Series(dtype='datetime64[ns, UTC]')
    collected_label = collected.max().tz_convert('Europe/Moscow').strftime('%d.%m.%Y %H:%M') if not collected.empty else 'нет данных'
    html += f'<footer><span>Данные на {window.snapshot_date:%d.%m.%Y} · последняя загрузка снимка аудитории: {collected_label} МСК</span><span>Отчёт сформирован: {generated_at:%d.%m.%Y %H:%M} МСК</span></footer></article>'
    return html


def document(content):
    return '<!doctype html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Инвестиционные каналы — Selectel</title><style>'+CSS+'</style></head><body>'+content+'</body></html>'


def audience_matrix(audience, platforms, company_names):
    """Visible plain-text cells, ready for rich-table and TSV clipboard copy."""
    ids = list(dict.fromkeys(audience.company_id))
    ids.sort(key=lambda c: (c != 'selectel', list(company_names).index(c)))
    rows = []
    for platform in [*platforms, 'total']:
        row = {'Площадка': 'Итого' if platform == 'total' else PLATFORM_NAMES[platform]}
        for company in ids:
            matching = audience.loc[(audience.company_id == company) & (audience.platform == platform)]
            entry = matching.iloc[0] if not matching.empty else None
            if entry is None or entry.provided_accounts == 0:
                value = '—'
            elif pd.isna(entry.followers):
                value = 'нет данных'
            else:
                value = f'{integer(entry.followers)} ({percent(entry.delta_pct)})'
            row[company_names[company]] = value
        rows.append(row)
    return pd.DataFrame(rows)
