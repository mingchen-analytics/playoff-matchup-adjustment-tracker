"""The research dashboard renders, defaults to the motivating case, and switches series."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_research_app_defaults_to_the_wembanyama_case():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=60)
    assert not app.exception and not app.error
    assert app.sidebar.selectbox[1].value == 1641705  # Victor Wembanyama
    assert app.selectbox(key="transition_2026_okc_sas_api_20261005").value == "G1 → G2"
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Total change (TVD)"] == "0.648"
    assert metrics["Assignment"] == "0.333"


def test_research_app_switches_series_and_players():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=60)
    app.sidebar.selectbox[0].set_value("2025_okc_ind_api_20261005").run(timeout=60)
    assert not app.exception and not app.error
    app.sidebar.checkbox[0].uncheck().run(timeout=60)
    assert not app.exception and len(app.sidebar.selectbox[1].options) > 4
