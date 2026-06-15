import cv2
import numpy as np
import pandas as pd
import pytest

from millikan_ai.calibration.grid import detect_horizontal_grid_lines, detect_vertical_grid_lines
from millikan_ai.config import load_config
from millikan_ai.elementary.estimate import estimate_elementary_charge
from millikan_ai.physics.charge import compute_drop_result
from millikan_ai.segments.fitting import fit_line, fit_terminal_velocity, fit_track_segments, select_stable_window
from millikan_ai.segments.platforms import VoltageSample, segment_voltage_platforms
from millikan_ai.segments.voltage_change import detect_voltage_platform_changes


def _fast_elementary_config() -> dict:
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 0
    config["elementary"]["measurement_mc_samples"] = 20
    config["elementary"]["null_simulation_samples"] = 0
    config["elementary"]["tau_lambda_profile_optimize_points"] = 2
    config["elementary"]["tau_lambda_optimizer_maxiter"] = 12
    config["physics"]["random_mc_samples"] = 50
    return config


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
    config["roi"]["voltage_roi"] = [180, 0, 170, 92]

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


def test_select_stable_window_keeps_full_platform_by_default():
    t = np.arange(0, 5, 0.1)
    y = 2.0 * t + 4.0
    y[:20] += np.sin(np.arange(20)) * 8
    frame = pd.DataFrame({"time_s": t, "y_px": y, "x_px": np.zeros_like(t), "is_valid_detection": True})
    stable = select_stable_window(frame, min_duration_s=1.5, min_points=15)
    assert stable["time_s"].min() == 0.0
    assert stable["time_s"].max() == t[-1]


def test_fit_terminal_velocity_handles_upward_and_equilibrium_motion():
    t = np.linspace(0.0, 4.0, 41)
    upward = fit_terminal_velocity(t, 12.0 - 3.0 * t, bootstrap_samples=0)
    equilibrium = fit_terminal_velocity(t, np.full_like(t, 7.0), bootstrap_samples=0)

    assert upward["velocity_px_s"] == pytest.approx(-3.0)
    assert upward["fit_method"] == "robust_huber"
    assert equilibrium["velocity_px_s"] == pytest.approx(0.0)
    assert equilibrium["r2_diagnostic"] == 1.0


def test_fit_terminal_velocity_bootstrap_is_reproducible():
    rng = np.random.default_rng(123)
    t = np.linspace(0.0, 5.0, 80)
    y = 4.0 + 1.5 * t + rng.normal(0, 0.2, len(t))

    first = fit_terminal_velocity(t, y, bootstrap_samples=80, random_seed=99)
    second = fit_terminal_velocity(t, y, bootstrap_samples=80, random_seed=99)

    assert first["uncertainty_method"] == "block_bootstrap"
    assert first["sigma_velocity_random_px_s"] > 0
    assert first["velocity_ci_95_px_s"] == pytest.approx(second["velocity_ci_95_px_s"])


def test_fit_terminal_velocity_rejects_non_increasing_time():
    with pytest.raises(ValueError, match="non_increasing_time"):
        fit_terminal_velocity(np.array([0.0, 0.2, 0.2, 0.4]), np.array([1.0, 1.2, 1.3, 1.4]))


def test_fit_track_segments_uses_full_platform_and_boundary_guard_frames_only():
    config = load_config("configs/default.yaml")
    config["segment"]["boundary_guard_frames"] = 2
    track = pd.DataFrame(
        {
            "video_id": ["synthetic"] * 10,
            "track_id": ["candidate_001"] * 10,
            "frame_idx": np.arange(10),
            "time_s": np.arange(10) / 10.0,
            "x_px": np.zeros(10),
            "y_px": np.arange(10, dtype=float),
            "is_valid_detection": True,
        }
    )
    platforms = pd.DataFrame(
        [
            {
                "platform_id": "P001",
                "start_frame": 0,
                "end_frame": 9,
                "start_time_s": 0.0,
                "end_time_s": 0.9,
                "voltage_V": 0.0,
            }
        ]
    )

    segments = fit_track_segments(track, platforms, scale_y_m_per_px=1e-6, config=config)

    assert segments.iloc[0]["start_time_s"] == pytest.approx(0.2)
    assert segments.iloc[0]["end_time_s"] == pytest.approx(0.7)
    assert segments.iloc[0]["num_points"] == 6


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
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 900
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e, "sigma_charge_C": 0.04e-19}}
        for i, n in enumerate([2, 3, 5, 7, 8])
    ]
    result = estimate_elementary_charge(drops, config)
    assert result["valid"] is True
    assert abs(result["elementary_charge"]["e_hat_C"] - e) < 0.03e-19
    assert result["elementary_charge"]["search_interval_C"] == [0.5e-19, 2.5e-19]
    assert result["model_comparison"]["method"] == "bounded_profile_quantized_likelihood"


