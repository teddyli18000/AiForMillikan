import json
from pathlib import Path

import cv2
import numpy as np

from millikan_ai.config import load_config, save_config
from millikan_ai.pipeline import run_pipeline


def _fast_config() -> dict:
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 0
    config["elementary"]["measurement_mc_samples"] = 0
    config["elementary"]["null_simulation_samples"] = 0
    config["segment"]["velocity_bootstrap_samples_quick"] = 0
    return config


def _make_two_platform_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (360, 260))
    drop_y = 45.0
    for idx in range(180):
        frame = np.zeros((260, 360, 3), dtype=np.uint8)
        for grid_y in [25, 65, 105, 145, 185, 225]:
            cv2.line(frame, (35, grid_y), (260, grid_y), (255, 255, 255), 2)
        cv2.putText(frame, "100V" if idx < 90 else "250V", (235, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (230, 230, 230), 2, cv2.LINE_AA)
        drop_y += 0.30 if idx < 90 else 0.12
        cv2.circle(frame, (115, int(drop_y)), 4, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def test_analyze_generates_markdown_report_with_real_q(tmp_path: Path):
    video = tmp_path / "two_platform.mp4"
    _make_two_platform_video(video)
    config = _fast_config()
    config["roi"]["microscope_roi"] = [25, 15, 250, 235]
    config["roi"]["voltage_roi"] = [225, 0, 120, 55]
    config["manual_platforms"] = [
        {"platform_id": "P001", "start_frame": 0, "end_frame": 89, "start_time_s": 0.0, "end_time_s": 2.966, "voltage_V": 100.0, "voltage_confidence": 1.0, "source": "manual"},
        {"platform_id": "P002", "start_frame": 90, "end_frame": 179, "start_time_s": 3.0, "end_time_s": 5.966, "voltage_V": 250.0, "voltage_confidence": 1.0, "source": "manual"},
    ]
    config["segment"]["stable_min_duration_s"] = 1.0
    config["segment"]["min_valid_points"] = 20
    config["segment"]["min_fit_r2"] = 0.75
    config["segment"]["min_motion_displacement_px"] = 4
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    run_dir = run_pipeline(video, config_path, tmp_path / "run")
    report = (run_dir / "analysis_report.md").read_text(encoding="utf-8")
    drop = json.loads((run_dir / "drop_results.json").read_text(encoding="utf-8"))
    elementary = json.loads((run_dir / "elementary_charge_result.json").read_text(encoding="utf-8"))

    assert (run_dir / "analysis_report.md").exists()
    assert drop["valid"] is True
    assert drop["result"]["charge_abs_C"] > 0
    assert "运行状态：" in report
    assert "单颗油滴结果" in report
    assert "距离标定" in report
    assert "时间计算" in report
    assert "insufficient_independent_drops" in report
    assert "视频是否合法" not in report
    assert elementary["flags"] == ["insufficient_independent_drops"]


def test_single_platform_report_is_invalid(tmp_path: Path):
    video = tmp_path / "single_platform.mp4"
    _make_two_platform_video(video)
    config = _fast_config()
    config["roi"]["microscope_roi"] = [25, 15, 250, 235]
    config["manual_platforms"] = [
        {"platform_id": "P001", "start_frame": 0, "end_frame": 179, "start_time_s": 0.0, "end_time_s": 5.966, "voltage_V": 100.0, "voltage_confidence": 1.0, "source": "manual"},
    ]
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    run_dir = run_pipeline(video, config_path, tmp_path / "run")
    report = (run_dir / "analysis_report.md").read_text(encoding="utf-8")
    drop = json.loads((run_dir / "drop_results.json").read_text(encoding="utf-8"))
    validity = json.loads((run_dir / "validity_report.json").read_text(encoding="utf-8"))

    assert drop["valid"] is False
    assert "insufficient_platforms" in report
    assert "运行状态：FAILED" in report
    assert validity["overall_valid_for_q"] is False
    assert "enough_voltage_platforms" in validity["blocking_failed_checks"] or "distinct_voltage_values" in validity["blocking_failed_checks"]
