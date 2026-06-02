from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import Roi
from millikan_ai.segments.fitting import fit_line, select_stable_window
from millikan_ai.tracking.detector import Blob, detect_blobs
from millikan_ai.video.reader import inspect_video


def _distance(a: Blob, b: Blob) -> float:
    return math.hypot(a.x_px - b.x_px, a.y_px - b.y_px)


def _platform_fit_score(rows: list[dict[str, object]], platforms: pd.DataFrame, config: dict) -> tuple[int, float, float]:
    if not rows or platforms.empty:
        return 0, 0.0, 0.0
    frame = pd.DataFrame(rows)
    transient = float(config["segment"]["transient_drop_s"])
    min_duration = float(config["segment"]["stable_min_duration_s"])
    min_points = int(config["segment"]["min_valid_points"])
    min_r2 = float(config["segment"]["min_fit_r2"])
    min_displacement = float(config["segment"].get("min_motion_displacement_px", 0))
    usable = 0
    r2_values = []
    vx_values = []
    for platform in platforms.to_dict("records"):
        start = float(platform["start_time_s"]) + transient
        end = float(platform["end_time_s"])
        segment = frame[(frame["time_s"] >= start) & (frame["time_s"] <= end) & (frame["is_valid_detection"].astype(bool))]
        if len(segment) < max(2, min_points):
            continue
        segment = select_stable_window(segment, min_duration, min_points)
        y_fit = fit_line(segment["time_s"].to_numpy(float), segment["y_px"].to_numpy(float))
        x_fit = fit_line(segment["time_s"].to_numpy(float), segment["x_px"].to_numpy(float))
        duration = float(segment["time_s"].max() - segment["time_s"].min())
        if abs(y_fit["slope"]) * duration < min_displacement:
            continue
        r2_values.append(max(0.0, min(1.0, y_fit["r2"])))
        vx_values.append(abs(x_fit["slope"]))
        if y_fit["r2"] >= min_r2:
            usable += 1
    mean_r2 = float(np.mean(r2_values)) if r2_values else 0.0
    mean_abs_vx = float(np.mean(vx_values)) if vx_values else 0.0
    drift_score = 1.0 / (1.0 + mean_abs_vx / 3.0)
    return usable, mean_r2, drift_score


def track_best_candidate(
    video_path: str | Path,
    video_id: str,
    microscope_roi: Roi,
    platforms: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    meta = inspect_video(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    tracking_cfg = config["tracking"]
    min_area = float(tracking_cfg["min_blob_area_px"])
    max_area = float(tracking_cfg["max_blob_area_px"])
    max_radius = float(tracking_cfg["max_search_radius_px"])
    ok, frame = cap.read()
    if not ok:
        cap.release()
        return pd.DataFrame(), pd.DataFrame()
    seeds = detect_blobs(frame, microscope_roi, min_area, max_area)[: int(tracking_cfg["top_k_seeds"])]
    if not seeds:
        cap.release()
        return pd.DataFrame(), pd.DataFrame(
            [{"candidate_id": "none", "usable_platform_count": 0, "total_duration_s": 0, "missing_ratio": 1, "score_total": 0, "rank": 1, "reject_reason": "no_seeds"}]
        )
    tracks: list[list[dict[str, object]]] = []
    summaries = []
    for seed_idx, seed in enumerate(seeds[: min(10, len(seeds))], start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        current = seed
        rows = []
        missing = 0
        for frame_idx in range(meta.frame_count):
            ok, frame = cap.read()
            if not ok:
                break
            blobs = detect_blobs(frame, microscope_roi, min_area, max_area)
            nearest = min(blobs, key=lambda blob: _distance(blob, current), default=None)
            valid = nearest is not None and _distance(nearest, current) <= max_radius
            if valid:
                current = nearest
            else:
                missing += 1
            time_s = frame_idx / meta.fps if meta.fps else 0.0
            platform_id = ""
            voltage = np.nan
            if not platforms.empty:
                hit = platforms[(platforms["start_time_s"] <= time_s) & (platforms["end_time_s"] >= time_s)]
                if not hit.empty:
                    platform_id = str(hit.iloc[0]["platform_id"])
                    voltage = float(hit.iloc[0]["voltage_V"])
            rows.append(
                {
                    "video_id": video_id,
                    "track_id": f"candidate_{seed_idx:03d}",
                    "frame_idx": frame_idx,
                    "time_s": time_s,
                    "x_px": current.x_px,
                    "y_px": current.y_px,
                    "radius_px": current.radius_px,
                    "area_px": current.area_px,
                    "brightness": current.brightness,
                    "voltage_V": voltage,
                    "platform_id": platform_id,
                    "is_valid_detection": valid,
                    "tracking_source": "detection" if valid else "last_known",
                }
            )
        missing_ratio = missing / max(len(rows), 1)
        total_duration = rows[-1]["time_s"] - rows[0]["time_s"] if len(rows) > 1 else 0.0
        platform_count = len({row["platform_id"] for row in rows if row["platform_id"]})
        fit_usable_count, mean_r2, drift_score = _platform_fit_score(rows, platforms, config)
        coverage_basis = fit_usable_count if not platforms.empty else platform_count
        coverage_score = min(1.0, coverage_basis / max(len(platforms), 1)) if not platforms.empty else 0.0
        continuity_score = 1 - missing_ratio
        score = max(0.0, min(1.0, 0.35 * continuity_score + 0.35 * coverage_score + 0.20 * mean_r2 + 0.10 * drift_score))
        tracks.append(rows)
        summaries.append(
            {
                "candidate_id": f"candidate_{seed_idx:03d}",
                "usable_platform_count": platform_count,
                "total_duration_s": total_duration,
                "missing_ratio": missing_ratio,
                "score_total": score,
                "fit_usable_platform_count": fit_usable_count,
                "mean_speed_fit_r2": mean_r2,
                "drift_score": drift_score,
                "rank": 0,
                "reject_reason": "" if fit_usable_count >= min(2, len(platforms)) or platforms.empty else "insufficient_stable_platform_fits",
            }
        )
    cap.release()
    summaries.sort(key=lambda row: row["score_total"], reverse=True)
    for rank, row in enumerate(summaries, start=1):
        row["rank"] = rank
    best_id = summaries[0]["candidate_id"]
    best_rows = next(rows for rows in tracks if rows and rows[0]["track_id"] == best_id)
    return pd.DataFrame(best_rows), pd.DataFrame(summaries)
