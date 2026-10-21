import io
import json
from pathlib import Path
import pandas as pd
import pytest
from sqlalchemy import select, func
from storage import (database, seed_registry, Company, Account, Post, PostMetricSnapshot,
                     AudienceSnapshot, SourceSyncRun, Comment, TopicLabel)
from ingest import import_frame, read_table
from analysis import post_frame, audience_comparison, rank_posts, classify
from demo import populate_demo
from adapters import StubAdapter, FileAdapter

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def factory(tmp_path):
    _, factory = database(tmp_path/'test.sqlite')
    seed_registry(factory, ROOT/'data/accounts.json')
    return factory


def post(**overrides):
    return dict(company_id='selectel', platform='telegram', account_id='selectel_IR', post_id='1',
                source_url='https://t.me/selectel_IR/1', published_at='2026-01-01T10:00:00Z',
                observed_at='2026-01-11T10:00:00Z', text='Выручка и дивиденды', kind='official',
                reactions='10', comments_count='2', shares='3', views='100', followers='1000', **overrides)


def updated(**kwargs):
    result = post()
    result.update(kwargs)
    return result


def count(factory, cls):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(cls))


def test_registry_preserved_and_idempotent(factory):
    seed_registry(factory, ROOT/'data/accounts.json')
    assert count(factory, Company) == 10
    assert count(factory, Account) == 15
    with factory() as session:
        accounts = list(session.scalars(select(Account)))
    assert sum(a.platform == 'pulse' for a in accounts) == 10
    assert sum(a.platform == 'telegram' for a in accounts) == 5
    seed = json.loads((ROOT/'data/accounts.json').read_text())['sources']
    for a in accounts:
        expected = next(x for x in seed if x['account_id'] == a.account_id and x['platform'] == a.platform)
        for key in ['company_id', 'source_url', 'clean_url', 'verification']:
            assert getattr(a, key) == expected[key]


def test_metrics_and_nulls(factory):
    import_frame(factory, pd.DataFrame([post()]), 'posts')
    row = post_frame(factory).iloc[0]
    assert row.interactions == 15
    assert row.per_1000_followers == 15
    assert row.per_1000_views == 150
    assert row.reach is None
    import_frame(factory, pd.DataFrame([updated(shares='', views='', followers='0')]), 'posts')
    row = post_frame(factory).iloc[0]
    assert row.interactions is None
    assert row.per_1000_views is None
    assert row.per_1000_followers is None
    assert count(factory, Post) == 1
    assert count(factory, PostMetricSnapshot) == 1


def test_snapshot_history_latest(factory):
    import_frame(factory, pd.DataFrame([post(), updated(observed_at='2026-01-12T10:00:00Z', reactions='99')]), 'posts')
    assert count(factory, PostMetricSnapshot) == 2
    assert post_frame(factory).iloc[0].reactions == 99


def test_monthly_uses_only_actual_months(factory):
    row = dict(platform='telegram', account_id='selectel_IR', source_url='https://t.me/selectel_IR', followers='100', observed_at='2026-01-10T00:00:00Z')
    import_frame(factory, pd.DataFrame([row]), 'audience')
    result = audience_comparison(factory, 'telegram', '2026-02-01').set_index('company_id')
    assert pd.isna(result.loc['selectel', 'followers'])
    assert pd.isna(result.loc['selectel', 'delta'])
    row.update(followers='125', observed_at='2026-02-12T00:00:00Z')
    import_frame(factory, pd.DataFrame([row]), 'audience')
    result = audience_comparison(factory, 'telegram', '2026-02-01').set_index('company_id')
    assert result.loc['selectel', 'delta'] == 25
    assert result.loc['selectel', 'delta_pct'] == 25
    import_frame(factory, pd.DataFrame([row]), 'audience')
    assert count(factory, AudienceSnapshot) == 2
    assert audience_comparison(factory, 'telegram', '2026-04-01').delta.isna().all()


@pytest.mark.parametrize('changes', [dict(reactions='-1'), dict(shares='1.5'), dict(views='nan'),
    dict(account_id='unknown'), dict(company_id='unknown'), dict(source_url='javascript:alert(1)'),
    dict(observed_at='2025-12-01T00:00:00Z'), dict(published_at='2026-01-01'),
    dict(observed_at='2099-01-01T00:00:00Z'), dict(topics='invented'), dict(formats='invented'),
    dict(communication_tone='invented'), dict(dataset='demo')])
