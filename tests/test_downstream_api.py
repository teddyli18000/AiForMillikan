import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from millikan_ai.config import load_config
from millikan_ai.downstream import run_downstream_analysis
from millikan_ai.physics.charge import eta_eff
from millikan_ai.physics.viscosity import resolve_air_viscosity


def _known_truth_motion(config: dict, radius_m: float, charge_C: float) -> tuple[float, float]:
    viscosity = resolve_air_viscosity(config)
    physics = config["physics"]
    eta = viscosity["air_viscosity_Pa_s"]
    eff = eta_eff(radius_m, eta, physics["pressure_Pa"], physics["cunningham_b_Pa_m"])
    alpha = (2 * physics["oil_density_kg_m3"] * physics["gravity_m_s2"] * radius_m**2) / (9 * eff)
    gamma = charge_C / (6 * math.pi * eff * radius_m * physics["plate_distance_m"])
    return alpha, gamma


def _trajectories_for_drops(config: dict, charges: list[float]) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    scale = 1.0e-6
    radius = 0.72e-6
    platforms = pd.DataFrame(
        [
            {
                "platform_id": "P001",
                "start_frame": 0,
                "end_frame": 40,
                "start_time_s": 0.0,
                "end_time_s": 4.0,
                "voltage_V": 0.0,
            },
            {
                "platform_id": "P002",
                "start_frame": 50,
                "end_frame": 90,
                "start_time_s": 5.0,
                "end_time_s": 9.0,
                "voltage_V": 250.0,
            },
            {
                "platform_id": "P003",
                "start_frame": 100,
                "end_frame": 140,
                "start_time_s": 10.0,
                "end_time_s": 14.0,
                "voltage_V": 400.0,
            },
        ]
    )
    rows = []
    for drop_index, charge in enumerate(charges, start=1):
        alpha, gamma = _known_truth_motion(config, radius, charge)
        y_offset = 100.0 + drop_index * 20.0
        for platform in platforms.to_dict("records"):
            velocity_px_s = (alpha - gamma * float(platform["voltage_V"])) / scale
            for frame in range(int(platform["start_frame"]), int(platform["end_frame"]) + 1):
                time_s = frame / 10.0
                rows.append(
                    {
                        "video_id": "synthetic",
                        "track_id": f"accepted_{drop_index:03d}",
                        "frame_idx": frame,
                        "time_s": time_s,
                        "x_px": 50.0 + drop_index,
                        "y_px": y_offset + velocity_px_s * (time_s - float(platform["start_time_s"])),
                        "is_valid_detection": True,
                    }
                )
    return pd.DataFrame(rows), platforms, scale


def test_standalone_downstream_api_requires_no_video_and_uses_every_successful_q(tmp_path: Path):
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 20
    config["elementary"]["measurement_mc_samples"] = 20
    config["elementary"]["null_simulation_samples"] = 0
    e = 1.6e-19
    trajectories, platforms, scale = _trajectories_for_drops(config, [2 * e, 3 * e, 5 * e])

    result = run_downstream_analysis(
        trajectories=trajectories,
        platforms=platforms,
        scale_y_m_per_px=scale,
        config=config,
        run_dir=tmp_path,
    )

    assert result["multi_drop_results"]["valid_drop_count"] == 3
    assert result["elementary"]["num_used_drops"] == 3
    assert result["elementary"]["valid"] is True
    assert (tmp_path / "drop_charge_results.csv").exists()
    assert (tmp_path / "analysis_report.md").exists()


def test_standalone_downstream_api_excludes_only_failed_q_from_elementary(tmp_path: Path):
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 10
    config["elementary"]["measurement_mc_samples"] = 10
    config["elementary"]["null_simulation_samples"] = 0
    e = 1.6e-19
    trajectories, platforms, scale = _trajectories_for_drops(config, [2 * e, 3 * e, 5 * e])
    bad_platforms = platforms.copy()
    bad_platforms["voltage_V"] = 100.0

    result = run_downstream_analysis(
        trajectories=trajectories[trajectories["track_id"] == "accepted_001"],
        platforms=bad_platforms,
        scale_y_m_per_px=scale,
        config=config,
        run_dir=tmp_path / "failed",
    )

    assert result["multi_drop_results"]["valid_drop_count"] == 0
    assert result["elementary"]["valid"] is False
    assert result["elementary"]["num_used_drops"] == 0
    failures = result["charge_failures"]["failures"]
    assert failures and "insufficient_distinct_voltages" in failures[0]["errors"]


def test_downstream_api_does_not_import_or_call_tracker():
    import millikan_ai.downstream as downstream

    assert not hasattr(downstream, "track_multiple_candidates")


def test_downstream_shared_systematic_monte_carlo_outputs_correlated_uncertainty(tmp_path: Path):
    config = load_config("configs/default.yaml")
    config["elementary"]["e_bootstrap_samples"] = 0
    config["elementary"]["measurement_mc_samples"] = 0
    config["elementary"]["null_simulation_samples"] = 0
    config["physics"]["random_mc_samples"] = 80
    config["physics"]["systematic_mc_samples"] = 120
    config["physics"]["systematic_uncertainty"] = {
        "spatial_scale_rel": 0.01,
        "plate_distance_rel": 0.01,
        "voltage_scale_rel": 0.005,
        "temperature_C": 0.5,
        "pressure_rel": 0.002,
        "oil_density_rel": 0.005,
        "cunningham_b_rel": 0.01,
    }
    e = 1.6e-19
    trajectories, platforms, scale = _trajectories_for_drops(config, [2 * e, 3 * e, 5 * e])

    result = run_downstream_analysis(
        trajectories=trajectories,
        platforms=platforms,
        scale_y_m_per_px=scale,
        config=config,
        run_dir=tmp_path,
    )

    uncertainty = result["uncertainty_details"]
    assert uncertainty["status"] == "complete"
    assert uncertainty["shared_systematic_mc"]["samples_used"] >= 100
    per_drop = uncertainty["per_drop"]
    assert len(per_drop) == 3
    assert all(row["sigma_charge_systematic_C"] > 0 for row in per_drop)
    assert all(row["combined_charge_ci95_low_C"] < row["charge_abs_C"] < row["combined_charge_ci95_high_C"] for row in per_drop)
