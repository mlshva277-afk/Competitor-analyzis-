from pathlib import Path
from datetime import date
import pandas as pd
import pytest
from sqlalchemy import select, func
from monthly import (report_window, audience_report, monthly_posts, monthly_activity,
                     competitors, key_post)
from report_view import fragment, document
from storage import database, seed_registry, Post
from ingest import import_frame
from demo import ensure_monthly_demo


@pytest.fixture
def factory(tmp_path):
    _, factory = database(tmp_path/'monthly.sqlite')
    seed_registry(factory, Path(__file__).resolve().parents[1]/'data/accounts.json')
    return factory


def audience(factory, platform, account, value, observed):
    import_frame(factory, pd.DataFrame([dict(platform=platform, account_id=account, followers=value,
                 observed_at=observed, source_url='https://example.org/observation')]), 'audience')


def post(factory, post_id='1', published='2024-10-05T10:00:00Z', measured='2024-10-31T18:00:00Z', reactions=10, **kwargs):
    row = dict(company_id='selectel', platform='telegram', account_id='selectel_IR', post_id=post_id,
               source_url='https://example.org/post/'+post_id, published_at=published, observed_at=measured,
               text='Отчётность', kind='official', reactions=reactions, comments_count=2, shares=1, views=100,
               followers=1000)
    row.update(kwargs)
    import_frame(factory, pd.DataFrame([row]), 'posts')


def test_november_means_october_vs_september():
    window = report_window('2024-11-25')
    assert window.snapshot_date == date(2024, 10, 31)
    assert window.previous_snapshot_date == date(2024, 9, 30)
    assert window.current_start.date() == date(2024, 10, 1)
    assert window.label == 'ноябрь 2024'
    assert window.data_label == 'октябрь 2024'


@pytest.mark.parametrize('month,current,previous', [
    ('2025-01-01', date(2024,12,31), date(2024,11,30)),
    ('2024-03-01', date(2024,2,29), date(2024,1,31)),
    ('2025-03-01', date(2025,2,28), date(2025,1,31))])
def test_calendar_edges(month,current,previous):
    window = report_window(month)
    assert window.snapshot_date == current
    assert window.previous_snapshot_date == previous


def test_strict_end_day_and_latest_on_that_day(factory):
    audience(factory, 'telegram', 'selectel_IR', 100, '2024-09-30T12:00:00Z')
    audience(factory, 'telegram', 'selectel_IR', 110, '2024-10-30T12:00:00Z')
    window = report_window('2024-11-01')
    frame, _ = audience_report(factory, window, ['telegram'])
    row = frame.loc[(frame.company_id=='selectel') & (frame.platform=='telegram')].iloc[0]
    assert pd.isna(row.followers) and pd.isna(row.delta)
    audience(factory, 'telegram', 'selectel_IR', 120, '2024-10-31T10:00:00Z')
    audience(factory, 'telegram', 'selectel_IR', 125, '2024-10-31T20:30:00Z')
    audience(factory, 'telegram', 'selectel_IR', 999, '2024-10-31T21:00:00Z')  # Moscow Nov 1
    frame, details = audience_report(factory, window, ['telegram'])
    row = frame.loc[(frame.company_id=='selectel') & (frame.platform=='telegram')].iloc[0]
    assert row.followers == 125 and row.delta == 25 and row.delta_pct == 25
    assert details.loc[details.company_id=='selectel', 'observed_at'].iloc[0].startswith('2024-10-31T20:30')


def test_total_requires_all_provided_accounts_not_absent_channels(factory):
    window = report_window('2024-11-01')
    audience(factory, 'telegram', 'selectel_IR', 100, '2024-09-30T12:00:00Z')
    audience(factory, 'telegram', 'selectel_IR', 120, '2024-10-31T12:00:00Z')
    frame, _ = audience_report(factory, window)
    assert pd.isna(frame.loc[(frame.company_id=='selectel') & (frame.platform=='total'), 'followers'].iloc[0])
    audience(factory, 'pulse', 'Selectel_Official', 900, '2024-09-30T12:00:00Z')
    audience(factory, 'pulse', 'Selectel_Official', 980, '2024-10-31T12:00:00Z')
    frame, _ = audience_report(factory, window)
    row = frame.loc[(frame.company_id=='selectel') & (frame.platform=='total')].iloc[0]
    assert row.followers == 1100 and row.delta == 100 and row.delta_pct == 10
    audience(factory, 'pulse', 'Astra_Group', 50, '2024-10-31T12:00:00Z')
    frame, _ = audience_report(factory, window)
    astra_total = frame.loc[(frame.company_id=='astra') & (frame.platform=='total')].iloc[0]
    assert astra_total.followers == 50  # Telegram not provided, not a missing measured account.
    assert pd.isna(astra_total.delta_pct)


