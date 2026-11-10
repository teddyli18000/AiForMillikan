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


def _autocorrelation(values: np.ndarray, lag: int) -> float:
    if lag <= 0 or len(values) <= lag + 1:
        return 0.0
    centered = values - np.mean(values)
    denom = float(np.dot(centered, centered))
    if denom <= 0:
        return 0.0
    return float(np.dot(centered[:-lag], centered[lag:]) / denom)


def _estimate_bootstrap_block_length(residual: np.ndarray) -> tuple[int, str]:
    n = len(residual)
    if n < 8:
        return max(1, n), "insufficient_points"
    increments = np.diff(residual)
    series = increments if len(increments) >= 4 and float(np.std(increments)) > 0 else residual
    positive_corr = []
    max_lag = max(1, min(len(series) // 2, 40))
    for lag in range(1, max_lag + 1):
        rho = _autocorrelation(series, lag)
        if not math.isfinite(rho) or rho <= 0.0:
            break
        positive_corr.append(rho)
    if not positive_corr:
        fallback = max(2, min(n, int(round(math.sqrt(n)))))
        return fallback, "sqrt_n_fallback"
    tau_int = 1.0 + 2.0 * float(np.sum(positive_corr))
    block_len = max(2, min(n, int(round(tau_int))))
    return block_len, "autocorrelation"


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
) -> tuple[np.ndarray, int, str]:
    rng = np.random.default_rng(seed)
    n = len(time_s)
    block_len, block_method = _estimate_bootstrap_block_length(residual)
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
    return np.asarray(slopes, dtype=float), block_len, block_method


def fit_terminal_velocity(
    time_s: np.ndarray,
    y_px: np.ndarray,
    *,
    bootstrap_samples: int = 0,
    random_seed: int = 42,
) -> dict[str, object]:
    time_s = np.asarray(time_s, dtype=float)
    y_px = np.asarray(y_px, dtype=float)
    warnings: list[str] = []
    if len(time_s) != len(y_px):
        raise ValueError("mismatched_time_coordinate_lengths")
    if len(time_s) < 2:
        raise ValueError("insufficient_observations")
    if not (np.all(np.isfinite(time_s)) and np.all(np.isfinite(y_px))):
        raise ValueError("non_finite_time_or_coordinate")
    if np.any(np.diff(time_s) <= 0):
        raise ValueError("non_increasing_time")
    if float(np.max(time_s) - np.min(time_s)) <= 0:
        raise ValueError("zero_time_span")
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
    block_len = 0
    block_method = ""
    if bootstrap_samples > 0 and len(time_s) >= 8 and float(np.std(residual)) > 0:
        boot_slopes, block_len, block_method = _bootstrap_slopes(time_s, fitted, residual, int(bootstrap_samples), int(random_seed))
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
        "bootstrap_block_length": int(block_len),
        "bootstrap_block_length_method": block_method,
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
    boundary_guard_frames = int(config["segment"].get("boundary_guard_frames", 0))
    bootstrap_samples = int(config["segment"].get("velocity_bootstrap_samples_quick", 0))
    random_seed = int(config.get("elementary", {}).get("random_seed", 42))
    for platform in platforms.to_dict("records"):
        if platform.get("voltage_V") is None or not math.isfinite(float(platform["voltage_V"])):
            raise ValueError("missing_voltage")
        start = float(platform["start_time_s"])
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
        if len(valid) >= 2:
            valid = select_stable_window(valid, 0.0, 2)
            if not valid.empty:
                start = float(valid["time_s"].min())
                end = float(valid["time_s"].max())
                duration = max(0.0, end - start)
        if len(valid) >= 2:
            try:
                terminal = fit_terminal_velocity(
                    valid["time_s"].to_numpy(float),
                    valid["y_px"].to_numpy(float),
                    bootstrap_samples=bootstrap_samples,
                    random_seed=random_seed,
                )
            except ValueError as exc:
                terminal = {
                    "velocity_px_s": 0.0,
                    "r2_diagnostic": 0.0,
                    "rmse_px": math.inf,
                    "sigma_velocity_random_px_s": math.inf,
                    "fit_method": "input_error",
                    "uncertainty_method": "input_error",
                    "velocity_ci_95_px_s": [math.nan, math.nan],
                    "slope_first_half": math.nan,
                    "slope_second_half": math.nan,
                    "residual_autocorrelation_lag1": math.nan,
                    "bootstrap_block_length": 0,
                    "bootstrap_block_length_method": "",
                    "warnings": [str(exc)],
                }
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
                "bootstrap_block_length": 0,
                "bootstrap_block_length_method": "",
                "warnings": ["insufficient_points"],
            }
        stable = len(valid) >= 2 and math.isfinite(float(y_fit["slope"])) and terminal["fit_method"] != "input_error"
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
                "bootstrap_block_length": terminal["bootstrap_block_length"],
                "bootstrap_block_length_method": terminal["bootstrap_block_length_method"],
                "stable": stable,
                "flags": ";".join(flags + list(terminal["warnings"])),
            }
        )
    return pd.DataFrame(rows)