def test_elementary_charge_uses_all_successful_q_without_quality_gate():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 500
    e = 1.6e-19
    drops = [
        {"drop_id": "d1", "valid": True, "quality_score": 0.0, "result": {"charge_abs_C": 2 * e, "sigma_charge_C": 0.04e-19}},
        {"drop_id": "d2", "valid": True, "quality_score": 0.0, "result": {"charge_abs_C": 3 * e, "sigma_charge_C": 0.04e-19}},
        {"drop_id": "d3", "valid": True, "quality_score": 0.0, "result": {"charge_abs_C": 5 * e, "sigma_charge_C": 0.04e-19}},
    ]

    result = estimate_elementary_charge(drops, config)

    assert result["valid"] is True
    assert result["num_used_drops"] == 3


def test_elementary_charge_reports_harmonic_ambiguity_for_even_multiples():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 900
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e, "sigma_charge_C": 0.03e-19}}
        for i, n in enumerate([2, 4, 6, 8, 10])
    ]

    result = estimate_elementary_charge(drops, config)

    assert result["valid"] is True
    assert result["harmonic_analysis"]["harmonic_ambiguity"] is True
    assert len(result["harmonic_analysis"]["candidate_modes"]) >= 2


def test_elementary_model_comparison_scores_clear_quantization_positive():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 500
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e + offset, "sigma_charge_C": 0.05e-19}}
        for i, (n, offset) in enumerate(zip([2, 3, 4, 5, 6, 7], [0.01e-19, -0.02e-19, 0.0, 0.02e-19, -0.01e-19, 0.0]))
    ]

    result = estimate_elementary_charge(drops, config)

    assert result["model_comparison"]["continuous_model"] == "heteroscedastic_error_convolved_gmm"
    assert result["model_comparison"]["delta_elpd"] > 0


def test_elementary_model_comparison_does_not_overstate_continuous_sample():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 400
    values = np.array([2.2, 2.7, 3.1, 3.8, 4.4, 5.0]) * 1e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": float(value), "sigma_charge_C": 0.08e-19}}
        for i, value in enumerate(values)
    ]

    result = estimate_elementary_charge(drops, config)

    assert result["model_comparison"]["evidence_label"] != "strong"


def test_quantized_profile_optimizes_tau_lambda_continuously():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 100
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e + offset, "sigma_charge_C": 0.025e-19}}
        for i, (n, offset) in enumerate(zip([2, 3, 4, 6, 8, 9], [0.00e-19, 0.04e-19, -0.03e-19, 0.02e-19, -0.04e-19, 0.03e-19]))
    ]

    result = estimate_elementary_charge(drops, config)

    optimizer = result["optimizer"]
    assert optimizer["tau_lambda_optimizer"] == "scipy_minimize"
    assert optimizer["converged"] is True
    assert optimizer["n_eval"] > 0
    old_tau_grid = {0.0, 0.5, 1.0, 2.0, 4.0}
    tau_ratio = result["elementary_charge"]["tau_C"] / 0.025e-19
    assert all(abs(tau_ratio - value) > 0.02 for value in old_tau_grid)


def test_model_comparison_uses_repeated_5fold_for_large_samples():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 70
    config["elementary"]["cv_repeats"] = 2
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": (2 + (i % 7)) * e + ((i % 3) - 1) * 0.01e-19, "sigma_charge_C": 0.05e-19}}
        for i in range(20)
    ]

    result = estimate_elementary_charge(drops, config)
    comparison = result["model_comparison"]

    assert comparison["comparison_method"] == "repeated_5fold_predictive_likelihood"
    assert comparison["folds"] == 5
    assert comparison["repeats"] > 1
    assert len(comparison["per_split_delta_elpd"]) == comparison["folds"] * comparison["repeats"]
    assert comparison["delta_elpd_se"] >= 0


