"""Validated atomic CSV/XLSX imports. Explicit observed_at prevents fake history."""
from io import BytesIO
from urllib.parse import urlsplit
import pandas as pd
from sqlalchemy import select
from storage import (Account, Company, AudienceSnapshot, Post, PostMetricSnapshot,
                     TopicLabel, Comment, SourceSyncRun, utcnow)
from analysis import classify, TOPICS, FORMATS, TONES

PLATFORMS = ['pulse', 'telegram', 'vk', 'smartlab', 'alfa_investor', 'bcs_profit']
METRICS = ['reactions', 'comments_count', 'shares', 'views', 'reach', 'followers']
SCHEMAS = {
    'posts': ['company_id', 'platform', 'account_id', 'post_id', 'source_url', 'published_at', 'observed_at', 'text', 'kind', *METRICS, 'topics', 'formats', 'communication_tone'],
    'audience': ['platform', 'account_id', 'observed_at', 'source_url', 'followers'],
    'comments': ['company_id', 'platform', 'post_id', 'kind', 'comment_id', 'text', 'source_url', 'issuer_tone', 'market_tone', 'question_topic'],
}
REQUIRED = {
    'posts': ['company_id', 'platform', 'post_id', 'source_url', 'published_at', 'observed_at', 'text', 'kind'],
    'audience': SCHEMAS['audience'],
    'comments': ['company_id', 'platform', 'post_id', 'kind', 'comment_id', 'text', 'source_url'],
}


def read_table(content, name):
    if name.lower().endswith('.xlsx'):
        return pd.read_excel(BytesIO(content), dtype=str, keep_default_na=False)
    if name.lower().endswith('.csv'):
        return pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    raise ValueError('Поддерживаются CSV (UTF-8) и XLSX')


def clean(value):
    return '' if value is None or pd.isna(value) else str(value).strip()


def timestamp(value):
    if not clean(value):
        raise ValueError('Не указано время наблюдения/публикации')
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError('Некорректное время')
    if ts.tzinfo is None:
        raise ValueError('Время должно содержать часовой пояс, например 2026-10-01T12:00:00Z')
    ts = ts.tz_convert('UTC')
    if ts > pd.Timestamp.now(tz='UTC') + pd.Timedelta(minutes=5):
        raise ValueError('Дата находится в будущем')
    return ts.isoformat()


def number(value):
    value = clean(value)
    if not value:
        return None
    try:
        n = float(value)
        if not 0 <= n <= 9_000_000_000_000_000 or not n.is_integer():
            raise ValueError()
        return int(n)
    except (ValueError, OverflowError):
        raise ValueError('Метрики должны быть целыми неотрицательными числами либо пустыми') from None


def url(value):
    value = clean(value)
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Нужна публичная HTTP(S) ссылка без учётных данных')
    return value


def labels(value, allowed):
    values = list(dict.fromkeys(v.strip() for v in clean(value).split('|') if v.strip()))
    if set(values) - set(allowed):
        raise ValueError('Неизвестные метки: ' + ', '.join(set(values)-set(allowed)))
    return values


def log_run(factory, source, platform, status, count, error=None, account_pk=None):
    with factory.begin() as session:
        session.add(SourceSyncRun(source=source, platform=platform, status=status, rows_count=count,
                                  error=error, account_pk=account_pk,
                                  coverage='Только строки загруженного файла; полнота платформы не подтверждена'))


