from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from millikan_ai.normal.config import normal_config
from millikan_ai.normal.inversion import run_weighted_integer_inversion
from millikan_ai.normal.session import save_measurement
from millikan_ai.normal.tracking import locate_features_near_position, track_single_drop_frames
from millikan_ai.normal.voltage import VoltageSample, merge_change_operations


def test_normal_namespace_does_not_import_experimental_tracking_physics_segments():
    root = Path("src/millikan_ai/normal")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = [
        "millikan_ai.tracking",
        "millikan_ai.segments",
        "millikan_ai.pipeline",
        "millikan_ai.physics",
        "millikan_ai.quality",
    ]
    for name in forbidden:
        assert name not in text


def test_trackpy_local_detection_selects_real_feature():
    gray = np.zeros((90, 120), dtype=np.uint8)
    cv2.circle(gray, (50, 44), 4, 255, -1)
    cv2.circle(gray, (82, 44), 4, 220, -1)
    cfg = normal_config()["tracking"] | {"diameter": 7, "minmass": 20, "local_topn": 5}

    features = locate_features_near_position(gray, np.array([52.0, 44.0]), 35, cfg)

    assert len(features) >= 1
    assert float(np.hypot(features.iloc[0]["x"] - 50.0, features.iloc[0]["y"] - 44.0)) < 5.0


def test_frame_gap_velocity_after_missing_is_divided_by_gap(monkeypatch):
    frames = [np.zeros((40, 40, 3), dtype=np.uint8) for _ in range(4)]
    detections = {
        1: pd.DataFrame(),
        2: pd.DataFrame([{"x": 10.0, "y": 14.0, "mass": 100.0}]),
        3: pd.DataFrame([{"x": 10.0, "y": 16.0, "mass": 100.0}]),
    }
    calls = {"frame": 0}

    def fake_locate(_gray, _center, _radius, _config, _grid_mask=None):
        calls["frame"] += 1
        return detections[calls["frame"]]

    monkeypatch.setattr("millikan_ai.normal.tracking.locate_features_near_position", fake_locate)
    cfg = normal_config()["tracking"] | {"memory_frames": 3, "max_accept_distance_px": 100}

    track = track_single_drop_frames(frames, np.array([10.0, 10.0]), 0, cfg)

    row3 = track[track["source_frame"] == 3].iloc[0]
    assert row3["state"] == "tracking"
    assert abs(float(row3["pred_y"]) - 16.0) < 1e-6


def test_voltage_operation_merge_keeps_intermediate_235v_as_one_operation():
    cfg = normal_config()
    samples = [VoltageSample(i, i * 0.2, 0.0) for i in range(8)]
    samples += [
        VoltageSample(50, 10.0, 0.22),
        VoltageSample(55, 11.0, 0.18),
        VoltageSample(60, 12.0, 0.21),
    ]

    operations = merge_change_operations(samples, cfg)

    assert len(operations) == 1
    assert operations[0]["start_frame"] == 50
    assert operations[0]["end_frame"] == 60


def test_invalid_grid_measurement_saves_diagnostic_only(tmp_path: Path):
    payload = {
        "session_root": str(tmp_path / "session"),
        "run_root": str(tmp_path / "runs"),
        "video_path": "missing.mp4",
        "balance_voltage_V": 240,
        "target": {"target_frame": 0, "source_center": {"x": 10, "y": 10}, "source_video_box": {"x": 8, "y": 8, "width": 5, "height": 5}},
        "boundary": {"fall_start_frame": 1, "fall_end_frame": 10},
        "grid": {"valid": False},
    }

    result = save_measurement(payload)
    record = result["record"]

    assert record["status"] == "diagnostic"
    assert record["selected"] is False
    assert record["q"]["diagnostic_only"] is True
    assert record["recovery_suggestions"]


def test_weighted_inversion_requires_three_selected_valid_records():
    cfg = normal_config()
    records = [
        {"record_id": "a", "selected": True, "status": "valid", "q": {"valid": True, "charge_abs_C": 4 * 1.6e-19, "sigma_q_total_C": 0.05e-19}},
        {"record_id": "b", "selected": True, "status": "valid", "q": {"valid": True, "charge_abs_C": 5 * 1.6e-19, "sigma_q_total_C": 0.05e-19}},
    ]

    result = run_weighted_integer_inversion(records, cfg)

    assert result["reliable"] is False
    assert result["status"] == "insufficient_eligible_records"

