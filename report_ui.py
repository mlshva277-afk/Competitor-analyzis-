from io import BytesIO
import pandas as pd
import streamlit as st
from monthly import report_window, audience_report, monthly_posts, monthly_activity, PLATFORM_NAMES, REPORT_TZ
from report_view import CSS, fragment, document, audience_matrix
from clipboard_view import render_clipboard

METRIC_LABELS = {'reactions': 'Реакции', 'interactions': 'Взаимодействия', 'per_1000_followers': 'Взаимодействия на 1000 подписчиков', 'per_1000_views': 'Взаимодействия на 1000 просмотров'}


def render_monthly(factory, companies, selected, is_demo):
    today = pd.Timestamp.now(tz=REPORT_TZ)
    left, middle, right = st.columns([1, 1, 2])
    year = left.number_input('Год отчёта', min_value=2020, max_value=today.year+1, value=today.year, step=1, key='monthly_report_year')
    from monthly import MONTHS
    month = middle.selectbox('Месяц отчёта', range(1, 13), index=today.month-1, format_func=lambda m: MONTHS[m-1].capitalize(), key='monthly_report_month')
    platforms = right.multiselect('Площадки в сводной таблице', list(PLATFORM_NAMES), default=['pulse', 'telegram'], format_func=PLATFORM_NAMES.get)
    if not selected or not platforms:
        st.info('Выберите хотя бы одну компанию и одну площадку для отчёта.')
        return
    window = report_window(f'{year}-{month:02d}-01')
    st.caption(f'Отчёт за {window.label}: публикации за {window.data_label}, аудитория {window.snapshot_date:%d.%m.%Y} минус {window.previous_snapshot_date:%d.%m.%Y}. Все границы — по Москве. Например, ноябрь = 31 октября − 30 сентября.')
    with st.expander('Как выбирать ключевые публикации'):
        ranking_platform = st.selectbox('Площадка ключевых публикаций', platforms, format_func=PLATFORM_NAMES.get)
        metric = st.selectbox('Метрика ключевого поста', list(METRIC_LABELS), format_func=METRIC_LABELS.get)
        minimum_age = st.number_input('Минимальный возраст поста при замере в отчёте, дней', min_value=0, value=0)
        st.caption('Топ-3 компаний — по суммарной аудитории предоставленных каналов. Ключевой пост каждой — по выбранной метрике на одной площадке. Рейтинг постов учитывает только метрики, измеренные в последний день месяца; поздние замеры не используются.')
    audience, details = audience_report(factory, window, platforms, selected)
    posts = monthly_posts(factory, window, platforms, selected)
    activity = monthly_activity(factory, window, platforms, selected)
    content = fragment(window, audience, details, posts, companies, platforms, activity, ranking_platform, metric, minimum_age, 'demo' if is_demo else 'real', today)
    # Display through HTML sanitization; user strings and links are also escaped in report_view.
    st.html('<style>'+CSS+'</style>'+content)
    matrix = audience_matrix(audience, platforms, companies)
    st.subheader('Копирование таблицы аудитории')
    render_clipboard(matrix)
    with st.expander('Выбрать отдельные ячейки для копирования'):
        st.caption('Выделите ячейки таблицы и нажмите Ctrl+C (на Mac — ⌘C).')
        st.dataframe(matrix, hide_index=True, width='stretch')
    html = document(content)
    a, b = st.columns(2)
    a.download_button('Скачать отчёт HTML / для печати в PDF', html.encode('utf-8'), f'invest-report-{year}-{month:02d}.html', 'text/html')
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        for name, frame in [('audience', audience), ('snapshot_details', details), ('posts_as_of', posts), ('activity_sample', activity)]:
            safe = frame.copy()
            # Treat imported strings as text, never Excel formulas.
            for column in safe.select_dtypes(include=['object']).columns:
                safe[column] = safe[column].map(lambda v: "'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v)
            safe.to_excel(writer, sheet_name=name, index=False)
        pd.DataFrame([dict(report_month=str(window.report_start.date()), current_snapshot=str(window.snapshot_date),
                           previous_snapshot=str(window.previous_snapshot_date), timezone=REPORT_TZ,
                           generated_at=today.isoformat(), dataset='demo' if is_demo else 'real',
                           coverage='Только импортированная выборка', metric_platform=ranking_platform, metric=metric)]).to_excel(writer, sheet_name='report_metadata', index=False)
    b.download_button('Скачать данные отчёта XLSX', buffer.getvalue(), f'invest-report-{year}-{month:02d}.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.caption('Для PDF скачайте HTML, откройте его в браузере и выберите Печать → Сохранить как PDF (альбомная ориентация). Ссылка в карточке открывает исходную публикацию.')
    with st.expander('Проверить исходные замеры и полноту данных'):
        st.dataframe(details.rename(columns={'company': 'Компания', 'platform': 'Площадка', 'account_id': 'Аккаунт',
                                             'target_date': 'Требуемая дата', 'previous_target_date': 'Предыдущая дата',
                                             'observed_at': 'Замер', 'previous_observed_at': 'Предыдущий замер',
                                             'collected_at': 'Загружено', 'source_url': 'Источник'}), hide_index=True, width='stretch')
        st.caption('Снимок должен приходиться именно на требуемый календарный день в Москве. Последний доступный снимок внутри месяца не подменяет снимок на конец месяца. Статус проверки ссылки из реестра сам по себе не подтверждает статистику.')
