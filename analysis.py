"""Pure analytics: null is unknown, never an implicit zero."""
import pandas as pd
from sqlalchemy import select
from storage import Account, AudienceSnapshot, Post, PostMetricSnapshot, TopicLabel, Comment

TOPICS = {
    'отчётность/финансы': ['отчет', 'отчёт', 'выручк', 'прибыл', 'ebitda'],
    'дивиденды': ['дивиденд'],
    'корпоративные новости': ['совет директор', 'сделк', 'назначен', 'собрани'],
    'продукты': ['продукт', 'сервис', 'релиз', 'облачн'],
    'кейсы': ['кейс', 'внедрен', 'внедрён'],
    'рынок': ['рынок', 'рынк', 'ставк', 'котиров'],
    'образовательный контент': ['как ', 'инструкц', 'разбираем', 'объясня'],
    'мероприятия': ['вебинар', 'конференц', 'мероприят'],
    'репутационные темы': ['сбой', 'жалоб', 'надежн', 'надёжн', 'рейтинг'],
}
FORMATS = ['текст', 'иллюстрации', 'видео', 'опрос', 'карточки']
TONES = ['нейтральный', 'позитивный', 'негативный', 'смешанный', 'не определён']


def classify(text):
    lower = text.lower()
    return [topic for topic, words in TOPICS.items() if any(w in lower for w in words)]


def post_frame(factory, now=None, observed_before=None):
    now = pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    rows = []
    with factory() as session:
        for post in session.scalars(select(Post)):
            query = select(PostMetricSnapshot).where(PostMetricSnapshot.post_pk == post.id)
            if observed_before is not None:
                cutoff = pd.Timestamp(observed_before).tz_convert('UTC').isoformat()
                query = query.where(PostMetricSnapshot.observed_at < cutoff)
            metric = session.scalar(query.order_by(PostMetricSnapshot.observed_at.desc()).limit(1))
            labels = list(session.scalars(select(TopicLabel).where(TopicLabel.post_pk == post.id)))
            row = {c.name: getattr(post, c.name) for c in Post.__table__.columns}
            for field in ['reactions', 'comments_count', 'shares', 'views', 'reach', 'followers', 'observed_at']:
                row[field] = getattr(metric, field) if metric else None
            row['topics'] = [x.label for x in labels if x.category == 'topic']
            row['formats'] = [x.label for x in labels if x.category == 'format']
            # Interactions are only complete when every component is known.
            components = [row[x] for x in ['reactions', 'comments_count', 'shares']]
            row['interactions'] = sum(components) if all(x is not None for x in components) else None
            for denominator, name in [('followers', 'per_1000_followers'), ('views', 'per_1000_views')]:
                row[name] = row['interactions'] / row[denominator] * 1000 if row['interactions'] is not None and row[denominator] and row[denominator] > 0 else None
            published = pd.Timestamp(post.published_at)
            row['age_days'] = max(0, (now - published).total_seconds() / 86400)
            row['metric_age_days'] = max(0, (pd.Timestamp(metric.observed_at) - published).total_seconds() / 86400) if metric else None
            rows.append(row)
    columns = [c.name for c in Post.__table__.columns] + ['reactions', 'comments_count', 'shares', 'views', 'reach', 'followers', 'observed_at', 'topics', 'formats', 'interactions', 'per_1000_followers', 'per_1000_views', 'age_days', 'metric_age_days']
    return pd.DataFrame(rows, columns=columns)


def audience_comparison(factory, platform, month):
    """Report month refers to the two preceding exact month-end dates (Moscow)."""
    from monthly import report_window, REPORT_TZ
    window = report_window(month)
    rows = []
    with factory() as session:
        for account in session.scalars(select(Account).where(Account.platform == platform)):
            snapshots = list(session.scalars(select(AudienceSnapshot).where(AudienceSnapshot.account_pk == account.id)))
            current = sorted([s for s in snapshots if pd.Timestamp(s.observed_at).tz_convert(REPORT_TZ).date() == window.snapshot_date], key=lambda s: s.observed_at)
            past = sorted([s for s in snapshots if pd.Timestamp(s.observed_at).tz_convert(REPORT_TZ).date() == window.previous_snapshot_date], key=lambda s: s.observed_at)
            a, b = (current[-1] if current else None), (past[-1] if past else None)
            rows.append(dict(company_id=account.company_id, followers=a.followers if a else None,
                             observed_at=a.observed_at if a else None, previous_observed_at=b.observed_at if b else None,
                             delta=a.followers-b.followers if a and b else None,
                             delta_pct=(a.followers-b.followers)/b.followers*100 if a and b and b.followers > 0 else None))
    return pd.DataFrame(rows, columns=['company_id', 'followers', 'observed_at', 'previous_observed_at', 'delta', 'delta_pct'])


def rank_posts(frame, metric, minimum_age=7, ascending=False):
    if frame.empty:
        return frame
    if frame.platform.nunique() != 1:
        raise ValueError('Рейтинг допустим только внутри одной платформы')
    return frame.loc[(frame.metric_age_days >= minimum_age) & frame[metric].notna()].sort_values(metric, ascending=ascending)


def comments_frame(factory):
    with factory() as session:
        rows = []
        for comment, post in session.execute(select(Comment, Post).join(Post, Comment.post_pk == Post.id)):
            rows.append({**{c.name: getattr(comment, c.name) for c in Comment.__table__.columns}, 'company_id': post.company_id, 'platform': post.platform, 'published_at': post.published_at, 'kind': post.kind})
    return pd.DataFrame(rows)


def activity(frame, company_ids, start, end):
    days = max(1, (pd.Timestamp(end)-pd.Timestamp(start)).days+1)
    counts = frame.groupby('company_id').size() if not frame.empty else pd.Series(dtype=int)
    # Counts describe imported sample, not all platform posts.
    return pd.DataFrame([{'company_id': c, 'posts_in_sample': int(counts.get(c, 0)),
                          'posts_per_week_in_sample': counts.get(c, 0)*7/days} for c in company_ids])
