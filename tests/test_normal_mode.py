from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from millikan_ai.config import load_config
from millikan_ai.normal.elementary import estimate_both_algorithms, estimate_normal_integer_fit
from millikan_ai.normal.physics import FallVelocityFit, compute_balance_fall_q, detected_points_for_fit, fit_fall_velocity
from millikan_ai.normal.tracking import (
    NormalSingleDropTrackingConfig,
    missing_reacquired_events,
    track_normal_single_drop,
)
from millikan_ai.normal.voltage import merge_change_operations, normal_window_from_operations
from millikan_ai.physics.charge import eta_eff
from millikan_ai.physics.viscosity import resolve_air_viscosity
from millikan_ai.tracking.trackpy_core import SingleDropTrackingConfig


def _blank_frames(count: int) -> list[np.ndarray]:
    return [np.zeros((24, 24), dtype=np.uint8) for _ in range(count)]


def test_reacquired_velocity_is_normalized_by_frame_gap():
    detections = {
        1: (1.0, 0.0),
        5: (5.0, 0.0),
        6: (6.0, 0.0),
    }

    def locator(_gray, _center, _radius, _config, _grid_mask, frame_id):
        if frame_id not in detections:
            return pd.DataFrame()
        x, y = detections[frame_id]
        return pd.DataFrame([{"x": x, "y": y, "mass": 100.0}])

    track = track_normal_single_drop(
        _blank_frames(7),
        np.array([0.0, 0.0]),
        NormalSingleDropTrackingConfig(SingleDropTrackingConfig(single_memory=5, max_accept_distance=20)),
        feature_locator=locator,
    )

    reacquired = track.loc[track["frame"] == 5].iloc[0]
    after = track.loc[track["frame"] == 6].iloc[0]
    assert reacquired["status"] == "reacquired"
    assert reacquired["frame_gap_since_detection"] == 4
    assert reacquired["velocity_x_px_frame"] == pytest.approx(1.0)
    assert after["pred_x"] == pytest.approx(6.0)
    assert missing_reacquired_events(track)[0]["missing_frames"] == 3


def test_missing_prediction_points_do_not_enter_velocity_fit():
    track = pd.DataFrame(
        [
            {"source_frame": 0, "x": 10.0, "y": 10.0, "detected": True, "status": "tracking"},
            {"source_frame": 1, "x": 10.0, "y": 11.0, "detected": True, "status": "tracking"},
            {"source_frame": 2, "x": math.nan, "y": math.nan, "pred_x": 10.0, "pred_y": 50.0, "detected": False, "status": "missing"},
            {"source_frame": 5, "x": 10.0, "y": 15.0, "detected": True, "status": "reacquired"},
            {"source_frame": 6, "x": 10.0, "y": 16.0, "detected": True, "status": "tracking"},
        ]
    )

    points = detected_points_for_fit(track, 0, 6)
    fit = fit_fall_velocity(track, fps=1.0, scale_y_m_per_px=1.0, start_frame=0, end_frame=6, min_points=4)

    assert len(points) == 4
    assert set(points["source_frame"]) == {0, 1, 5, 6}
    assert fit.slope_y_px_s == pytest.approx(1.0)


def test_fit_window_caps_at_penultimate_grid_line():
    track = pd.DataFrame(
        [
            {"source_frame": frame, "x": 0.0, "y": float(y), "detected": True, "status": "tracking"}
            for frame, y in [(0, 10), (1, 20), (2, 30), (3, 40), (4, 105), (5, 115)]
        ]
    )

    fit = fit_fall_velocity(track, fps=1.0, scale_y_m_per_px=1.0e-6, start_frame=0, end_frame=5, penultimate_grid_y_px=100.0, min_points=4)

    assert fit.valid is True
    assert fit.end_frame == 3
    assert fit.num_points == 4


def test_voltage_changes_merge_recovery_bounce_and_suggest_window():
    changes = [
        {"frame_idx": 100, "sample_start_frame": 95, "sample_end_frame": 105, "score": 0.5},
        {"frame_idx": 300, "sample_start_frame": 295, "sample_end_frame": 305, "score": 0.4},
        {"frame_idx": 330, "sample_start_frame": 326, "sample_end_frame": 336, "score": 0.7},
    ]

    operations = merge_change_operations(changes, fps=30.0, merge_window_s=2.0)
    window = normal_window_from_operations(operations, frame_count=500, fps=30.0, stable_after_s=0.2)

    assert len(operations) == 2
    assert operations[1].start_frame == 295
    assert operations[1].end_frame == 336
    assert window["fall_start_frame"] == 111
    assert window["fall_end_frame"] == 294
    assert window["flags"] == []


