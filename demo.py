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
