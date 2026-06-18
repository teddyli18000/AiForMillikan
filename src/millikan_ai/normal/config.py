from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_NORMAL_CONFIG: dict[str, Any] = {
    "tracking": {
        "diameter": 5,
        "invert": False,
        "minmass": 80.0,
        "local_search_radius_px": 45.0,
        "max_accept_distance_px": 30.0,
        "memory_frames": 5,
        "local_topn": 20,
        "grid_reject_dilate_px": 0,
        "grid_occlusion_radius_px": 2,
        "skip_detection_on_grid": True,
        "max_search_radius_px": 90.0,
        "min_reacquire_trend_dy_px": -2.0,
        "max_reacquire_dx_px": 18.0,
        "max_velocity_jump_ratio": 3.5,
    },
    "grid": {
        "sample_frames": 48,
        "sample_stride": 3,
        "measurement_distance_m": 0.0015,
        "min_horizontal_coverage": 0.45,
        "line_merge_px": 5,
        "mask_dilate_px": 5,
    },
    "voltage": {
        "sample_stride_frames": 5,
        "search_region": [0.45, 0.0, 0.55, 0.32],
        "descriptor_width": 96,
        "descriptor_height": 32,
        "change_threshold_sigma": 3.0,
        "min_change_score": 0.08,
        "stable_after_s": 0.35,
        "operation_gap_multiplier": 2.5,
        "operation_gap_min_s": 2.2,
        "operation_gap_max_s": 2.8,
    },
    "fit": {
        "min_points": 12,
        "min_duration_s": 0.8,
        "min_displacement_px": 8.0,
        "min_r2": 0.90,
        "max_rmse_px": 3.5,
        "max_missing_ratio": 0.35,
        "max_x_drift_px": 30.0,
        "max_reacquire_dx_px": 18.0,
        "max_half_velocity_ratio": 2.2,
    },
    "physics": {
        "plate_distance_m": 0.005,
        "oil_density_kg_m3": 981.0,
        "pressure_Pa": 101325.0,
        "cunningham_b_Pa_m": 0.0000082,
        "gravity_m_s2": 9.80665,
        "air_viscosity_Pa_s": 1.81e-5,
        "random_bootstrap_samples": 300,
        "systematic_mc_samples": 300,
        "systematic_uncertainty": {
            "spatial_scale_rel": 0.0,
            "plate_distance_rel": 0.0,
            "voltage_scale_rel": 0.0,
            "air_viscosity_rel": 0.0,
            "pressure_rel": 0.0,
            "oil_density_rel": 0.0,
            "cunningham_b_rel": 0.0,
        },
    },
    "inversion": {
        "min_records": 3,
        "e_min_C": 1.35e-19,
        "e_max_C": 1.90e-19,
        "grid_points": 900,
        "max_integer": 60,
        "max_weighted_rms": 2.5,
        "harmonic_tolerance": 0.04,
        "leave_one_out_max_rel_shift": 0.08,
    },
}


def normal_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_NORMAL_CONFIG)
    if overrides:
        _merge(cfg, overrides)
    return cfg


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
