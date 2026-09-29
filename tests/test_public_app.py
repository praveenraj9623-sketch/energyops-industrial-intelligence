"""Streamlit startup and scoped-filter smoke test against committed files."""

from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_public_app_renders_and_filters_without_database():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert len(app.tabs) == 6
    assert any(metric.value == "959,636.71" for metric in app.metric)
    app.date_input[0].set_value((date(2018, 6, 1), date(2018, 6, 30))).run()
    assert not app.exception
    assert any(metric.value == "65,404.64" for metric in app.metric)
    assert any(metric.value == "2,880" for metric in app.metric)
    app.multiselect[0].set_value(["Light_Load"]).run()
    app.selectbox[0].set_value("Lagging power factor review").run()
    assert not app.exception
    assert any(metric.value == "959,636.71" for metric in app.metric)