def test_invalid_import_atomic_and_logged(factory, changes):
    with pytest.raises(ValueError):
        import_frame(factory, pd.DataFrame([updated(post_id='good'), updated(**changes)]), 'posts')
    assert count(factory, Post) == 0
    with factory() as session:
        run = session.scalar(select(SourceSyncRun))
        assert run.status == 'error'
        assert run.error


def test_external_separate_without_inventing_account(factory):
    import_frame(factory, pd.DataFrame([post(), updated(kind='external', account_id='', source_url='https://example.org/1')]), 'posts')
    frame = post_frame(factory)
    assert set(frame.kind) == {'official', 'external'}
    assert count(factory, Account) == 15
    assert pd.isna(frame.loc[frame.kind == 'external', 'account_pk'].iloc[0])


def test_ranking_rejects_platform_mix_and_young_measurement(factory):
    import_frame(factory, pd.DataFrame([post(), updated(post_id='2', observed_at='2026-01-02T10:00:00Z', reactions='999')]), 'posts')
    frame = post_frame(factory)
    assert rank_posts(frame, 'reactions', 7).post_id.tolist() == ['1']
    mixed = frame.copy()
    mixed.loc[0, 'platform'] = 'pulse'
    with pytest.raises(ValueError):
        rank_posts(mixed, 'reactions')


def test_multiple_topics_formats_and_comments(factory):
    import_frame(factory, pd.DataFrame([updated(formats='текст|видео', topics='дивиденды|рынок')]), 'posts')
    row = post_frame(factory).iloc[0]
    assert set(row.topics) == {'дивиденды', 'рынок'}
    assert set(row.formats) == {'текст', 'видео'}
    comment = dict(company_id='selectel', platform='telegram', post_id='1', kind='official', comment_id='c1',
                   text='Когда дивиденды?', source_url='https://t.me/selectel_IR/1?comment=1',
                   issuer_tone='позитивный', market_tone='негативный', question_topic='сроки дивидендов')
    for _ in range(2):
        import_frame(factory, pd.DataFrame([comment]), 'comments')
    assert count(factory, Comment) == 1
    with factory() as session:
        c = session.scalar(select(Comment))
        assert c.issuer_tone == 'позитивный' and c.market_tone == 'негативный'
    assert {'отчётность/финансы', 'дивиденды'} <= set(classify('Выручка и дивиденды'))


def test_xlsx_csv_real_adapter(factory):
    frame = pd.DataFrame([post()])
    buf = io.BytesIO()
    frame.to_excel(buf, index=False)
    result = FileAdapter(buf.getvalue(), 'posts.xlsx', 'posts').sync(factory)
    assert result.rows == 1
    assert read_table(frame.to_csv(index=False).encode('utf-8-sig'), 'posts.csv').iloc[0].post_id == '1'
    with pytest.raises(Exception):
        FileAdapter(b'broken', 'bad.xlsx', 'posts').sync(factory)
    with factory() as session:
        assert session.scalars(select(SourceSyncRun).where(SourceSyncRun.status == 'error')).first()


def test_stub_and_demo_isolation(factory, tmp_path):
    result = StubAdapter('pulse').sync(factory)
    assert result.status == 'not_configured' and result.rows == 0
    _, demo = database(tmp_path/'demo.sqlite')
    seed_registry(demo, ROOT/'data/accounts.json')
    populate_demo(demo)
    assert count(demo, Post) == 46
    assert count(factory, Post) == 0


def test_absent_platform_returns_schema(factory):
    frame = audience_comparison(factory, 'vk', '2026-01-01')
    assert frame.empty
    assert {'company_id', 'followers', 'delta'} <= set(frame.columns)


def test_registry_files_match_uploads():
    # The checked-in JSON retains original metadata, not just extracted accounts.
    registry = json.loads((ROOT/'data/accounts.json').read_text())
    assert registry['comparison_baseline_company_id'] == 'selectel'
    assert registry['sources'][0]['verification'] == 'requires_live_check'
