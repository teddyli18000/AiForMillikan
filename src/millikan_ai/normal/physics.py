from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def fit_zero_v_velocity(track_rows: list[dict[str, Any]], fps: float, scale_y_m_per_px: float, cfg: dict[str, Any]) -> dict[str, Any]:
    track = pd.DataFrame(track_rows)
    if track.empty or "use_for_fit" not in track:
        return {"valid": False, "flags": ["no_track_rows"], "recovery_suggestions": ["重新框选油滴或调整 0V 时间窗口。"]}
    usable = track[(track["use_for_fit"].astype(bool)) & (track["detected"].astype(bool))].copy()
    fit_cfg = cfg["fit"]
    flags: list[str] = []
    suggestions: list[str] = []
    if len(usable) < int(fit_cfg.get("min_points", 5)):
        flags.append("too_few_fit_points")
        suggestions.append("增加 0V 下落窗口长度，或重新选择更清晰的油滴。")
    if len(usable) >= 2:
        t = usable["source_frame"].to_numpy(float) / float(fps)
        y = usable["y"].to_numpy(float)
        x = usable["x"].to_numpy(float)
        duration = float(t[-1] - t[0])
        displacement = float(y[-1] - y[0])
        slope, intercept = np.polyfit(t, y, 1)
        pred = slope * t + intercept
        residual = y - pred
        ss_res = float(np.sum(residual**2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
        rmse = math.sqrt(ss_res / max(1, len(y)))
        t_centered_ss = float(np.sum((t - float(np.mean(t))) ** 2))
        if len(y) > 2 and t_centered_ss > 0:
            residual_variance = ss_res / float(len(y) - 2)
            slope_sigma_px_s = math.sqrt(max(0.0, residual_variance / t_centered_ss))
            sigma_v_m_s = abs(float(scale_y_m_per_px)) * slope_sigma_px_s
        else:
            slope_sigma_px_s = math.nan
            sigma_v_m_s = math.nan
        x_drift = float(np.max(x) - np.min(x))
        missing_ratio = float((track["state"] == "missing").sum() / max(1, len(track)))
        velocity_m_s = float(slope * scale_y_m_per_px)
        if duration < float(fit_cfg.get("min_duration_s", 0.35)):
            flags.append("duration_too_short")
        if abs(displacement) < float(fit_cfg.get("min_displacement_px", 2.0)):
            flags.append("motion_too_small")
        if r2 < float(fit_cfg.get("min_r2", 0.55)):
            flags.append("low_r2")
        if missing_ratio > float(fit_cfg.get("max_missing_ratio", 0.55)):
            flags.append("missing_ratio_too_high")
        if velocity_m_s <= 0:
            flags.append("non_positive_downward_velocity")
            suggestions.append("确认 0V 下落窗口和视频 +Y 方向；下落应表现为 y 增大。")
    else:
        duration = displacement = r2 = rmse = x_drift = missing_ratio = velocity_m_s = math.nan
        slope = slope_sigma_px_s = sigma_v_m_s = math.nan
        ss_res = t_centered_ss = math.nan
        intercept = math.nan
        flags.append("too_few_fit_points")
    return {
        "valid": len(flags) == 0,
        "velocity_m_s": velocity_m_s,
        "slope_px_s": float(slope) if math.isfinite(float(slope)) else None,
        "slope_sigma_px_s": float(slope_sigma_px_s) if math.isfinite(float(slope_sigma_px_s)) else None,
        "sigma_v_m_s": float(sigma_v_m_s) if math.isfinite(float(sigma_v_m_s)) else None,
        "residual_ss_px2": float(ss_res) if math.isfinite(float(ss_res)) else None,
        "time_centered_ss_s2": float(t_centered_ss) if math.isfinite(float(t_centered_ss)) else None,
        "duration_s": duration,
        "displacement_px": displacement,
        "r2": r2,
        "rmse_px": rmse,
        "x_drift_px": x_drift,
        "missing_ratio": missing_ratio,
        "fit_point_count": int(len(usable)),
        "fit_start_frame": int(usable["source_frame"].min()) if len(usable) else None,
        "fit_end_frame": int(usable["source_frame"].max()) if len(usable) else None,
        "intercept_y_px": float(intercept) if math.isfinite(float(intercept)) else None,
        "flags": list(dict.fromkeys(flags)),
        "recovery_suggestions": list(dict.fromkeys(suggestions)) or [],
    }


def compute_q(fit: dict[str, Any], balance_voltage_V: float, cfg: dict[str, Any]) -> dict[str, Any]:
    flags = list(fit.get("flags", [])) if not fit.get("valid") else []
    if not math.isfinite(float(balance_voltage_V)) or float(balance_voltage_V) <= 0:
        flags.append("invalid_balance_voltage")
    velocity = float(fit.get("velocity_m_s") or math.nan)
    if not math.isfinite(velocity) or velocity <= 0:
        flags.append("invalid_velocity")
    if flags:
        return {"valid": False, "diagnostic_only": True, "flags": list(dict.fromkeys(flags)), "recovery_suggestions": fit.get("recovery_suggestions") or ["重新测量该油滴。"]}
    pcfg = cfg["physics"]
    eta = float(pcfg["air_viscosity_Pa_s"])
    rho = float(pcfg["oil_density_kg_m3"])
    g = float(pcfg["gravity_m_s2"])
    b = float(pcfg["cunningham_b_kPa_m"])
    p = float(pcfg["pressure_kPa"])
    d = float(pcfg["plate_distance_m"])
    bp = b / p
    radius = (math.sqrt(bp * bp + (18.0 * eta * velocity) / (rho * g)) - bp) / 2.0
    eta_eff = eta / (1.0 + b / (p * radius))
    charge = 6.0 * math.pi * eta_eff * radius * velocity * d / float(balance_voltage_V)
    sigma_v = float(fit.get("sigma_v_m_s") or math.nan)
    if not math.isfinite(sigma_v) or sigma_v <= 0:
        flags.append("invalid_velocity_uncertainty")
    sensitivity = 3.0 * (radius + bp) / (2.0 * radius + bp) if radius > 0 else math.nan
    sigma = abs(charge) * sensitivity * (sigma_v / velocity) if not flags and math.isfinite(sensitivity) else math.nan
    uncertainty_budget = {
        "included": [
            {
                "component": "velocity_fit_random",
                "sigma_v_m_s": float(sigma_v) if math.isfinite(sigma_v) else None,
                "relative_velocity": float(sigma_v / velocity) if math.isfinite(sigma_v) and velocity > 0 else None,
                "q_velocity_sensitivity": float(sensitivity) if math.isfinite(sensitivity) else None,
                "source": "linear-regression slope standard error propagated through q(v)",
            },
        ],
        "not_included": [
            "balance_voltage_uncertainty",
            "measurement_distance_uncertainty",
            "plate_distance_uncertainty",
            "viscosity_uncertainty",
            "pressure_uncertainty",
            "oil_density_uncertainty",
            "cunningham_b_uncertainty",
        ],
        "note": "Normal v1 reports q uncertainty from the implemented velocity-fit random term only; undefined instrument uncertainties are explicit non-included terms.",
    }
    valid = all(math.isfinite(value) and value > 0 for value in [radius, abs(charge), sigma])
    return {
        "valid": bool(valid),
        "diagnostic_only": not bool(valid),
        "q_C": float(abs(charge)),
        "charge_abs_C": float(abs(charge)),
        "sigma_q_C": float(sigma) if math.isfinite(float(sigma)) else None,
        "sigma_q_random_C": float(sigma) if math.isfinite(float(sigma)) else None,
        "uncertainty_budget": uncertainty_budget,
        "radius_m": float(radius),
        "eta_eff_Pa_s": float(eta_eff),
        "velocity_m_s": float(velocity),
        "balance_voltage_V": float(balance_voltage_V),
        "q_ci95_C": [max(0.0, abs(charge) - 1.96 * sigma), abs(charge) + 1.96 * sigma] if valid else None,
        "flags": [] if valid else list(dict.fromkeys([*flags, "invalid_q_result"])),
        "parameters": dict(pcfg),
    }
