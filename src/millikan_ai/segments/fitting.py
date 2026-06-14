from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import least_squares


def fit_line(time_s: np.ndarray, values: np.ndarray) -> dict[str, float]:
    if len(time_s) < 2:
        return {"slope": 0.0, "intercept": 0.0, "r2": 0.0, "rmse": math.inf, "sigma_slope": math.inf}
    coeffs, cov = np.polyfit(time_s, values, deg=1, cov=True) if len(time_s) > 2 else (np.polyfit(time_s, values, deg=1), np.zeros((2, 2)))
    slope = float(coeffs[0])
    intercept = float(coeffs[1])
    predicted = slope * time_s + intercept
    residual = values - predicted
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((values - np.mean(values)) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    rmse = math.sqrt(ss_res / len(time_s))
    sigma_slope = math.sqrt(float(cov[0, 0])) if cov.size else 0.0
    return {"slope": slope, "intercept": intercept, "r2": r2, "rmse": rmse, "sigma_slope": sigma_slope}


def select_stable_window(valid: pd.DataFrame, min_duration_s: float, min_points: int) -> pd.DataFrame:
    return valid.sort_values("time_s").reset_index(drop=True).copy()


def _lag1_autocorrelation(values: np.ndarray) -> float:
    if len(values) < 3:
        return 0.0
    centered = values - np.mean(values)
    denom = float(np.dot(centered, centered))
    if denom <= 0:
        return 0.0
    return float(np.dot(centered[:-1], centered[1:]) / denom)


def _robust_fit(time_s: np.ndarray, values: np.ndarray) -> tuple[float, float, str, list[str]]:
    warnings: list[str] = []
    initial = fit_line(time_s, values)
    slope = float(initial["slope"])
    intercept = float(initial["intercept"])
    predicted = slope * time_s + intercept
    residual = values - predicted
    scale = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
    scale = max(scale, float(initial["rmse"]), 1e-12)
    try:
        result = least_squares(
            lambda params: (params[0] + params[1] * time_s - values) / scale,
            np.array([intercept, slope], dtype=float),
            loss="huber",
            f_scale=1.0,
        )
        if not result.success:
            warnings.append("robust_fit_failed")
            return intercept, slope, "ordinary_least_squares", warnings
        return float(result.x[0]), float(result.x[1]), "robust_huber", warnings
    except Exception:
        warnings.append("robust_fit_exception")
        return intercept, slope, "ordinary_least_squares", warnings


def _analytic_sigma_slope(time_s: np.ndarray, residual: np.ndarray) -> float:
    if len(time_s) < 3:
        return math.inf
    centered_t = time_s - np.mean(time_s)
    denom = float(np.sum(centered_t**2))
    if denom <= 0:
        return math.inf
    sigma2 = float(np.sum(residual**2) / max(1, len(time_s) - 2))
    return math.sqrt(max(0.0, sigma2 / denom))


def _bootstrap_slopes(
    time_s: np.ndarray,
    fitted: np.ndarray,
    residual: np.ndarray,
    samples: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(time_s)
    block_len = max(2, min(n, int(round(math.sqrt(n)))))
    starts = np.arange(n)
    slopes = []
    for _ in range(samples):
        boot_residual: list[float] = []
        while len(boot_residual) < n:
            start = int(rng.choice(starts))
            block_indices = (start + np.arange(block_len)) % n
            boot_residual.extend(residual[block_indices].tolist())
        y_boot = fitted + np.asarray(boot_residual[:n], dtype=float)
        _intercept, slope, _method, _warnings = _robust_fit(time_s, y_boot)
        if math.isfinite(slope):
            slopes.append(float(slope))
    return np.asarray(slopes, dtype=float)


def fit_terminal_velocity(
    time_s: np.ndarray,
    y_px: np.ndarray,
    *,
    bootstrap_samples: int = 0,
    random_seed: int = 42,
) -> dict[str, object]:
    time_s = np.asarray(time_s, dtype=float)
    y_px = np.asarray(y_px, dtype=float)
    finite = np.isfinite(time_s) & np.isfinite(y_px)
    time_s = time_s[finite]
    y_px = y_px[finite]
    warnings: list[str] = []
    if len(time_s) < 2:
        return {
            "velocity_px_s": 0.0,
            "intercept_px": 0.0,
            "sigma_velocity_random_px_s": math.inf,
            "velocity_ci_95_px_s": [math.nan, math.nan],
            "fit_method": "unfit",
            "uncertainty_method": "insufficient_points",
            "num_points": int(len(time_s)),
            "duration_s": 0.0,
            "rmse_px": math.inf,
            "r2_diagnostic": 0.0,
            "slope_first_half": math.nan,
            "slope_second_half": math.nan,
            "residual_autocorrelation_lag1": math.nan,
            "warnings": ["insufficient_points"],
        }
    order = np.argsort(time_s)
    time_s = time_s[order]
    y_px = y_px[order]
    if np.any(np.diff(time_s) <= 0):
        warnings.append("non_increasing_time")
    intercept, slope, fit_method, fit_warnings = _robust_fit(time_s, y_px)
    warnings.extend(fit_warnings)
    fitted = intercept + slope * time_s
    residual = y_px - fitted
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((y_px - np.mean(y_px)) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    rmse = math.sqrt(ss_res / len(time_s))
    sigma = _analytic_sigma_slope(time_s, residual)
    ci = [slope - 1.96 * sigma, slope + 1.96 * sigma] if math.isfinite(sigma) else [math.nan, math.nan]
    uncertainty_method = "analytic_fallback"
    if bootstrap_samples > 0 and len(time_s) >= 8 and float(np.std(residual)) > 0:
        boot_slopes = _bootstrap_slopes(time_s, fitted, residual, int(bootstrap_samples), int(random_seed))
        if len(boot_slopes) >= 2:
            sigma = float(np.std(boot_slopes, ddof=1))
            ci = [float(np.percentile(boot_slopes, 2.5)), float(np.percentile(boot_slopes, 97.5))]
            uncertainty_method = "block_bootstrap"
        else:
            warnings.append("bootstrap_failed")
    midpoint = len(time_s) // 2
    first = fit_line(time_s[:midpoint], y_px[:midpoint])["slope"] if midpoint >= 2 else math.nan
    second = fit_line(time_s[midpoint:], y_px[midpoint:])["slope"] if len(time_s) - midpoint >= 2 else math.nan
    return {
        "velocity_px_s": float(slope),
        "intercept_px": float(intercept),
        "sigma_velocity_random_px_s": float(sigma),
        "velocity_ci_95_px_s": [float(ci[0]), float(ci[1])],
        "fit_method": fit_method,
        "uncertainty_method": uncertainty_method,
        "num_points": int(len(time_s)),
        "duration_s": float(time_s[-1] - time_s[0]),
        "rmse_px": float(rmse),
        "r2_diagnostic": float(r2),
        "slope_first_half": float(first),
        "slope_second_half": float(second),
        "residual_autocorrelation_lag1": _lag1_autocorrelation(residual),
        "warnings": warnings,
    }


def fit_track_segments(
    track: pd.DataFrame,
    platforms: pd.DataFrame,
    scale_y_m_per_px: float,
    config: dict,
) -> pd.DataFrame:
    rows = []
    default_video_id = str(track["video_id"].iloc[0]) if "video_id" in track and not track.empty else ""
    default_track_id = str(track["track_id"].iloc[0]) if "track_id" in track and not track.empty else ""
    transient = float(config["segment"].get("transient_drop_s", 0.0))
    boundary_guard_frames = int(config["segment"].get("boundary_guard_frames", 0))
    min_duration = float(config["segment"]["stable_min_duration_s"])
    min_points = int(config["segment"]["min_valid_points"])
    min_r2 = float(config["segment"]["min_fit_r2"])
    min_displacement = float(config["segment"].get("min_motion_displacement_px", 0))
    bootstrap_samples = int(config["segment"].get("velocity_bootstrap_samples_quick", 0))
    random_seed = int(config.get("elementary", {}).get("random_seed", 42))
    for platform in platforms.to_dict("records"):
        start = float(platform["start_time_s"]) + transient
        end = float(platform["end_time_s"])
        segment = track[(track["time_s"] >= start) & (track["time_s"] <= end)].copy()
        if boundary_guard_frames > 0 and "frame_idx" in track and "start_frame" in platform and "end_frame" in platform:
            start_frame = int(platform["start_frame"]) + boundary_guard_frames
            end_frame = int(platform["end_frame"]) - boundary_guard_frames
            segment = segment[(segment["frame_idx"] >= start_frame) & (segment["frame_idx"] <= end_frame)].copy()
            if not segment.empty:
                start = float(segment["time_s"].min())
                end = float(segment["time_s"].max())
        valid = segment[segment["is_valid_detection"].astype(bool)] if not segment.empty else segment
        flags = []
        duration = max(0.0, end - start)
        if duration < min_duration:
            flags.append("too_short")
        if len(valid) < min_points:
            flags.append("too_few_points")
        if len(valid) >= 2 and duration >= min_duration:
            valid = select_stable_window(valid, min_duration, min_points)
            if not valid.empty:
                start = float(valid["time_s"].min())
                end = float(valid["time_s"].max())
                duration = max(0.0, end - start)
        if len(valid) >= 2:
            terminal = fit_terminal_velocity(
                valid["time_s"].to_numpy(float),
                valid["y_px"].to_numpy(float),
                bootstrap_samples=bootstrap_samples,
                random_seed=random_seed,
            )
            y_fit = {
                "slope": float(terminal["velocity_px_s"]),
                "r2": float(terminal["r2_diagnostic"]),
                "rmse": float(terminal["rmse_px"]),
                "sigma_slope": float(terminal["sigma_velocity_random_px_s"]),
            }
            x_fit = fit_line(valid["time_s"].to_numpy(float), valid["x_px"].to_numpy(float))
        else:
            y_fit = {"slope": 0.0, "r2": 0.0, "rmse": math.inf, "sigma_slope": math.inf}
            x_fit = {"slope": 0.0}
            terminal = {
                "fit_method": "unfit",
                "uncertainty_method": "insufficient_points",
                "velocity_ci_95_px_s": [math.nan, math.nan],
                "slope_first_half": math.nan,
                "slope_second_half": math.nan,
                "residual_autocorrelation_lag1": math.nan,
                "warnings": ["insufficient_points"],
            }
        displacement = abs(float(y_fit["slope"])) * duration
        if displacement < min_displacement:
            flags.append("low_motion_displacement")
        if y_fit["r2"] < min_r2 and abs(y_fit["slope"]) > 0.5:
            flags.append("low_r2")
        stable = len(valid) >= 2 and math.isfinite(float(y_fit["slope"]))
        rows.append(
            {
                "video_id": str(segment["video_id"].iloc[0]) if not segment.empty else default_video_id,
                "track_id": str(segment["track_id"].iloc[0]) if not segment.empty else default_track_id,
                "platform_id": platform["platform_id"],
                "voltage_V": platform["voltage_V"],
                "start_time_s": start,
                "end_time_s": end,
                "num_points": int(len(valid)),
                "duration_s": duration,
                "vy_px_s": y_fit["slope"],
                "vy_m_s": y_fit["slope"] * scale_y_m_per_px,
                "sigma_vy": y_fit["sigma_slope"] * scale_y_m_per_px if math.isfinite(y_fit["sigma_slope"]) else math.inf,
                "velocity_ci_95_m_s": [
                    value * scale_y_m_per_px if math.isfinite(float(value)) else math.nan
                    for value in terminal["velocity_ci_95_px_s"]
                ],
                "fit_method": terminal["fit_method"],
                "uncertainty_method": terminal["uncertainty_method"],
                "vx_px_s": x_fit["slope"],
                "r2_y": y_fit["r2"],
                "rmse_y": y_fit["rmse"],
                "slope_first_half": terminal["slope_first_half"],
                "slope_second_half": terminal["slope_second_half"],
                "residual_autocorrelation_lag1": terminal["residual_autocorrelation_lag1"],
                "stable": stable,
                "flags": ";".join(flags + list(terminal["warnings"])),
            }
        )
    return pd.DataFrame(rows)