def test_null_simulation_reports_empirical_p_value():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 60
    config["elementary"]["null_simulation_samples"] = 5
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e, "sigma_charge_C": 0.06e-19}}
        for i, n in enumerate([2, 3, 4, 5, 6, 7])
    ]

    result = estimate_elementary_charge(drops, config)
    null = result["model_comparison"]["null_simulation"]

    assert null["samples"] == 5
    assert len(null["null_delta_elpd_distribution"]) == 5
    assert 0.0 <= null["empirical_p_value"] <= 1.0
    assert result["model_comparison"]["evidence_label"] in {"strong", "moderate", "weak", "insufficient"}


def test_uncertainty_outputs_include_bootstrap_and_measurement_mc_counts():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 70
    config["elementary"]["e_bootstrap_samples"] = 7
    config["elementary"]["measurement_mc_samples"] = 9
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e, "sigma_charge_C": 0.05e-19}}
        for i, n in enumerate([2, 3, 5, 7, 8])
    ]

    result = estimate_elementary_charge(drops, config)
    elementary = result["elementary_charge"]

    assert elementary["uncertainty_method"] == "profile_bootstrap_measurement_mc"
    assert elementary["bootstrap_samples_used"] == 7
    assert elementary["measurement_mc_samples_used"] == 9
    assert len(elementary["measurement_mc_ci_95_C"]) == 2


def test_heteroscedastic_gmm_reports_sigma_aware_fit():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 60
    values = [1.6e-19, 1.65e-19, 1.7e-19, 5.0e-19, 5.1e-19, 10.0e-19]
    sigmas = [0.03e-19, 0.03e-19, 0.03e-19, 0.08e-19, 0.08e-19, 2.5e-19]
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": value, "sigma_charge_C": sigma}}
        for i, (value, sigma) in enumerate(zip(values, sigmas))
    ]

    result = estimate_elementary_charge(drops, config)
    comparison = result["model_comparison"]

    assert comparison["continuous_model"] == "heteroscedastic_error_convolved_gmm"
    assert comparison["heteroscedastic"] is True
    assert comparison["continuous_components"] <= 2


@pytest.mark.parametrize("n_drops", [3, 5, 10, 15, 20, 40])
def test_elementary_quantized_known_truth_across_dataset_sizes(n_drops):
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 70
    config["elementary"]["comparison_profile_grid_points"] = 40
    config["elementary"]["cv_repeats"] = 1
    e = 1.6e-19
    multipliers = [2 + (idx % 8) for idx in range(n_drops)]
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e + ((i % 3) - 1) * 0.01e-19, "sigma_charge_C": 0.05e-19}}
        for i, n in enumerate(multipliers)
    ]

    result = estimate_elementary_charge(drops, config)

    assert result["valid"] is True
    assert result["num_used_drops"] == n_drops
    assert abs(result["elementary_charge"]["e_hat_C"] - e) < 0.12e-19


def test_elementary_reports_leave_one_drop_out_stability_and_is_order_invariant():
    config = _fast_elementary_config()
    config["elementary"]["profile_grid_points"] = 80
    config["elementary"]["comparison_profile_grid_points"] = 40
    e = 1.6e-19
    drops = [
        {"drop_id": f"d{i}", "valid": True, "result": {"charge_abs_C": n * e, "sigma_charge_C": 0.05e-19}}
        for i, n in enumerate([2, 3, 5, 7, 8])
    ]

    forward = estimate_elementary_charge(drops, config)
    reversed_result = estimate_elementary_charge(list(reversed(drops)), config)

    stability = forward["stability"]["leave_one_drop_out"]
    assert len(stability) == 5
    assert all(row["valid"] for row in stability)
    assert forward["elementary_charge"]["e_hat_C"] == pytest.approx(reversed_result["elementary_charge"]["e_hat_C"])
