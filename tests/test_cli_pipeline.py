import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import yaml

from millikan_ai.cli.__main__ import _parse_platform_spec
from millikan_ai.config import load_config, save_config
from millikan_ai.pipeline import run_pipeline, validate_run


def _make_synthetic_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (30, y), (230, y), (255, 255, 255), 2)
        x = 90
        y = 50 + idx * 0.35
        cv2.circle(frame, (int(x), int(y)), 4, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def test_pipeline_with_manual_platforms_on_synthetic_video(tmp_path: Path):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)
    config = load_config("configs/default.yaml")
    config["roi"]["microscope_roi"] = [20, 20, 240, 200]
    config["manual_platforms"] = [
        {"platform_id": "P001", "start_frame": 0, "end_frame": 59, "start_time_s": 0.0, "end_time_s": 1.97, "voltage_V": 0.0, "voltage_confidence": 1.0, "source": "manual"},
        {"platform_id": "P002", "start_frame": 60, "end_frame": 119, "start_time_s": 2.0, "end_time_s": 3.97, "voltage_V": 200.0, "voltage_confidence": 1.0, "source": "manual"},
    ]
    config["segment"]["stable_min_duration_s"] = 0.5
    config["segment"]["transient_drop_s"] = 0.1
    config["segment"]["min_valid_points"] = 10
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)
    run_dir = run_pipeline(video, config_path, tmp_path / "run")
    errors = validate_run(run_dir, config_path)
    assert errors == []
    diagnostics = json.loads((run_dir / "diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["track_rows"] > 0
    assert (run_dir / "overlay_best_track.mp4").exists()


def test_cli_help_runs():
    result = subprocess.run(
        [".venv/Scripts/python", "-m", "millikan_ai.cli", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "inspect" in result.stdout


def test_parse_cli_platform_spec_uses_frame_time():
    platform = _parse_platform_spec("30:90:175", fps=30.0, index=2)
    assert platform["platform_id"] == "P002"
    assert platform["start_time_s"] == 1.0
    assert platform["end_time_s"] == 3.0
    assert platform["voltage_V"] == 175.0
    assert platform["source"] == "manual_cli"
