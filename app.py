from pathlib import Path
from datetime import timedelta
import os
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select, func
from storage import database, seed_registry, Company, Account, Post, SourceSyncRun
from analysis import post_frame, audience_comparison, rank_posts, comments_frame, activity, TOPICS, FORMATS, TONES
from ingest import SCHEMAS
from adapters import FileAdapter, StubAdapter
from demo import populate_demo

st.set_page_config(page_title='Invest Social Intelligence', page_icon='📊', layout='wide')
ROOT = Path(__file__).resolve().parent


@st.cache_resource
def connect(path):
    engine, factory = database(path)
    seed_registry(factory, ROOT / 'data/accounts.json')
    return engine, factory

LABELS = {
    'company_id': 'Компания', 'platform': 'Площадка', 'account_id': 'Аккаунт',
    'source_url': 'Исходная ссылка', 'clean_url': 'Ссылка без параметров', 'verification': 'Проверка',
    'role': 'Роль', 'followers': 'Подписчики', 'observed_at': 'Время наблюдения',
    'previous_observed_at': 'Предыдущее наблюдение', 'delta': 'Изменение подписчиков', 'delta_pct': 'Изменение, %',
    'published_at': 'Опубликовано', 'collected_at': 'Собрано', 'text': 'Текст', 'kind': 'Тип материала',
    'reactions': 'Реакции', 'comments_count': 'Комментарии (метрика)', 'shares': 'Репосты',
    'views': 'Просмотры', 'reach': 'Охват', 'interactions': 'Взаимодействия',
    'per_1000_followers': 'Взаимодействия / 1000 подписчиков', 'per_1000_views': 'Взаимодействия / 1000 просмотров',
    'age_days': 'Возраст сейчас, дней', 'metric_age_days': 'Возраст при замере, дней',
    'topics': 'Темы', 'formats': 'Форматы', 'communication_tone': 'Тон коммуникации',
    'label_method': 'Метод разметки', 'post_id': 'ID поста', 'issuer_tone': 'Тон к эмитенту',
    'market_tone': 'Тон к рынку/активу', 'question_topic': 'Запрос инвестора',
    'analysis_method': 'Метод анализа', 'source': 'Источник', 'status': 'Статус', 'rows_count': 'Строк обработано',
    'error': 'Ошибка / ограничение', 'coverage': 'Охват выборки', 'account_pk': 'ID аккаунта в БД',
    'posts_in_sample': 'Постов в выборке', 'posts_per_week_in_sample': 'Постов в неделю (выборка)',
    'previous_posts': 'Постов в прошлом месяце (выборка)', 'sample_delta': 'Изменение числа постов (выборка)',
}

mode = st.sidebar.radio('Набор данных', ['Реальные данные', 'Демо (demo)'],
                        index=1 if os.getenv('ISI_DEFAULT_DEMO') == '1' else 0)
is_demo = mode == 'Демо (demo)'
real_path = Path(os.getenv('ISI_DB_PATH', str(ROOT/'data/invest.sqlite'))).resolve()
demo_path = real_path.with_name(real_path.stem + '.demo.sqlite')
engine, factory = connect(str(demo_path if is_demo else real_path))
if is_demo:
    with factory() as session:
        empty = session.scalar(select(func.count()).select_from(Post)) == 0
    if empty:
        populate_demo(factory)
    st.warning('DEMO — синтетические данные в отдельной базе. Не являются статистикой компаний. Ссылки example.org — демонстрационные.')

with factory() as session:
    companies = {x.id: x.name for x in session.scalars(select(Company))}
    registry = pd.DataFrame([{**{c.name: getattr(x, c.name) for c in Account.__table__.columns}, 'role': 'baseline' if x.company_id == 'selectel' else 'competitor'} for x in session.scalars(select(Account))])

page = st.sidebar.radio('Раздел', ['Обзор', 'Selectel vs конкуренты', 'Публикации', 'Темы и тренды', 'Реакции/комментарии', 'Источники и качество данных'])
platform = st.sidebar.selectbox('Площадка', ['pulse', 'telegram', 'vk', 'smartlab', 'alfa_investor', 'bcs_profit'])
kind_label = st.sidebar.radio('Материалы', ['Официальные посты', 'Внешние упоминания'])
kind = 'official' if kind_label == 'Официальные посты' else 'external'
today = pd.Timestamp.now(tz='UTC').date()
period = st.sidebar.date_input('Период публикации (UTC)', (today-timedelta(days=89), today))
selected = st.sidebar.multiselect('Компании', list(companies), default=list(companies), format_func=companies.get)
st.sidebar.caption('Нет данных ≠ 0. Покрытие: только импортированные строки. Полный сбор платформ не заявляется.')
frame_all = post_frame(factory)
if not isinstance(period, (tuple, list)) or len(period) != 2:
    st.info('Выберите начало и конец периода.')
    st.stop()
