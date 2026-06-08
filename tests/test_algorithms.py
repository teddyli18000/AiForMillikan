import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import detect_horizontal_grid_lines, detect_vertical_grid_lines
from millikan_ai.config import load_config
from millikan_ai.elementary.estimate import estimate_elementary_charge
from millikan_ai.physics.charge import compute_drop_result
from millikan_ai.segments.fitting import fit_line, fit_track_segments, select_stable_window
from millikan_ai.segments.platforms import VoltageSample, segment_voltage_platforms
from millikan_ai.segments.voltage_change import detect_voltage_platform_changes


def test_detect_horizontal_grid_lines_on_synthetic_image():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    for y in [30, 70, 110, 150, 190]:
        cv2.line(image, (20, y), (300, y), (255, 255, 255), 2)
    lines = detect_horizontal_grid_lines(image)
    assert len(lines) == 5
    assert abs(lines[1] - 70) <= 2


def test_detect_vertical_grid_lines_on_synthetic_image():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    for x in [30, 90, 150, 210, 270]:
        cv2.line(image, (x, 20), (x, 220), (255, 255, 255), 2)
    lines = detect_vertical_grid_lines(image)
    assert len(lines) == 5
    assert abs(lines[-2] - 210) <= 2


def test_segment_voltage_platforms_groups_stable_values():
    samples = [
        VoltageSample(i * 10, i / 3, 100 if i < 6 else 180, 0.9, "manual_test")
        for i in range(12)
    ]
    platforms = segment_voltage_platforms(samples, voltage_tolerance_V=5, min_duration_s=1.0)
    assert list(platforms["voltage_V"]) == [100, 180]


def _make_voltage_change_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (360, 240))
    for idx in range(150):
        frame = np.zeros((240, 360, 3), dtype=np.uint8)
        shift_x = int(round(2 * np.sin(idx / 17)))
        shift_y = int(round(1 * np.cos(idx / 19)))
        x0, y0 = 190 + shift_x, 12 + shift_y
        cv2.rectangle(frame, (x0, y0), (x0 + 145, y0 + 78), (210, 210, 230), 1)
        cv2.line(frame, (x0, y0 + 52), (x0 + 120, y0 + 52), (210, 210, 230), 1)
        if idx < 50:
            text = "+000V"
        elif idx < 58:
            text = "+090V" if idx % 2 else "+175V"
        elif idx < 105:
            text = "+175V"
        elif idx < 114:
            text = "+200V" if idx % 2 else "+248V"
        else:
            text = "+248V"
        cv2.putText(frame, text, (x0 + 12, y0 + 38), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 255), 2)
        cv2.putText(frame, f"{idx / 30:04.1f}S", (x0 + 28, y0 + 74), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 255), 1)
        writer.write(frame)
    writer.release()


def test_detect_voltage_platform_changes_with_jitter_and_unstable_transitions(tmp_path):
    video = tmp_path / "voltage_changes.mp4"
    _make_voltage_change_video(video)
    config = load_config("configs/default.yaml")
    config["auto_platform_detection"]["sample_stride_frames"] = 3
    config["auto_platform_detection"]["min_platform_duration_s"] = 0.8
    config["auto_platform_detection"]["transition_padding_s"] = 0.1

    suggestions, samples, diagnostics = detect_voltage_platform_changes(video, expected_platform_count=3, config=config)

    assert diagnostics["detected_platform_count"] == 3
    assert diagnostics["roi"]["w"] > 0
    assert len(samples) > 20
    assert list(suggestions["platform_id"]) == ["P001", "P002", "P003"]
    assert suggestions.iloc[0]["end_frame"] < 55
    assert suggestions.iloc[1]["start_frame"] > 50
    assert suggestions.iloc[1]["end_frame"] < 110
    assert suggestions.iloc[2]["start_frame"] > 105
    assert (suggestions["source"] == "auto_change_detector").all()


def test_fit_line_recovers_velocity():
    t = np.arange(0, 5, 0.1)
    y = 4.0 * t + 7.0
    fit = fit_line(t, y)
    assert abs(fit["slope"] - 4.0) < 1e-9
    assert fit["r2"] > 0.999


def test_select_stable_window_skips_noisy_platform_prefix():
    t = np.arange(0, 5, 0.1)
    y = 2.0 * t + 4.0
    y[:20] += np.sin(np.arange(20)) * 8
    frame = pd.DataFrame({"time_s": t, "y_px": y, "x_px": np.zeros_like(t), "is_valid_detection": True})
    stable = select_stable_window(frame, min_duration_s=1.5, min_points=15)
    fit = fit_line(stable["time_s"].to_numpy(float), stable["y_px"].to_numpy(float))
    assert stable["time_s"].min() >= 1.0
    assert fit["r2"] > 0.95


def test_fit_track_segments_preserves_track_id_for_transient_cropped_short_platform():
    config = load_config("configs/default.yaml")
    config["segment"]["transient_drop_s"] = 0.5
    config["segment"]["stable_min_duration_s"] = 1.0
    config["segment"]["min_valid_points"] = 5
    track = pd.DataFrame(
        {
            "video_id": ["synthetic"] * 10,
            "track_id": ["candidate_001"] * 10,
            "time_s": np.arange(10) / 30.0,
            "x_px": np.full(10, 50.0),
            "y_px": np.linspace(100, 105, 10),
            "is_valid_detection": True,
        }
    )
    platforms = pd.DataFrame(
        [
            {
                "platform_id": "P001",
                "start_time_s": 0.0,
                "end_time_s": 0.2,
                "voltage_V": 100.0,
            }
        ]
    )

    segments = fit_track_segments(track, platforms, scale_y_m_per_px=1e-6, config=config)

    assert segments.iloc[0]["track_id"] == "candidate_001"
    assert segments.iloc[0]["video_id"] == "synthetic"
    assert "too_short" in segments.iloc[0]["flags"]


def test_compute_drop_result_for_synthetic_segments():
    config = load_config("configs/default.yaml")
    rows = []
    for voltage, velocity in [(0.0, 2.0e-4), (200.0, 1.0e-4), (400.0, -0.5e-4)]:
        rows.append(
            {
                "platform_id": f"P{len(rows)+1:03d}",
                "voltage_V": voltage,
                "vy_m_s": velocity,
                "stable": True,
            }
        )
    result = compute_drop_result(pd.DataFrame(rows), config)
    assert result["result"]["radius_m"] > 0
    assert result["result"]["charge_abs_C"] > 0


def test_elementary_charge_estimator_on_integer_multiples():
    config = load_config("configs/default.yaml")
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e, "sigma_charge_C": 0.04e-19}}
        for i, n in enumerate([2, 3, 5, 7, 8])
    ]
    result = estimate_elementary_charge(drops, config)
    assert result["valid"] is True
    assert abs(result["elementary_charge"]["e_hat_C"] - e) < 0.03e-19
