from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_NORMAL_CONFIG: dict[str, Any] = {
    "session": {
        "session_root": "runs/normal_session",
        "run_root": "runs/normal_records",
    },
    "voltage": {
        "sample_stride_frames": 5,
        "search_region": [0.45, 0.0, 0.55, 0.32],
        "descriptor_width": 96,
        "descriptor_height": 32,
        "min_change_score": 0.08,
        "change_threshold_sigma": 3.0,
        "stable_after_s": 0.25,
        "operation_gap_s": 0.8,
    },
    "selection": {
        "before_zero_v_start_s": 1.0,
        "after_zero_v_start_s": 0.5,
    },
    "grid": {
        "sample_frames": 40,
        "sample_stride": 3,
        "measurement_distance_m": 0.0015,
        "min_horizontal_coverage": 0.42,
        "line_merge_px": 5,
        "mask_dilate_px": 5,
    },
    "tracking": {
        "diameter": 5,
        "invert": False,
        "minmass": 80.0,
        "local_search_radius_px": 45.0,
        "max_accept_distance_px": 30.0,
        "memory_frames": 8,
        "local_topn": 20,
        "grid_occlusion_radius_px": 2,
        "skip_detection_on_grid": True,
        "max_tracking_seconds": 20.0,
    },
    "fit": {
        "min_points": 5,
        "min_duration_s": 0.35,
        "min_displacement_px": 2.0,
        "min_r2": 0.55,
        "max_missing_ratio": 0.55,
    },
    "physics": {
        "plate_distance_m": 0.005,
        "oil_density_kg_m3": 981.0,
        "pressure_Pa": 101325.0,
        "cunningham_b_Pa_m": 0.0000082,
        "gravity_m_s2": 9.80665,
        "air_viscosity_Pa_s": 1.81e-5,
        "relative_uncertainty_floor": 0.05,
    },
    "inversion": {
        "min_records": 3,
        "e_min_C": 1.35e-19,
        "e_max_C": 1.90e-19,
        "grid_points": 900,
        "max_integer": 80,
        "max_iterations": 8,
        "candidate_count": 8,
        "sigma_floor_C": 0.0,
        "max_weighted_rms": 2.5,
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
