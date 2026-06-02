from __future__ import annotations

import math

import numpy as np
import pandas as pd


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
    if len(valid) <= min_points:
        return valid
    valid = valid.sort_values("time_s").reset_index(drop=True)
    best: tuple[float, int, int] | None = None
    times = valid["time_s"].to_numpy(float)
    for start_idx in range(0, len(valid) - min_points + 1):
        for end_idx in range(start_idx + min_points - 1, len(valid)):
            duration = times[end_idx] - times[start_idx]
            if duration < min_duration_s:
                continue
            # Prefer longer windows when fit quality is comparable.
            window = valid.iloc[start_idx : end_idx + 1]
            y_fit = fit_line(window["time_s"].to_numpy(float), window["y_px"].to_numpy(float))
            score = max(0.0, y_fit["r2"]) + min(0.1, duration / 100.0)
            if best is None or score > best[0]:
                best = (score, start_idx, end_idx)
            break
    if best is None:
        return valid
    _, start_idx, end_idx = best
    return valid.iloc[start_idx : end_idx + 1].copy()


def fit_track_segments(
    track: pd.DataFrame,
    platforms: pd.DataFrame,
    scale_y_m_per_px: float,
    config: dict,
) -> pd.DataFrame:
    rows = []
    transient = float(config["segment"]["transient_drop_s"])
    min_duration = float(config["segment"]["stable_min_duration_s"])
    min_points = int(config["segment"]["min_valid_points"])
    min_r2 = float(config["segment"]["min_fit_r2"])
    min_displacement = float(config["segment"].get("min_motion_displacement_px", 0))
    for platform in platforms.to_dict("records"):
        start = float(platform["start_time_s"]) + transient
        end = float(platform["end_time_s"])
        segment = track[(track["time_s"] >= start) & (track["time_s"] <= end)].copy()
        valid = segment[segment["is_valid_detection"].astype(bool)] if not segment.empty else segment
        flags = []
        duration = max(0.0, end - start)
        if duration < min_duration:
            flags.append("too_short")
        if len(valid) < min_points:
            flags.append("too_few_points")
        if len(valid) >= min_points and duration >= min_duration:
            valid = select_stable_window(valid, min_duration, min_points)
            if not valid.empty:
                start = float(valid["time_s"].min())
                end = float(valid["time_s"].max())
                duration = max(0.0, end - start)
        if len(valid) >= 2:
            y_fit = fit_line(valid["time_s"].to_numpy(float), valid["y_px"].to_numpy(float))
            x_fit = fit_line(valid["time_s"].to_numpy(float), valid["x_px"].to_numpy(float))
        else:
            y_fit = {"slope": 0.0, "r2": 0.0, "rmse": math.inf, "sigma_slope": math.inf}
            x_fit = {"slope": 0.0}
        displacement = abs(float(y_fit["slope"])) * duration
        if displacement < min_displacement:
            flags.append("low_motion_displacement")
        if y_fit["r2"] < min_r2 and abs(y_fit["slope"]) > 0.5:
            flags.append("low_r2")
        stable = not flags
        rows.append(
            {
                "video_id": str(segment["video_id"].iloc[0]) if not segment.empty else "",
                "track_id": str(segment["track_id"].iloc[0]) if not segment.empty else "",
                "platform_id": platform["platform_id"],
                "voltage_V": platform["voltage_V"],
                "start_time_s": start,
                "end_time_s": end,
                "num_points": int(len(valid)),
                "duration_s": duration,
                "vy_px_s": y_fit["slope"],
                "vy_m_s": y_fit["slope"] * scale_y_m_per_px,
                "sigma_vy": y_fit["sigma_slope"] * scale_y_m_per_px if math.isfinite(y_fit["sigma_slope"]) else math.inf,
                "vx_px_s": x_fit["slope"],
                "r2_y": y_fit["r2"],
                "rmse_y": y_fit["rmse"],
                "stable": stable,
                "flags": ";".join(flags),
            }
        )
    return pd.DataFrame(rows)
