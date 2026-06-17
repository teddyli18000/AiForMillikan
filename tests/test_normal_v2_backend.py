from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pytest


def test_normal_v2_imports_stay_isolated():
    root = Path("src/millikan_ai/normal_v2")
    assert root.exists()
    forbidden = {
        "millikan_ai.tracking",
        "millikan_ai.segments",
        "millikan_ai.pipeline",
        "millikan_ai.physics",
        "millikan_ai.quality",
    }
    violations: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if any(module == item or module.startswith(item + ".") for item in forbidden):
                        violations.append(f"{path}:{module}")
                continue
            if module and any(module == item or module.startswith(item + ".") for item in forbidden):
                violations.append(f"{path}:{module}")
    assert violations == []


def test_reacquired_velocity_is_normalized_by_frame_gap():
    from millikan_ai.normal_v2.tracking import Detection, NormalTrackingConfig, track_single_drop

    detections = {
        1: Detection(11.0, 10.0, mass=90.0),
        4: Detection(17.0, 10.0, mass=92.0),
        5: Detection(19.0, 10.0, mass=93.0),
    }

    result = track_single_drop(
        frame_count=6,
        initial_position=(10.0, 10.0),
        target_frame=0,
        fps=30.0,
        config=NormalTrackingConfig(memory_frames=5, base_search_radius_px=8.0, max_accept_distance_px=12.0),
        detector=lambda frame_idx, _pred, _radius: detections.get(frame_idx),
    )

    by_frame = {point.frame_idx: point for point in result.points}
    assert by_frame[2].status == "missing"
    assert by_frame[3].status == "missing"
    assert by_frame[4].status == "reacquired"
    assert by_frame[4].frame_gap_since_detection == 3
    assert by_frame[5].predicted_x == pytest.approx(19.0)


def test_missing_points_do_not_enter_velocity_fit_and_region_truncates_once():
    from millikan_ai.normal_v2.tracking import TrackPoint
    from millikan_ai.normal_v2.velocity import fit_terminal_velocity

    points = [
        TrackPoint(frame_idx=0, time_s=0.0, status="tracking", x=5.0, y=20.0, predicted_x=5.0, predicted_y=20.0),
        TrackPoint(frame_idx=1, time_s=1.0, status="missing", x=None, y=None, predicted_x=5.0, predicted_y=30.0),
        TrackPoint(frame_idx=2, time_s=2.0, status="reacquired", x=5.0, y=60.0, predicted_x=5.0, predicted_y=60.0),
        TrackPoint(frame_idx=3, time_s=3.0, status="tracking", x=5.0, y=80.0, predicted_x=5.0, predicted_y=80.0),
        TrackPoint(frame_idx=4, time_s=4.0, status="tracking", x=5.0, y=101.0, predicted_x=5.0, predicted_y=101.0),
        TrackPoint(frame_idx=5, time_s=5.0, status="tracking", x=5.0, y=80.0, predicted_x=5.0, predicted_y=80.0),
    ]

    fit = fit_terminal_velocity(
        points,
        start_time_s=0.0,
        end_time_s=5.0,
        scale_y_m_per_px=2.0e-6,
        legal_y_min_px=10.0,
        legal_y_max_px=100.0,
        min_points=3,
    )

    assert fit.valid is True
    assert fit.used_frame_indices == [0, 2, 3]
    assert fit.truncated_at_frame == 4
    assert fit.velocity_m_s == pytest.approx(20.0 * 2.0e-6)


def test_operation_merge_and_normal_window_handles_recovery_and_no_recovery():
    from millikan_ai.normal_v2.voltage_events import ChangePeak, merge_change_operations, normal_window_from_operations

    operations = merge_change_operations(
        [
            ChangePeak(frame_idx=30, score=0.8),
            ChangePeak(frame_idx=35, score=0.7),
            ChangePeak(frame_idx=150, score=0.9),
            ChangePeak(frame_idx=156, score=0.6),
        ],
        fps=30.0,
        merge_window_s=0.4,
    )
    assert [(op.start_frame, op.end_frame) for op in operations] == [(30, 35), (150, 156)]

    window = normal_window_from_operations(operations, frame_count=240, fps=30.0, stable_after_s=0.2)
    assert window.start_frame == 41
    assert window.end_frame == 149
    assert "has_recovery_operation" in window.flags

    no_recovery = normal_window_from_operations(operations[:1], frame_count=240, fps=30.0, stable_after_s=0.2)
    assert no_recovery.start_frame == 41
    assert no_recovery.end_frame == 239
    assert "no_recovery_operation" in no_recovery.flags


def test_grid_scale_uses_second_to_penultimate_lines():
    from millikan_ai.normal_v2.grid_calibration import grid_scale_from_horizontal_lines

    result = grid_scale_from_horizontal_lines([10, 30, 50, 70, 90], measurement_distance_m=1.5e-3)

    assert result.valid is True
    assert result.y_second_px == 30
    assert result.y_penultimate_px == 70
    assert result.scale_y_m_per_px == pytest.approx(1.5e-3 / 40.0)


