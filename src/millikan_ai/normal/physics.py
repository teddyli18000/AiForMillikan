from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from millikan_ai.physics.charge import eta_eff, solve_radius_with_cunningham
from millikan_ai.physics.viscosity import resolve_air_viscosity


@dataclass(frozen=True)
class FallVelocityFit:
    valid: bool
    flags: list[str]
    start_frame: int | None
    end_frame: int | None
    num_points: int
    slope_y_px_s: float
    intercept_y_px: float
    velocity_m_s: float
    sigma_velocity_m_s: float
    r2: float
    rmse_px: float
    first_half_slope_y_px_s: float
    second_half_slope_y_px_s: float

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "flags": self.flags,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "num_points": self.num_points,
            "slope_y_px_s": self.slope_y_px_s,
            "intercept_y_px": self.intercept_y_px,
            "velocity_m_s": self.velocity_m_s,
            "sigma_velocity_m_s": self.sigma_velocity_m_s,
            "r2": self.r2,
            "rmse_px": self.rmse_px,
            "first_half_slope_y_px_s": self.first_half_slope_y_px_s,
            "second_half_slope_y_px_s": self.second_half_slope_y_px_s,
        }


def detected_points_for_fit(
    track: pd.DataFrame,
    start_frame: int,
    end_frame: int | None,
    *,
    penultimate_grid_y_px: float | None = None,
) -> pd.DataFrame:
    if track.empty:
        return pd.DataFrame()
    frame_col = "source_frame" if "source_frame" in track.columns else "frame"
    detected = track[track["detected"].astype(bool)].copy()
    if "status" in detected.columns:
        detected = detected[detected["status"].astype(str).isin(["tracking", "reacquired"])]
    detected = detected[np.isfinite(pd.to_numeric(detected["x"], errors="coerce")) & np.isfinite(pd.to_numeric(detected["y"], errors="coerce"))]
    detected = detected[pd.to_numeric(detected[frame_col], errors="coerce") >= int(start_frame)]
    if end_frame is not None:
        detected = detected[pd.to_numeric(detected[frame_col], errors="coerce") <= int(end_frame)]
    if penultimate_grid_y_px is not None and math.isfinite(float(penultimate_grid_y_px)):
        detected = detected[pd.to_numeric(detected["y"], errors="coerce") <= float(penultimate_grid_y_px)]
    return detected.sort_values(frame_col).reset_index(drop=True)


def _linear_fit(t: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float, float]:
    slope, intercept = np.polyfit(t, y, deg=1)
    predicted = slope * t + intercept
    residual = y - predicted
    ss_res = float(np.sum(np.square(residual)))
    ss_tot = float(np.sum(np.square(y - float(np.mean(y)))))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    rmse = math.sqrt(ss_res / len(t)) if len(t) else math.inf
    if len(t) > 2:
        centered = t - float(np.mean(t))
        sxx = float(np.sum(np.square(centered)))
        sigma2 = ss_res / max(1, len(t) - 2)
        slope_se = math.sqrt(sigma2 / sxx) if sxx > 0 else math.inf
    else:
        slope_se = math.inf
    return float(slope), float(intercept), float(r2), float(rmse), float(slope_se)