start, end = period
frame = frame_all.loc[(frame_all.platform == platform) & (frame_all.kind == kind) & frame_all.company_id.isin(selected)].copy()
if not frame.empty:
    dates = pd.to_datetime(frame.published_at, utc=True).dt.date
    frame = frame.loc[(dates >= start) & (dates <= end)]
st.title('Invest Social Intelligence')
st.caption(f'{page} · {platform} · {kind_label} · {start:%d.%m.%Y} — {end:%d.%m.%Y} · {"demo" if is_demo else "real"}')


def table(df, columns=None):
    if df.empty:
        st.info('Нет данных в выбранной выборке.')
        return
    view = df.copy() if columns is None else df[[c for c in columns if c in df]].copy()
    if 'company_id' in view:
        view['company_id'] = view.company_id.map(companies)
    for c in view:
        if view[c].map(lambda v: isinstance(v, list)).any():
            view[c] = view[c].map(lambda v: ' | '.join(v) if isinstance(v, list) else v)
    view = view.rename(columns=LABELS)
    st.dataframe(view.style.format(na_rep='нет данных', precision=2), hide_index=True, width='stretch',
                 column_config={'Исходная ссылка': st.column_config.LinkColumn('Исходная ссылка')})


POST_COLUMNS = ['company_id', 'post_id', 'source_url', 'published_at', 'observed_at', 'text', 'reactions', 'comments_count', 'shares', 'views', 'reach', 'followers', 'interactions', 'per_1000_followers', 'per_1000_views', 'age_days', 'metric_age_days', 'topics', 'formats', 'communication_tone', 'label_method']

if page == 'Обзор':
    a, b, c, d = st.columns(4)
    a.metric('Компаний в реестре', len(companies))
    b.metric('Аккаунтов в реестре', len(registry))
    c.metric('Пульс', int((registry.platform == 'pulse').sum()))
    d.metric('Telegram', int((registry.platform == 'telegram').sum()))
    st.subheader('Выбранная выборка')
    st.metric('Импортированных публикаций', len(frame))
    if frame.empty:
        st.info('Нет данных о публикациях. Импортируйте CSV/XLSX в разделе «Источники и качество данных» или включите демо.')
    else:
        daily = frame.assign(day=pd.to_datetime(frame.published_at, utc=True).dt.date).groupby(['day', 'company_id']).size().reset_index(name='Публикации')
        daily['Компания'] = daily.company_id.map(companies)
        st.plotly_chart(px.line(daily, x='day', y='Публикации', color='Компания', markers=True, labels={'day': 'Дата (UTC)'}), width='stretch')
        st.caption('Число строк в выборке не доказывает полноту активности компании на площадке.')
    st.subheader('Исходный реестр')
    table(registry, ['company_id', 'role', 'platform', 'account_id', 'source_url', 'clean_url', 'verification'])