def test_balance_fall_q_recovers_known_charge_and_uncertainty_changes_with_noise():
    from millikan_ai.normal_v2.physics import PhysicalConfig, compute_balance_fall_charge
    from millikan_ai.normal_v2.uncertainty import velocity_uncertainty_from_residuals

    cfg = PhysicalConfig(
        plate_distance_m=5.0e-3,
        oil_density_kg_m3=981.0,
        gravity_m_s2=9.80665,
        air_viscosity_Pa_s=1.81e-5,
        pressure_Pa=101325.0,
        cunningham_b_Pa_m=8.2e-6,
    )
    result = compute_balance_fall_charge(v_g_m_s=1.2e-4, balance_voltage_V=240.0, config=cfg)

    assert result.valid is True
    assert result.radius_m > 0
    assert result.charge_C > 0

    low = velocity_uncertainty_from_residuals([0.01, -0.01, 0.0], slope_m_s=1.2e-4, sample_count=30)
    high = velocity_uncertainty_from_residuals([0.2, -0.2, 0.1], slope_m_s=1.2e-4, sample_count=30)
    assert high.standard_uncertainty_m_s > low.standard_uncertainty_m_s


def test_unique_records_and_session_roundtrip(tmp_path: Path):
    from millikan_ai.normal_v2.records import NormalQRecord, NormalSession, save_session, load_session

    first = NormalQRecord.create(
        video_path="same.mp4",
        target_frame=50,
        window={"start_frame": 60, "end_frame": 120},
        q_C=3.2e-19,
        sigma_q_C=0.1e-19,
        valid=True,
    )
    second = NormalQRecord.create(
        video_path="same.mp4",
        target_frame=50,
        window={"start_frame": 60, "end_frame": 120},
        q_C=3.2e-19,
        sigma_q_C=0.1e-19,
        valid=True,
    )
    assert first.record_id != second.record_id

    path = tmp_path / "session.json"
    save_session(NormalSession(records=[first, second]), path)
    loaded = load_session(path)

    assert [record.record_id for record in loaded.records] == [first.record_id, second.record_id]
    assert loaded.counts()["selected_valid"] == 2


def test_normal_integer_fit_accepts_truth_and_rejects_common_divisor_boundary_and_large_residual():
    from millikan_ai.normal_v2.elementary import estimate_normal_integer_fit

    truth = 1.602e-19
    good = [
        {"record_id": "a", "q_C": 2 * truth, "sigma_q_C": 0.04e-19, "valid": True, "selected": True},
        {"record_id": "b", "q_C": 3 * truth, "sigma_q_C": 0.04e-19, "valid": True, "selected": True},
        {"record_id": "c", "q_C": 5 * truth, "sigma_q_C": 0.04e-19, "valid": True, "selected": True},
        {"record_id": "d", "q_C": 7 * truth, "sigma_q_C": 0.04e-19, "valid": True, "selected": True},
    ]
    fit = estimate_normal_integer_fit(good, grid_points=800)
    assert fit["valid"] is True
    assert fit["e_hat_C"] == pytest.approx(truth, rel=0.003)

    common_divisor = [
        {"record_id": "a", "q_C": 4 * truth, "sigma_q_C": 0.03e-19, "valid": True, "selected": True},
        {"record_id": "b", "q_C": 6 * truth, "sigma_q_C": 0.03e-19, "valid": True, "selected": True},
        {"record_id": "c", "q_C": 8 * truth, "sigma_q_C": 0.03e-19, "valid": True, "selected": True},
    ]
    rejected = estimate_normal_integer_fit(common_divisor, grid_points=800)
    assert rejected["valid"] is False
    assert "integer_assignments_nonprimitive" in rejected["flags"]

    noisy = good[:3] + [{"record_id": "x", "q_C": 4.41e-19, "sigma_q_C": 0.005e-19, "valid": True, "selected": True}]
    bad = estimate_normal_integer_fit(noisy, grid_points=800)
    assert bad["valid"] is False
    assert "weighted_residual_too_large" in bad["flags"]


def test_session_report_omits_blind_section_until_reliable_result():
    from millikan_ai.normal_v2.reporting import render_session_report

    report = render_session_report({"records": [{"valid": True, "selected": True}]}, inversion=None)
    assert "Blind inversion" not in report

    report = render_session_report(
        {"records": [{"valid": True, "selected": True}] * 3},
        inversion={"normal_algorithm": {"valid": False}, "experimental_algorithm": {"bounded_estimate_available": False}},
    )
    assert "Blind inversion" not in report

    report = render_session_report(
        {"records": [{"valid": True, "selected": True}] * 3},
        inversion={"normal_algorithm": {"valid": True, "e_hat_C": 1.6e-19}, "experimental_algorithm": {"bounded_estimate_available": False}},
    )
    assert "Blind inversion" in report
    assert "Normal algorithm" in report
    assert "Experimental algorithm" not in report
    assert "identified elementary charge" not in report
