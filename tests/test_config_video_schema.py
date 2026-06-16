from pathlib import Path

import pandas as pd

from millikan_ai.config import load_config
from millikan_ai.outputs.schemas import PLATFORMS_COLUMNS, validate_columns
from millikan_ai.video.reader import inspect_video
from millikan_ai.video.reader import save_diagnostic_frame


def _raw_smoke_video() -> Path:
    for candidate in [Path("raw_data/single.mp4"), Path("raw_data/1.mp4")]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("expected raw_data/single.mp4 or raw_data/1.mp4 for raw smoke tests")


def test_default_config_loads():
    config = load_config("configs/default.yaml")
    assert config["physics"]["plate_distance_m"] == 0.005
    assert config["segment"]["boundary_guard_frames"] == 0
    assert "transient_drop_s" not in config["segment"]
    assert "voltage_sign" not in config["physics"]
    assert "radius_tolerance_m" not in config["physics"]
    assert "max_radius_iterations" not in config["physics"]
    assert config["physics"]["random_mc_samples"] == 1000
    assert config["physics"]["systematic_mc_samples"] == 0
    assert "spatial_scale_rel" in config["physics"]["systematic_uncertainty"]
    assert config["viscosity"]["source"] == "temperature"
    assert config["elementary"]["min_drops_for_estimation"] == 3
    assert "e_search_min_C" not in config["elementary"]
    assert "e_search_max_C" not in config["elementary"]
    assert config["elementary"]["e_bootstrap_samples"] == 1000


def test_default_config_is_manual_platform_first_without_ocr():
    config = load_config("configs/default.yaml")
    assert "ocr" not in config


def test_raw_video_inspect_reads_metadata():
    meta = inspect_video(_raw_smoke_video())
    assert meta.readable is True
    assert meta.width > 0
    assert meta.height > 0
    assert meta.frame_count > 0
    assert meta.fps > 0


def test_save_diagnostic_frame_falls_back_for_unknown_suffix(tmp_path: Path):
    target = save_diagnostic_frame(_raw_smoke_video(), tmp_path / "first_frame.jp")
    assert target.name == "first_frame.jpg"
    assert target.exists()


def test_schema_validator_reports_missing_columns(tmp_path: Path):
    path = tmp_path / "platforms.csv"
    pd.DataFrame({"platform_id": ["P001"]}).to_csv(path, index=False)
    errors = validate_columns(path, PLATFORMS_COLUMNS)
    assert "platforms.csv missing column: start_frame" in errors
