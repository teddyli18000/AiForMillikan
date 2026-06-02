import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import detect_horizontal_grid_lines
from millikan_ai.config import load_config
from millikan_ai.elementary.estimate import estimate_elementary_charge
from millikan_ai.ocr.voltage import find_voltage_roi, read_voltage_from_image
from millikan_ai.ocr.voltage import _first_text_line, preprocess_voltage_roi
from millikan_ai.ocr.voltage import _match_seven_segment_char
from millikan_ai.physics.charge import compute_drop_result
from millikan_ai.segments.fitting import fit_line, select_stable_window
from millikan_ai.segments.platforms import VoltageSample, segment_voltage_platforms


def test_detect_horizontal_grid_lines_on_synthetic_image():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    for y in [30, 70, 110, 150, 190]:
        cv2.line(image, (20, y), (300, y), (255, 255, 255), 2)
    lines = detect_horizontal_grid_lines(image)
    assert len(lines) == 5
    assert abs(lines[1] - 70) <= 2


def test_template_voltage_ocr_on_synthetic_digits():
    image = np.zeros((80, 220, 3), dtype=np.uint8)
    cv2.putText(image, "+100V", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (210, 210, 210), 2, cv2.LINE_AA)
    reading = read_voltage_from_image(image)
    assert reading.voltage_V == 100
    assert reading.confidence > 0.2


def test_voltage_ocr_rejects_unmarked_numeric_noise():
    image = np.zeros((80, 180, 3), dtype=np.uint8)
    cv2.putText(image, "855", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (210, 210, 210), 2, cv2.LINE_AA)
    reading = read_voltage_from_image(image)
    assert reading.voltage_V is None


def test_seven_segment_digit_classifier():
    image = np.zeros((42, 28), dtype=np.uint8)
    cv2.line(image, (6, 3), (22, 3), 255, 2)
    cv2.line(image, (24, 6), (24, 18), 255, 2)
    cv2.line(image, (24, 23), (24, 36), 255, 2)
    char, confidence = _match_seven_segment_char(image)
    assert char == "7"
    assert confidence >= 0.6


def test_voltage_ocr_line_selection_skips_top_noise():
    image = np.zeros((96, 408, 3), dtype=np.uint8)
    cv2.line(image, (5, 8), (170, 8), (210, 210, 210), 1)
    cv2.putText(image, "+100V", (120, 54), cv2.FONT_HERSHEY_SIMPLEX, 1.25, (210, 210, 210), 2, cv2.LINE_AA)
    binary = preprocess_voltage_roi(image)
    line = _first_text_line(binary)
    assert line.shape[0] > 40


def test_find_voltage_roi_uses_text_line_not_fixed_position():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    for x in [560, 760, 980]:
        cv2.line(image, (x, 40), (x, 680), (150, 120, 255), 2)
    for y in [110, 230, 350, 470, 590]:
        cv2.line(image, (250, y), (1000, y), (150, 120, 255), 2)
    cv2.putText(image, "+240V", (820, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (180, 160, 255), 2, cv2.LINE_AA)
    roi = find_voltage_roi(image)
    assert roi.x < 820
    assert roi.x + roi.w > 940
    assert roi.y < 80


def test_segment_voltage_platforms_groups_stable_values():
    samples = [
        VoltageSample(i * 10, i / 3, 100 if i < 6 else 180, 0.9, "template_ocr")
        for i in range(12)
    ]
    platforms = segment_voltage_platforms(samples, voltage_tolerance_V=5, min_duration_s=1.0)
    assert list(platforms["voltage_V"]) == [100, 180]


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
