from pathlib import Path

import pandas as pd

from millikan_ai.config import load_config
from millikan_ai.outputs.schemas import PLATFORMS_COLUMNS, validate_columns
from millikan_ai.video.reader import inspect_video
from millikan_ai.video.reader import save_diagnostic_frame


def test_default_config_loads():
    config = load_config("configs/default.yaml")
    assert config["physics"]["plate_distance_m"] == 0.005
    assert config["segment"]["stable_min_duration_s"] > 0


def test_default_config_is_manual_platform_first_without_ocr():
    config = load_config("configs/default.yaml")
    assert "ocr" not in config


def test_raw_video_inspect_reads_metadata():
    meta = inspect_video("raw_data/single.mp4")
    assert meta.readable is True
    assert meta.width == 1280
    assert meta.height == 720
    assert meta.frame_count > 0
    assert meta.fps > 0


def test_save_diagnostic_frame_falls_back_for_unknown_suffix(tmp_path: Path):
    target = save_diagnostic_frame("raw_data/single.mp4", tmp_path / "first_frame.jp")
    assert target.name == "first_frame.jpg"
    assert target.exists()


def test_schema_validator_reports_missing_columns(tmp_path: Path):
    path = tmp_path / "platforms.csv"
    pd.DataFrame({"platform_id": ["P001"]}).to_csv(path, index=False)
    errors = validate_columns(path, PLATFORMS_COLUMNS)
    assert "platforms.csv missing column: start_frame" in errors