elif page == 'Selectel vs конкуренты':
    st.subheader('Аудитория: выбранный месяц против предыдущего')
    month = st.date_input('Месяц сравнения', today.replace(day=1))
    st.caption('Последний реальный снимок в каждом календарном месяце (UTC). Без снимка в одном из месяцев динамика отсутствует. Даты замеров показаны в таблице.')
    aud = audience_comparison(factory, platform, month)
    all_companies = pd.DataFrame({'company_id': pd.Series(selected, dtype=object)})
    aud = all_companies.merge(aud, how='left', on='company_id')
    table(aud)
    missing_accounts = set(selected)-set(registry.loc[registry.platform == platform, 'company_id'])
    if missing_accounts:
        st.info('Аккаунт на этой площадке не предоставлен: ' + ', '.join(companies[c] for c in sorted(missing_accounts)) + '. Новые каналы не предполагаются.')
    st.subheader('Активность по выбранному периоду')
    table(activity(frame, selected, start, end))
    st.subheader('Активность: выбранный месяц против предыдущего')
    month_start = pd.Timestamp(month, tz='UTC').replace(day=1)
    prev_start = month_start-pd.offsets.MonthBegin(1)
    next_start = month_start+pd.offsets.MonthBegin(1)
    subset = frame_all.loc[(frame_all.platform == platform) & (frame_all.kind == kind)]
    if subset.empty:
        st.info('Нет данных для сравнения активности.')
    else:
        times = pd.to_datetime(subset.published_at, utc=True)
        current = subset.loc[(times >= month_start) & (times < next_start)].groupby('company_id').size()
        previous = subset.loc[(times >= prev_start) & (times < month_start)].groupby('company_id').size()
        comparison = pd.DataFrame([dict(company_id=c, posts_in_sample=current.get(c, 0), previous_posts=previous.get(c, 0), sample_delta=current.get(c, 0)-previous.get(c, 0)) for c in selected])
        table(comparison)
        st.caption('Нули здесь означают отсутствие строк в импортированной выборке, а не отсутствие публикаций. Сравнение полного текущего и предыдущего месяца требует полного покрытия; текущий месяц может быть незавершён.')
    st.subheader('Лидеры и нижняя часть рейтинга')
    metric = st.selectbox('Метрика', ['reactions', 'interactions', 'per_1000_followers', 'per_1000_views'], format_func=LABELS.get)
    min_age = st.number_input('Минимальный возраст поста при замере метрик, дней', min_value=0, value=7)
    st.caption('Рейтинг только в пределах выбранной платформы и периода. Возраст при замере, аудитория и время замера доступны в строках. Нижние позиции не означают «неуспешные» посты; длительность накопления реакций может различаться.')
    st.write('Лидеры')
    table(rank_posts(frame, metric, min_age).head(10), POST_COLUMNS)
    st.write('Нижняя часть рейтинга')
    table(rank_posts(frame, metric, min_age, ascending=True).head(10), POST_COLUMNS)

elif page == 'Публикации':
    query = st.text_input('Поиск по тексту')
    topic = st.selectbox('Тема', ['Все', *TOPICS])
    content_format = st.selectbox('Формат', ['Все', *FORMATS])
    if query:
        frame = frame.loc[frame.text.str.contains(query, case=False, regex=False)]
    if topic != 'Все':
        frame = frame.loc[frame.topics.map(lambda values: topic in values)]
    if content_format != 'Все':
        frame = frame.loc[frame.formats.map(lambda values: content_format in values)]
    table(frame, POST_COLUMNS)
    export = frame.copy()
    export['dataset'] = 'demo' if is_demo else 'real'
    st.download_button('Скачать выборку CSV', export.to_csv(index=False).encode('utf-8-sig'), 'posts-selection.csv', 'text/csv')

elif page == 'Темы и тренды':
    st.caption('Локальные правила по ключевым словам — предварительная разметка, не экспертное заключение. Тон коммуникации импортируется вручную, иначе «не определён». Темы и форматы могут быть множественными.')
    if frame.empty:
        st.info('Нет данных для анализа тем.')
    else:
        topic_rows = frame.explode('topics').dropna(subset=['topics'])
        if not topic_rows.empty:
            stats = topic_rows.groupby(['company_id', 'topics']).size().reset_index(name='Постов')
            stats['Компания'] = stats.company_id.map(companies)
            st.plotly_chart(px.bar(stats, x='topics', y='Постов', color='Компания', barmode='group', labels={'topics': 'Тема'}), width='stretch')
            trend = topic_rows.assign(Месяц=pd.to_datetime(topic_rows.published_at, utc=True).dt.strftime('%Y-%m')).groupby(['Месяц', 'topics']).size().reset_index(name='Постов')
            st.plotly_chart(px.line(trend, x='Месяц', y='Постов', color='topics', markers=True, labels={'topics': 'Тема'}), width='stretch')
        else:
            st.info('Темы не определены. Добавьте ручные метки в импорт.')
        formats = frame.explode('formats').groupby('formats').size().reset_index(name='Постов')
        st.plotly_chart(px.bar(formats, x='formats', y='Постов', labels={'formats': 'Формат'}), width='stretch')
        table(frame, ['company_id', 'text', 'topics', 'formats', 'communication_tone', 'label_method', 'source_url'])