def test_no_recovery_window_uses_video_end_until_tracking_can_refine():
    operations = merge_change_operations(
        [{"frame_idx": 100, "sample_start_frame": 95, "sample_end_frame": 105, "score": 0.5}],
        fps=30.0,
        merge_window_s=1.0,
    )

    window = normal_window_from_operations(operations, frame_count=220, fps=30.0, stable_after_s=0.1)

    assert window["fall_start_frame"] == 108
    assert window["fall_end_frame"] == 219
    assert "no_recovery_voltage_detected" in window["flags"]


def test_known_balance_fall_q_recovers_charge_with_uncertainty():
    config = load_config("configs/default.yaml")
    config["physics"]["random_mc_samples"] = 300
    constants = {**config["physics"], **resolve_air_viscosity(config)}
    radius = 0.75e-6
    charge = 4.8e-19
    eta = constants["air_viscosity_Pa_s"]
    pressure = constants["pressure_Pa"]
    b = constants["cunningham_b_Pa_m"]
    d = constants["plate_distance_m"]
    rho = constants["oil_density_kg_m3"]
    gravity = constants["gravity_m_s2"]
    eff = eta_eff(radius, eta, pressure, b)
    fall_velocity = (2 * rho * gravity * radius**2) / (9 * eff)
    gamma = charge / (6 * math.pi * eff * radius * d)
    balance_voltage = fall_velocity / gamma
    frames = np.arange(20, dtype=float)
    y = 100.0 + (fall_velocity / 1.0e-6) * frames + np.sin(frames) * 0.08
    track = pd.DataFrame(
        [{"source_frame": int(frame), "x": 0.0, "y": float(y_i), "detected": True, "status": "tracking"} for frame, y_i in zip(frames, y)]
    )

    fit = fit_fall_velocity(track, fps=1.0, scale_y_m_per_px=1.0e-6, start_frame=0, end_frame=19, min_points=5)
    q = compute_balance_fall_q(fit, balance_voltage_V=balance_voltage, config=config)

    assert fit.valid is True
    assert q["valid"] is True
    assert q["result"]["radius_m"] == pytest.approx(radius, rel=0.03)
    assert q["result"]["charge_abs_C"] == pytest.approx(charge, rel=0.04)
    assert q["result"]["sigma_q_total_C"] > 0
    assert "systematic_uncertainty_incomplete" in q["flags"]


def test_invalid_fall_fit_does_not_emit_usable_q():
    config = load_config("configs/default.yaml")
    fit = FallVelocityFit(
        valid=False,
        flags=["low_y_time_fit_r2"],
        start_frame=0,
        end_frame=20,
        num_points=21,
        slope_y_px_s=12.0,
        intercept_y_px=100.0,
        velocity_m_s=1.2e-4,
        sigma_velocity_m_s=2.0e-6,
        r2=0.5,
        rmse_px=8.0,
        first_half_slope_y_px_s=20.0,
        second_half_slope_y_px_s=2.0,
    )

    q = compute_balance_fall_q(fit, balance_voltage_V=100.0, config=config)

    assert q["valid"] is False
    assert q["usable_for_inversion"] is False
    assert q["result"] == {}
    assert "invalid_fall_velocity_fit" in q["flags"]
    assert "low_y_time_fit_r2" in q["flags"]


def _q_record(index: int, n: int, e_value: float = 1.602e-19, sigma: float = 0.03e-19) -> dict[str, object]:
    return {
        "record_id": f"q_{index:03d}",
        "q_C": n * e_value,
        "sigma_q_C": sigma,
        "usable_for_inversion": True,
        "selected": True,
    }


def test_normal_blind_inversion_recovers_known_spacing():
    records = [_q_record(index, n) for index, n in enumerate([2, 3, 5, 7], start=1)]

    result = estimate_normal_integer_fit(records, grid_points=500)

    assert result["valid"] is True
    assert result["e_hat_C"] == pytest.approx(1.602e-19, rel=0.01)
    assert [row["n_i"] for row in result["assignments"]] == [2, 3, 5, 7]


def test_normal_blind_inversion_rejects_common_divisor_assignments():
    records = [_q_record(index, n) for index, n in enumerate([4, 6, 8, 10], start=1)]

    result = estimate_normal_integer_fit(records, grid_points=500)

    assert result["valid"] is False
    assert "integer_assignments_nonprimitive" in result["flags"]
    assert result["integer_gcd"] == 2


def test_estimate_both_algorithms_reports_usable_count():
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 0
    config["elementary"]["measurement_mc_samples"] = 0
    config["elementary"]["null_simulation_samples"] = 0
    config["elementary"]["skip_stability_diagnostics"] = True
    records = [_q_record(index, n) for index, n in enumerate([2, 3, 5], start=1)]

    result = estimate_both_algorithms(records, config)

    assert result["usable_q_count"] == 3
    assert "normal_algorithm" in result
    assert "experimental_algorithm" in result
