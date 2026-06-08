import json
from pathlib import Path

import cv2
import numpy as np

from millikan_ai.api import AnalysisRequest, ManualPlatformInput, analyze_video, manual_platform_rows, parse_manual_platform_spec, prepare_analysis_config
from millikan_ai.api import prepare_auto_platform_config
from millikan_ai.config import load_config, save_config
from tests.test_algorithms import _make_voltage_change_video


def _make_synthetic_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (30, y), (230, y), (255, 255, 255), 2)
        cv2.circle(frame, (90, int(50 + idx * 0.35)), 4, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def test_manual_platform_api_builds_schema_rows():
    platform = parse_manual_platform_spec("30:90:175", source="manual_ui")
    rows = manual_platform_rows([platform], fps=30.0, frame_count=120)

    assert rows[0]["platform_id"] == "P001"
    assert rows[0]["start_time_s"] == 1.0
    assert rows[0]["end_time_s"] == 3.0
    assert rows[0]["voltage_V"] == 175.0
    assert rows[0]["source"] == "manual_ui"


def test_prepare_analysis_config_writes_manual_platforms(tmp_path: Path):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)
    config = load_config("configs/default.yaml")
    config["project"]["run_root"] = str(tmp_path / "runs")
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    prepared = prepare_analysis_config(video, config_path, [ManualPlatformInput(0, 59, 0.0), ManualPlatformInput(60, 119, 200.0)])
    prepared_config = load_config(prepared)

    assert prepared.name == "synthetic_manual_platforms.yaml"
    assert len(prepared_config["manual_platforms"]) == 2
    assert prepared_config["manual_platforms"][0]["source"] == "manual_ui"


def test_prepare_auto_platform_config_binds_user_voltage_values(tmp_path: Path):
    video = tmp_path / "auto_platform.mp4"
    _make_voltage_change_video(video)
    config = load_config("configs/default.yaml")
    config["project"]["run_root"] = str(tmp_path / "runs")
    config["auto_platform_detection"]["sample_stride_frames"] = 3
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    prepared = prepare_auto_platform_config(video, config_path, expected_platform_count=3, platform_values=[0.0, 175.0, 248.0])
    prepared_config = load_config(prepared)

    assert prepared.name == "auto_platform_auto_platforms.yaml"
    assert len(prepared_config["auto_platform_suggestions"]) == 3
    assert len(prepared_config["manual_platforms"]) == 3
    assert [row["voltage_V"] for row in prepared_config["manual_platforms"]] == [0.0, 175.0, 248.0]
    assert prepared_config["manual_platforms"][0]["source"] == "auto_boundary_manual_voltage"


def test_analyze_video_returns_manifest_for_frontend(tmp_path: Path):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)
    config = load_config("configs/default.yaml")
    config["project"]["run_root"] = str(tmp_path / "runs")
    config["roi"]["microscope_roi"] = [20, 20, 240, 200]
    config["segment"]["stable_min_duration_s"] = 0.5
    config["segment"]["transient_drop_s"] = 0.1
    config["segment"]["min_valid_points"] = 10
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    result = analyze_video(
        AnalysisRequest(
            video_path=video,
            config_path=config_path,
            run_dir=tmp_path / "run",
            manual_platforms=(ManualPlatformInput(0, 59, 0.0), ManualPlatformInput(60, 119, 200.0)),
        )
    )

    assert result.validation_errors == []
    assert result.manifest["schema_version"] == 1
    assert result.manifest["files"]["run_manifest_json"].endswith("run_manifest.json")
    assert json.loads((result.run_dir / "run_manifest.json").read_text(encoding="utf-8"))["run_dir"] == str(result.run_dir)
