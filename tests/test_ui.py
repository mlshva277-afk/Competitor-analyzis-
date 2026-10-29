from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ['Ежемесячный отчёт', 'Обзор', 'Selectel vs конкуренты', 'Публикации', 'Темы и тренды', 'Реакции/комментарии', 'Источники и качество данных']


@pytest.mark.parametrize('demo', [False, True])
def test_all_pages(tmp_path, monkeypatch, demo):
    monkeypatch.setenv('ISI_DB_PATH', str(tmp_path/'real.sqlite'))
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
    assert not app.exception
    if demo:
        app.sidebar.radio[0].set_value('Демо (demo)').run()
        assert not app.exception
    for page in PAGES:
        app.sidebar.radio[1].set_value(page).run()
        assert not app.exception, f'{page}: {app.exception}'
    # Both a populated and an absent platform must render safely.
    app.sidebar.selectbox[0].set_value('telegram').run()
    assert not app.exception
    app.sidebar.radio[1].set_value('Selectel vs конкуренты').run()
    assert not app.exception
    app.sidebar.selectbox[0].set_value('vk').run()
    assert not app.exception
    app.sidebar.radio[2].set_value('Внешние упоминания').run()
    assert not app.exception
    for page in PAGES:
        app.sidebar.radio[1].set_value(page).run()
        assert not app.exception
    app.sidebar.multiselect[0].set_value([]).run()
    for page in PAGES:
        app.sidebar.radio[1].set_value(page).run()
        assert not app.exception
