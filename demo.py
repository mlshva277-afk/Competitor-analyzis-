"""Synthetic data never written to the real database."""
import pandas as pd
from sqlalchemy import select
from storage import Account
from ingest import import_frame


def populate_demo(factory):
    now = pd.Timestamp.now(tz='UTC').floor('s')
    first = now.normalize().replace(day=1)
    posts, audience, comments = [], [], []
    with factory() as session:
        accounts = list(session.scalars(select(Account)))
    for i, account in enumerate(accounts):
        for month, followers in [(first-pd.offsets.MonthBegin(1), 1000+i*200), (first, 1050+i*210)]:
            audience.append(dict(platform=account.platform, account_id=account.account_id, observed_at=month.isoformat(), followers=followers, source_url=account.source_url, dataset='demo'))
        for j in range(3):
            post_id = f'demo-{i}-{j}'
            posts.append(dict(company_id=account.company_id, platform=account.platform, account_id=account.account_id,
                              post_id=post_id, source_url=f'https://example.org/demo/{post_id}',
                              published_at=(now-pd.Timedelta(days=10+j*9)).isoformat(), observed_at=now.isoformat(),
                              text=['DEMO: отчётность, выручка и дивиденды', 'DEMO: как работает облачный продукт', 'DEMO: вебинар о рынке'][j],
                              kind='official', reactions=20+i+j*3, comments_count=4+j, shares=2,
                              views='' if j == 2 else 500+i*40, reach='', followers=1050+i*210,
                              formats='текст|карточки' if j == 0 else 'текст', dataset='demo'))
            comments.append(dict(company_id=account.company_id, platform=account.platform, post_id=post_id, kind='official',
                                 comment_id='demo-question', text='DEMO: Когда будут дивиденды?',
                                 source_url=f'https://example.org/demo/{post_id}#comment', issuer_tone='нейтральный',
                                 market_tone='не определён', question_topic='сроки дивидендов', dataset='demo'))
    posts.append(dict(company_id='selectel', platform='telegram', account_id='', post_id='demo-external',
                      source_url='https://example.org/demo/external', published_at=(now-pd.Timedelta(days=12)).isoformat(),
                      observed_at=now.isoformat(), text='DEMO: внешний обзор рынка облачных продуктов', kind='external',
                      reactions=10, comments_count=2, shares=1, views=300, reach='', followers='', formats='текст', dataset='demo'))
    for kind, rows in [('posts', posts), ('audience', audience), ('comments', comments)]:
        import_frame(factory, pd.DataFrame(rows), kind, 'synthetic-demo', dataset='demo')


def ensure_monthly_demo(factory):
    """Supplement only the explicitly selected demo DB, once per report month.

    Real history is never synthesized. Existing demo records are kept intact.
    """
    from storage import SourceSyncRun
    from monthly import report_window, REPORT_TZ
    now = pd.Timestamp.now(tz=REPORT_TZ)
    window = report_window(now)
    marker = 'synthetic-monthly-demo-' + window.report_start.strftime('%Y-%m')
    with factory() as session:
        if session.scalar(select(SourceSyncRun).where(SourceSyncRun.source == marker)):
            return
        accounts = list(session.scalars(select(Account)))
    audience, posts = [], []
    # October report contains September-end minus August-end, and September posts.
    for i, account in enumerate(accounts):
        for day, followers in [(window.previous_snapshot_date, 1000+i*200), (window.snapshot_date, 1060+i*210)]:
            observed = pd.Timestamp(day, tz=REPORT_TZ) + pd.Timedelta(hours=23, minutes=55)
            audience.append(dict(platform=account.platform, account_id=account.account_id, observed_at=observed.isoformat(),
                                 followers=followers, source_url=account.source_url, dataset='demo'))
        for j in range(3):
            published = window.current_start + pd.Timedelta(days=3+j*8, hours=12)
            observed = pd.Timestamp(window.snapshot_date, tz=REPORT_TZ) + pd.Timedelta(hours=23, minutes=55)
            post_id = f'monthly-demo-{window.report_start:%Y%m}-{i}-{j}'
            posts.append(dict(company_id=account.company_id, platform=account.platform, account_id=account.account_id,
                              post_id=post_id, source_url=f'https://example.org/demo/{post_id}', published_at=published.isoformat(),
                              observed_at=observed.isoformat(), text=['DEMO: отчётность и финансовые результаты', 'DEMO: вебинар для инвесторов', 'DEMO: дивиденды и корпоративные новости'][j],
                              kind='official', reactions=30+i*3+j, comments_count=2+j, shares=1, views=500+i*40,
                              followers=1060+i*210, reach='', formats='текст|карточки', dataset='demo'))
    import_frame(factory, pd.DataFrame(audience), 'audience', marker, dataset='demo')
    import_frame(factory, pd.DataFrame(posts), 'posts', marker, dataset='demo')