def fit_fall_velocity(
    track: pd.DataFrame,
    *,
    fps: float,
    scale_y_m_per_px: float,
    start_frame: int,
    end_frame: int | None = None,
    penultimate_grid_y_px: float | None = None,
    min_points: int = 5,
) -> FallVelocityFit:
    points = detected_points_for_fit(track, start_frame, end_frame, penultimate_grid_y_px=penultimate_grid_y_px)
    if len(points) < int(min_points):
        return FallVelocityFit(False, ["too_few_tracking_points"], None, None, int(len(points)), math.nan, math.nan, math.nan, math.inf, math.nan, math.nan, math.nan, math.nan)
    frame_col = "source_frame" if "source_frame" in points.columns else "frame"
    frames = pd.to_numeric(points[frame_col], errors="raise").to_numpy(float)
    t = frames / float(fps)
    t = t - float(t[0])
    y = pd.to_numeric(points["y"], errors="raise").to_numpy(float)
    slope, intercept, r2, rmse, slope_se = _linear_fit(t, y)
    midpoint = len(points) // 2
    first_slope = _linear_fit(t[:midpoint], y[:midpoint])[0] if midpoint >= 2 else math.nan
    second_slope = _linear_fit(t[midpoint:], y[midpoint:])[0] if len(points) - midpoint >= 2 else math.nan
    flags: list[str] = []
    velocity = float(slope) * float(scale_y_m_per_px)
    sigma_velocity = abs(float(slope_se) * float(scale_y_m_per_px))
    if velocity <= 0 or not math.isfinite(velocity):
        flags.append("non_positive_fall_velocity")
    if not (math.isfinite(sigma_velocity) and sigma_velocity > 0):
        flags.append("velocity_uncertainty_unavailable")
    if r2 < 0.90:
        flags.append("low_y_time_fit_r2")
    return FallVelocityFit(
        valid=not flags,
        flags=flags,
        start_frame=int(frames[0]),
        end_frame=int(frames[-1]),
        num_points=int(len(points)),
        slope_y_px_s=float(slope),
        intercept_y_px=float(intercept),
        velocity_m_s=velocity,
        sigma_velocity_m_s=sigma_velocity,
        r2=float(r2),
        rmse_px=float(rmse),
        first_half_slope_y_px_s=float(first_slope),
        second_half_slope_y_px_s=float(second_slope),
    )


def _systematic_sigmas(config: dict[str, Any]) -> dict[str, float]:
    systematics = dict(config.get("physics", {}).get("systematic_uncertainty", {}) or {})
    return {
        "spatial_scale_rel": float(systematics.get("spatial_scale_rel", 0.0) or 0.0),
        "plate_distance_rel": float(systematics.get("plate_distance_rel", 0.0) or 0.0),
        "voltage_scale_rel": float(systematics.get("voltage_scale_rel", 0.0) or 0.0),
        "pressure_rel": float(systematics.get("pressure_rel", 0.0) or 0.0),
        "oil_density_rel": float(systematics.get("oil_density_rel", 0.0) or 0.0),
        "cunningham_b_rel": float(systematics.get("cunningham_b_rel", 0.0) or 0.0),
    }


def _charge_from_velocity(velocity_m_s: float, balance_voltage_V: float, constants: dict[str, Any]) -> tuple[float | None, float | None, list[str]]:
    if balance_voltage_V <= 0 or not math.isfinite(balance_voltage_V):
        return None, None, ["non_positive_balance_voltage"]
    radius, flags = solve_radius_with_cunningham(float(velocity_m_s), constants)
    if flags or radius is None:
        return None, None, flags
    eta = float(constants["air_viscosity_Pa_s"])
    pressure = float(constants["pressure_Pa"])
    b = float(constants["cunningham_b_Pa_m"])
    d = float(constants["plate_distance_m"])
    eff = eta_eff(radius, eta, pressure, b)
    gamma = float(velocity_m_s) / float(balance_voltage_V)
    charge = 6.0 * math.pi * eff * radius * d * gamma
    if not (math.isfinite(charge) and charge > 0):
        return radius, None, ["non_finite_charge"]
    return float(radius), float(charge), []


