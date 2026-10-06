"""Actual Streamlit interactions; synthetic series only live in temporary test roots."""

from pathlib import Path
import shutil

import pandas as pd
from streamlit.testing.v1 import AppTest
from series_manifest import load_manifest, manifest_from_dict, save_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_original_case_study_renders_and_preserves_wembanyama_result():
    app = AppTest.from_file(str(ROOT / "app_v1.py")).run(timeout=30)
    assert not app.exception
    assert not app.error
    assert (
        app.selectbox(key="player_2026_okc_sas_sample").value == "SAS|Victor Wembanyama"
    )
    largest = [m for m in app.metric if m.label == "Largest Adjustment"]
    assert largest[0].value == "0.620"
    assert any("sample" in info.value.lower() for info in app.info)
    player = app.selectbox(key="player_2026_okc_sas_sample")
    player.set_value("OKC|Shai Gilgeous-Alexander").run(timeout=30)
    assert not app.exception


def test_multi_series_and_one_game_state(tmp_path):
    (tmp_path / "data").mkdir()
    shutil.copy(
        ROOT / "data/OKC Spurs Matchup Data.csv", tmp_path / "data/reference.csv"
    )
    base = load_manifest(ROOT / "series/2026_okc_sas_sample.yml").to_dict()
    base["source_csv"] = "data/reference.csv"
    save_manifest(manifest_from_dict(base), tmp_path / "series/sample.yml")
    second = base.copy()
    second.update(
        series_id="fixture_bos_mia",
        team_a="BOS",
        team_b="MIA",
        default_player=None,
        source_csv="data/second.csv",
        games=[base["games"][0]],
    )
    data = pd.read_csv(tmp_path / "data/reference.csv")
    data = data[data.Game == 1].copy()
    data["OFF Team"] = data["OFF Team"].replace({"OKC": "BOS", "SAS": "MIA"})
    data["DEF Team"] = data["DEF Team"].replace({"OKC": "BOS", "SAS": "MIA"})
    data.to_csv(tmp_path / "data/second.csv", index=False)
    save_manifest(manifest_from_dict(second), tmp_path / "series/second.yml")
    code = (
        (ROOT / "app_v1.py")
        .read_text()
        .replace(
            "PROJECT_ROOT = Path(__file__).resolve().parent",
            f"PROJECT_ROOT = Path({str(tmp_path)!r})",
        )
    )
    app = AppTest.from_string(code).run(timeout=30)
    assert not app.exception
    app.sidebar.selectbox[2].set_value("fixture_bos_mia").run(timeout=30)
    assert not app.exception and not app.error
    assert app.selectbox(key="player_fixture_bos_mia").value.startswith(
        ("BOS|", "MIA|")
    )
    assert not [m for m in app.metric if m.label == "Largest Adjustment"]