elif page == 'Реакции/комментарии':
    st.caption('Взаимодействия = реакции + комментарии + репосты, только если известны все три компонента. Охват и просмотры хранятся отдельно. Знаменатель подписчиков — измерение, переданное вместе с метриками поста; текущая аудитория не подставляется.')
    table(frame, POST_COLUMNS)
    st.subheader('Комментарии и вопросы инвесторов')
    st.caption('Тон к эмитенту и рынку/активу задаётся раздельно при импорте. Без ручной оценки — «не определён». question_topic — ручная группировка запроса; без неё вопросы по знаку «?» лишь кандидаты для просмотра.')
    comments = comments_frame(factory)
    if comments.empty:
        st.info('Нет данных о текстах комментариев. Числовая метрика комментариев не заменяет их тексты.')
    else:
        comments = comments.loc[comments.post_pk.isin(frame.id)]
        tone = st.selectbox('Тон к эмитенту', ['Все', *TONES])
        if tone != 'Все':
            comments = comments.loc[comments.issuer_tone == tone]
        table(comments, ['company_id', 'text', 'issuer_tone', 'market_tone', 'question_topic', 'analysis_method', 'source_url'])
        questions = comments.loc[comments.question_topic.notna() | comments.text.str.contains('?', regex=False)].copy()
        if not questions.empty:
            questions['question_topic'] = questions.question_topic.fillna('Вопрос без ручной классификации')
            grouped = questions.groupby('question_topic').size().reset_index(name='Количество в выборке')
            table(grouped)
            table(questions, ['company_id', 'text', 'question_topic', 'source_url'])
        else:
            st.info('Содержательные вопросы в импортированной выборке не размечены.')

else:
    st.subheader('Импорт CSV / XLSX')
    st.caption('Импорт атомарный: ошибочная строка отклоняет весь файл. Повторный импорт обновляет тот же снимок, а новый observed_at сохраняет историю. dataset=demo запрещён в реальном режиме. Пустая метрика означает отсутствие данных, ноль — измеренный ноль.')
    import_kind = st.selectbox('Тип данных', ['posts', 'audience', 'comments'], format_func={'posts': 'Публикации и метрики', 'audience': 'Снимки аудитории', 'comments': 'Тексты комментариев'}.get)
    st.code(','.join(SCHEMAS[import_kind]), language=None)
    template = pd.DataFrame(columns=SCHEMAS[import_kind]+['dataset']).to_csv(index=False).encode('utf-8-sig')
    st.download_button('Скачать шаблон CSV', template, f'{import_kind}-template.csv', 'text/csv')
    upload = st.file_uploader('Файл UTF-8 CSV или XLSX', type=['csv', 'xlsx'])
    if st.button('Импортировать', disabled=upload is None):
        try:
            result = FileAdapter(upload.getvalue(), Path(upload.name).name, import_kind, 'demo' if is_demo else 'real').sync(factory)
            st.success(f'Импортировано строк: {result.rows}. Перейдите в нужный раздел для просмотра.')
        except Exception as exc:
            st.error(str(exc))
    st.subheader('Покрытие и ограничения')
    st.info('Официальные посты и внешние упоминания разделены. Покрытие — только предоставленные файлы. Реестр не подтверждает доступность сбора или текущую официальность аккаунта. История аудитории не восстанавливается.')
    st.write('OpenAI: выключен. Локальный режим не требует ключей. ChatGPT Plus не включает кредиты OpenAI API. Вызовы OpenAI в MVP не реализованы.')
    st.write('VK API / TGStat API: интерфейс адаптера подготовлен, сетевые реализации пока отсутствуют. Пульс, Смартлаб, Альфа-Инвестор, БКС Профит: доступность официальных API и условия использования не проверены; используется импорт файлов. Авторизация и ограничения платформ не обходятся.')
    table(registry, ['company_id', 'platform', 'account_id', 'verification', 'source_url'])
    st.subheader('Статус каждого источника')
    with factory() as session:
        runs = pd.DataFrame([{c.name: getattr(run, c.name) for c in SourceSyncRun.__table__.columns} for run in session.scalars(select(SourceSyncRun).order_by(SourceSyncRun.id.desc()))])
    statuses = []
    for account in registry.to_dict('records'):
        relevant = runs.loc[runs.account_pk == account['id']] if not runs.empty else pd.DataFrame()
        statuses.append(dict(company_id=account['company_id'], platform=account['platform'], account_id=account['account_id'],
                             status=relevant.iloc[0]['status'] if not relevant.empty else 'не синхронизирован',
                             collected_at=relevant.iloc[0]['collected_at'] if not relevant.empty else None,
                             error=relevant.iloc[0]['error'] if not relevant.empty else None))
    table(pd.DataFrame(statuses))
    st.subheader('Журнал импорта / синхронизации')
    table(runs, ['source', 'platform', 'account_pk', 'collected_at', 'status', 'rows_count', 'error', 'coverage'])
    with st.expander('Проверить заглушку адаптера (без сети)'):
        if st.button('Проверить выбранную площадку'):
            result = StubAdapter(platform).sync(factory)
            st.warning(result.message)