def import_frame(factory, frame, kind, source='file', dataset='real'):
    if kind not in SCHEMAS:
        raise ValueError('Неизвестный тип импорта')
    # A demo-labelled file must never enter the real database.
    try:
        missing = set(REQUIRED[kind]) - set(frame.columns)
        if missing:
            raise ValueError('Отсутствуют колонки: ' + ', '.join(sorted(missing)))
        if frame.empty:
            raise ValueError('Файл не содержит строк')
        if 'dataset' in frame and any(clean(v) and clean(v) != dataset for v in frame.dataset):
            raise ValueError('Метка dataset не совпадает с выбранным режимом')
        with factory.begin() as session:
            for index, raw in enumerate(frame.to_dict('records'), 2):
                try:
                    row = {k: clean(v) for k, v in raw.items()}
                    for field in REQUIRED[kind]:
                        if not row.get(field):
                            raise ValueError('Пустое обязательное поле ' + field)
                    platform = row['platform']
                    if platform not in PLATFORMS:
                        raise ValueError('Неизвестная платформа')
                    source_url = url(row['source_url'])
                    account = session.scalar(select(Account).where(Account.platform == platform, Account.account_id == row.get('account_id', '')))
                    if kind == 'audience':
                        if account is None:
                            raise ValueError('Аккаунт отсутствует в реестре')
                        observed = timestamp(row['observed_at'])
                        obj = session.scalar(select(AudienceSnapshot).where(AudienceSnapshot.account_pk == account.id, AudienceSnapshot.observed_at == observed))
                        if obj is None:
                            obj = AudienceSnapshot(account_pk=account.id, observed_at=observed)
                            session.add(obj)
                        obj.followers = number(row['followers'])
                        obj.source_url = source_url
                        obj.collected_at = utcnow()
                        continue
                    if session.get(Company, row['company_id']) is None:
                        raise ValueError('Компания отсутствует в реестре')
                    if row['kind'] not in ('official', 'external'):
                        raise ValueError('kind должен быть official или external')
                    post = session.scalar(select(Post).where(Post.company_id == row['company_id'], Post.platform == platform, Post.post_id == row['post_id'], Post.kind == row['kind']))
                    if kind == 'comments':
                        if post is None:
                            raise ValueError('Сначала импортируйте публикацию для комментария')
                        issuer = row.get('issuer_tone') or 'не определён'
                        market = row.get('market_tone') or 'не определён'
                        if issuer not in TONES or market not in TONES:
                            raise ValueError('Неизвестная тональность')
                        comment = session.scalar(select(Comment).where(Comment.post_pk == post.id, Comment.comment_id == row['comment_id']))
                        if comment is None:
                            comment = Comment(post_pk=post.id, comment_id=row['comment_id'])
                            session.add(comment)
                        for field in ['text', 'source_url']:
                            setattr(comment, field, row[field])
                        comment.issuer_tone, comment.market_tone = issuer, market
                        comment.question_topic = row.get('question_topic') or None
                        comment.collected_at = utcnow()
                        comment.analysis_method = 'manual_import' if row.get('issuer_tone') or row.get('market_tone') or row.get('question_topic') else 'unknown'
                        continue
                    if row['kind'] == 'official' and (account is None or account.company_id != row['company_id']):
                        raise ValueError('Официальный пост требует аккаунт компании из реестра')
                    published, observed = timestamp(row['published_at']), timestamp(row['observed_at'])
                    if observed < published:
                        raise ValueError('Наблюдение раньше публикации')
                    if post is None:
                        post = Post(company_id=row['company_id'], platform=platform, post_id=row['post_id'], kind=row['kind'])
                        session.add(post)
                    elif post.published_at != published:
                        raise ValueError('Для существующего поста нельзя менять время публикации')
                    post.account_pk = account.id if row['kind'] == 'official' else None
                    post.source_url, post.published_at, post.text = source_url, published, row['text']
                    post.collected_at = utcnow()
                    post.communication_tone = row.get('communication_tone') or 'не определён'
                    if post.communication_tone not in TONES:
                        raise ValueError('Неизвестный тон коммуникации')
                    post.label_method = 'manual_import' if row.get('topics') else 'local_rules'
                    session.flush()
                    metric = session.scalar(select(PostMetricSnapshot).where(PostMetricSnapshot.post_pk == post.id, PostMetricSnapshot.observed_at == observed))
                    if metric is None:
                        metric = PostMetricSnapshot(post_pk=post.id, observed_at=observed)
                        session.add(metric)
                    metric.source_url, metric.collected_at = source_url, utcnow()
                    for field in METRICS:
                        setattr(metric, field, number(row.get(field)))
                    for old in session.scalars(select(TopicLabel).where(TopicLabel.post_pk == post.id)):
                        session.delete(old)
                    session.flush()
                    for category, values in [('topic', labels(row.get('topics'), TOPICS) or classify(post.text)), ('format', labels(row.get('formats'), FORMATS) or ['текст'])]:
                        for value in values:
                            session.add(TopicLabel(post_pk=post.id, category=category, label=value))
                except Exception as exc:
                    raise ValueError(f'Строка {index}: {exc}') from exc
        # Record per account / external platform, so quality view covers each source.
        groups = frame.groupby(['platform', 'account_id'], dropna=False) if 'account_id' in frame else frame.groupby('platform')
        for key, group in groups:
            platform, account_id = key if isinstance(key, tuple) else (key, '')
            with factory() as session:
                account = session.scalar(select(Account).where(Account.platform == platform, Account.account_id == clean(account_id)))
                account_pk = account.id if account else None
            log_run(factory, source, platform, 'success', len(group), account_pk=account_pk)
        return len(frame)
    except Exception as exc:
        log_run(factory, source, 'import', 'error', 0, str(exc))
        raise