def compute_balance_fall_q(
    velocity_fit: FallVelocityFit,
    *,
    balance_voltage_V: float,
    config: dict[str, Any],
    record_id: str = "q_001",
) -> dict[str, object]:
    if not velocity_fit.valid:
        return {
            "record_id": record_id,
            "valid": False,
            "usable_for_inversion": False,
            "flags": ["invalid_fall_velocity_fit", *velocity_fit.flags],
            "fit": velocity_fit.to_dict(),
            "result": {},
        }
    constants = {**config["physics"], **resolve_air_viscosity(config)}
    radius, charge, flags = _charge_from_velocity(velocity_fit.velocity_m_s, balance_voltage_V, constants)
    if flags or radius is None or charge is None:
        return {
            "record_id": record_id,
            "valid": False,
            "usable_for_inversion": False,
            "flags": flags,
            "fit": velocity_fit.to_dict(),
            "result": {},
        }
    random_samples = int(config.get("physics", {}).get("random_mc_samples", 1000))
    rng = np.random.default_rng(int(config.get("elementary", {}).get("random_seed", 42)))
    random_charges: list[float] = []
    if random_samples > 1 and math.isfinite(velocity_fit.sigma_velocity_m_s) and velocity_fit.sigma_velocity_m_s > 0:
        draws = rng.normal(float(velocity_fit.velocity_m_s), float(velocity_fit.sigma_velocity_m_s), size=random_samples)
        for velocity in draws:
            if not math.isfinite(float(velocity)) or velocity <= 0:
                continue
            _radius_i, charge_i, draw_flags = _charge_from_velocity(float(velocity), balance_voltage_V, constants)
            if not draw_flags and charge_i is not None:
                random_charges.append(float(charge_i))
    sigma_random = float(np.std(random_charges, ddof=1)) if len(random_charges) > 1 else math.inf

    systematic = _systematic_sigmas(config)
    systematic_charges: list[float] = []
    systematic_incomplete = not any(value > 0 for value in systematic.values())
    if random_samples > 1 and not systematic_incomplete:
        for _ in range(random_samples):
            sampled_constants = dict(constants)
            sampled_velocity = float(velocity_fit.velocity_m_s) * rng.normal(1.0, systematic["spatial_scale_rel"]) if systematic["spatial_scale_rel"] > 0 else float(velocity_fit.velocity_m_s)
            sampled_u = float(balance_voltage_V) * rng.normal(1.0, systematic["voltage_scale_rel"]) if systematic["voltage_scale_rel"] > 0 else float(balance_voltage_V)
            for key, sigma_key in [
                ("plate_distance_m", "plate_distance_rel"),
                ("pressure_Pa", "pressure_rel"),
                ("oil_density_kg_m3", "oil_density_rel"),
                ("cunningham_b_Pa_m", "cunningham_b_rel"),
            ]:
                rel = systematic[sigma_key]
                if rel > 0:
                    sampled_constants[key] = float(sampled_constants[key]) * rng.normal(1.0, rel)
            _radius_i, charge_i, draw_flags = _charge_from_velocity(sampled_velocity, sampled_u, sampled_constants)
            if not draw_flags and charge_i is not None:
                systematic_charges.append(float(charge_i))
    sigma_systematic = float(np.std(systematic_charges, ddof=1)) if len(systematic_charges) > 1 else 0.0
    q_flags: list[str] = []
    if not (math.isfinite(sigma_random) and sigma_random > 0):
        q_flags.append("random_uncertainty_unavailable")
    if systematic_incomplete:
        q_flags.append("systematic_uncertainty_incomplete")
    sigma_total = math.sqrt(sigma_random**2 + sigma_systematic**2) if math.isfinite(sigma_random) else math.inf
    usable = bool(math.isfinite(charge) and charge > 0 and math.isfinite(sigma_total) and sigma_total > 0)
    return {
        "record_id": record_id,
        "valid": usable,
        "usable_for_inversion": usable,
        "flags": q_flags,
        "fit": velocity_fit.to_dict(),
        "result": {
            "radius_m": float(radius),
            "charge_abs_C": float(charge),
            "q_C": float(charge),
            "sigma_q_random_C": float(sigma_random),
            "sigma_q_systematic_C": float(sigma_systematic),
            "sigma_q_total_C": float(sigma_total),
            "q_ci95_low_C": float(np.percentile(random_charges, 2.5)) if random_charges else math.nan,
            "q_ci95_high_C": float(np.percentile(random_charges, 97.5)) if random_charges else math.nan,
            "random_mc_samples_used": int(len(random_charges)),
            "systematic_mc_samples_used": int(len(systematic_charges)),
            "balance_voltage_V": float(balance_voltage_V),
        },
    }