def test_zero_previous_has_absolute_delta_without_percent(factory):
    audience(factory, 'telegram', 'selectel_IR', 0, '2024-09-30T12:00:00Z')
    audience(factory, 'telegram', 'selectel_IR', 20, '2024-10-31T12:00:00Z')
    frame, _ = audience_report(factory, report_window('2024-11-01'), ['telegram'])
    row = frame.loc[(frame.company_id=='selectel') & (frame.platform=='telegram')].iloc[0]
    assert row.delta == 20 and pd.isna(row.delta_pct)


def test_posts_do_not_leak_later_metrics_or_adjacent_months(factory):
    post(factory)
    post(factory, measured='2024-11-01T00:00:00Z', reactions=999)
    post(factory, post_id='sep', published='2024-09-30T20:59:59Z')
    post(factory, post_id='oct-start', published='2024-09-30T21:00:00Z')
    post(factory, post_id='nov', published='2024-10-31T21:00:00Z', measured='2024-11-01T00:00:00Z')
    post(factory, post_id='external', kind='external', account_id='')
    window = report_window('2024-11-01')
    frame = monthly_posts(factory, window, ['telegram'], ['selectel'])
    assert set(frame.post_id) == {'1', 'oct-start'}
    assert frame.loc[frame.post_id=='1', 'reactions'].iloc[0] == 10
    activity = monthly_activity(factory, window, ['telegram'], ['selectel']).iloc[0]
    assert activity.current_posts == 2 and activity.previous_posts == 1


def test_key_post_requires_end_day_measurement_and_single_platform(factory):
    post(factory, post_id='stale', measured='2024-10-30T12:00:00Z', reactions=999)
    post(factory, post_id='good', reactions=10)
    post(factory, post_id='young', published='2024-10-31T10:00:00Z', reactions=100)
    post(factory, post_id='pulse', platform='pulse', account_id='Selectel_Official', reactions=2000)
    frame = monthly_posts(factory, report_window('2024-11-01'), ['telegram','pulse'], ['selectel'])
    selected = key_post(frame, 'selectel', 'telegram', 'reactions', 7)
    assert selected.post_id == 'good'
    assert key_post(frame, 'selectel', 'vk') is None


def test_html_escapes_text_shows_missing_and_partial_period(factory):
    window = report_window('2024-11-01')
    a, details = audience_report(factory, window)
    posts = monthly_posts(factory, window, ['telegram'], ['selectel'])
    activity = monthly_activity(factory, window, ['telegram'], ['selectel'])
    content = fragment(window,a,details,posts,{'selectel':'<script>alert(1)</script>', **{r.company_id:r.company for r in a.itertuples() if r.company_id!='selectel'}},
                       ['pulse','telegram'],activity,'telegram','reactions',0,'demo',pd.Timestamp('2024-10-29',tz='Europe/Moscow'),now='2024-10-29T00:00:00Z')
    assert '<script>' not in content
    assert '&lt;script&gt;' in content
    assert 'DEMO' in content and 'предварительный' in content
    assert 'Недостаточно данных' in content
    assert '31.10.2024' in content and '30.09.2024' in content
    assert '<!doctype html>' in document(content)
    assert competitors(a).empty


def test_monthly_demo_is_idempotent_and_has_exact_snapshots(factory):
    ensure_monthly_demo(factory)
    with factory() as session:
        count = session.scalar(select(func.count()).select_from(Post))
    ensure_monthly_demo(factory)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Post)) == count == 45
    window = report_window(pd.Timestamp.now(tz='Europe/Moscow'))
    a, _ = audience_report(factory, window)
    assert a.loc[(a.company_id=='selectel') & (a.platform=='total'), 'followers'].notna().all()
    assert len(competitors(a)) == 3


def test_brand_font_and_copy_values(factory):
    from report_view import audience_matrix, CSS
    from clipboard_view import clipboard_html
    audience(factory,'telegram','selectel_IR',100,'2024-09-30T10:00:00Z')
    audience(factory,'telegram','selectel_IR',125,'2024-10-31T10:00:00Z')
    a,_ = audience_report(factory,report_window('2024-11-01'),['telegram'])
    names = dict(zip(a.company_id,a.company))
    matrix = audience_matrix(a,['telegram'],names)
    assert matrix.loc[0,'Selectel'] == '125 (+25,0%)'
    assert matrix.loc[0,'Группа Астра'] == '—'
    assert matrix.loc[1,'Selectel'] == '125 (+25,0%)'
    assert {'#EB4247','#092433','#E3E6E7'} <= {c for c in ['#EB4247','#092433','#E3E6E7'] if c in CSS}
    assert 'font-family:Manrope' in CSS
    assert 'data:font/woff2;base64,' in CSS
    html = clipboard_html(matrix)
    assert 'Скопировать всю таблицу' in html
    assert 'text/plain' in html and 'text/html' in html
    assert 'plain.select()' in html
