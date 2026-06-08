from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.segments.fitting import fit_line, select_stable_window
from millikan_ai.tracking.detector import Blob, detect_blobs
from millikan_ai.tracking.fusion import KalmanPointTracker, track_lk_bidirectional
from millikan_ai.video.reader import inspect_video


@dataclass(frozen=True)
class TrackSeed:
    blob: Blob
    start_frame: int


def _distance(a: Blob, b: Blob) -> float:
    return math.hypot(a.x_px - b.x_px, a.y_px - b.y_px)


def _point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _select_detection(
    blobs: list[Blob],
    predicted: tuple[float, float],
    lk_point: tuple[float, float] | None,
    previous: Blob,
    motion: KalmanPointTracker,
    tracking_cfg: dict,
) -> Blob | None:
    max_radius = float(tracking_cfg["max_search_radius_px"])
    mahalanobis_gate = float(tracking_cfg.get("mahalanobis_gate", 6.0))
    lk_gate = float(tracking_cfg.get("lk_detection_gate_px", 12.0))
    max_area_ratio = float(tracking_cfg.get("max_area_ratio", 3.0))
    candidates: list[tuple[float, Blob]] = []
    for blob in blobs:
        predicted_distance = _point_distance((blob.x_px, blob.y_px), predicted)
        if predicted_distance > max_radius:
            continue
        lk_distance = _point_distance((blob.x_px, blob.y_px), lk_point) if lk_point is not None else float("inf")
        kalman_consistent = motion.mahalanobis_distance((blob.x_px, blob.y_px)) <= mahalanobis_gate
        lk_consistent = lk_point is not None and lk_distance <= lk_gate
        if not kalman_consistent and not lk_consistent:
            continue
        area_ratio = max(blob.area_px, previous.area_px) / max(min(blob.area_px, previous.area_px), 1e-6)
        if area_ratio > max_area_ratio:
            continue
        if lk_point is not None and not lk_consistent and predicted_distance > max_radius / 2:
            continue
        morphology_penalty = abs(math.log(max(blob.area_px, 1e-6) / max(previous.area_px, 1e-6)))
        lk_cost = lk_distance if lk_point is not None else 0.0
        cost = predicted_distance + 0.5 * lk_cost + 3.0 * morphology_penalty - 2.0 * blob.confidence
        candidates.append((cost, blob))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _collect_track_seeds(
    cap: cv2.VideoCapture,
    frame_count: int,
    microscope_roi: Roi,
    grid: GridCalibration | None,
    tracking_cfg: dict,
) -> list[TrackSeed]:
    sample_count = max(1, min(int(tracking_cfg.get("seed_sample_frames", 6)), frame_count))
    frame_indices = sorted(set(np.linspace(0, max(frame_count - 1, 0), sample_count, dtype=int).tolist()))
    min_area = float(tracking_cfg["min_blob_area_px"])
    max_area = float(tracking_cfg["max_blob_area_px"])
    min_grid_distance = float(tracking_cfg.get("seed_min_grid_line_distance_px", 0))
    min_roi_margin = float(tracking_cfg.get("min_tracking_roi_margin_px", 0))
    nms_distance = float(tracking_cfg.get("detection_nms_distance_px", 6))
    candidates: list[TrackSeed] = []
    for frame_idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        blobs = detect_blobs(
            frame,
            microscope_roi,
            min_area,
            max_area,
            grid=grid,
            min_grid_distance_px=min_grid_distance,
            min_roi_margin_px=min_roi_margin,
            nms_distance_px=nms_distance,
        )
        candidates.extend(TrackSeed(blob=blob, start_frame=frame_idx) for blob in blobs)
    candidates.sort(key=lambda seed: (seed.start_frame, -seed.blob.confidence))
    merge_distance = float(tracking_cfg.get("seed_merge_distance_px", 18))
    seeds: list[TrackSeed] = []
    for candidate in candidates:
        if any(_distance(candidate.blob, existing.blob) < merge_distance for existing in seeds):
            continue
        seeds.append(candidate)
        if len(seeds) >= int(tracking_cfg["top_k_seeds"]):
            break
    return seeds


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


def _grid_clear_fraction(rows: list[dict[str, object]], grid: GridCalibration | None, min_distance_px: float) -> float:
    if grid is None or min_distance_px <= 0:
        return 1.0
    lines = [(float(x), "x") for x in grid.grid_lines_x] + [(float(y), "y") for y in grid.grid_lines_y]
    if not lines:
        return 1.0
    valid_rows = [row for row in rows if bool(row.get("is_valid_detection"))]
    if not valid_rows:
        return 0.0
    clear = 0
    for row in valid_rows:
        x = float(row["x_px"])
        y = float(row["y_px"])
        distance = min(abs(x - value) if axis == "x" else abs(y - value) for value, axis in lines)
        if distance >= min_distance_px:
            clear += 1
    return clear / len(valid_rows)


def _roi_clear_fraction(rows: list[dict[str, object]], roi: Roi, min_margin_px: float) -> float:
    if min_margin_px <= 0:
        return 1.0
    valid_rows = [row for row in rows if bool(row.get("is_valid_detection"))]
    if not valid_rows:
        return 0.0
    left = float(roi.x)
    right = float(roi.x + roi.w)
    top = float(roi.y)
    bottom = float(roi.y + roi.h)
    clear = 0
    for row in valid_rows:
        x = float(row["x_px"])
        y = float(row["y_px"])
        margin = min(x - left, right - x, y - top, bottom - y)
        if margin >= min_margin_px:
            clear += 1
    return clear / len(valid_rows)


def _track_seed_candidates(
    video_path: str | Path,
    video_id: str,
    microscope_roi: Roi,
    platforms: pd.DataFrame,
    config: dict,
    grid: GridCalibration | None = None,
) -> tuple[dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    meta = inspect_video(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    tracking_cfg = config["tracking"]
    min_area = float(tracking_cfg["min_blob_area_px"])
    max_area = float(tracking_cfg["max_blob_area_px"])
    min_grid_distance = float(tracking_cfg.get("min_grid_line_distance_px", 0))
    min_grid_clear = float(tracking_cfg.get("min_grid_clear_fraction", 0))
    min_roi_margin = float(tracking_cfg.get("min_tracking_roi_margin_px", 0))
    min_roi_clear = float(tracking_cfg.get("min_roi_clear_fraction", 0))
    nms_distance = float(tracking_cfg.get("detection_nms_distance_px", 6))
    lk_window = int(tracking_cfg.get("lk_window_size_px", 21))
    lk_levels = int(tracking_cfg.get("lk_pyramid_levels", 3))
    lk_fb_error = float(tracking_cfg.get("lk_max_forward_backward_error_px", 1.5))
    lk_photo_error = float(tracking_cfg.get("lk_max_photometric_error", 30))
    max_missing_frames = int(tracking_cfg.get("max_missing_frames", 15))
    process_noise = float(tracking_cfg.get("kalman_process_noise", 1.0))
    measurement_noise = float(tracking_cfg.get("kalman_measurement_noise", 2.0))
    seeds = _collect_track_seeds(cap, meta.frame_count, microscope_roi, grid, tracking_cfg)
    if not seeds:
        cap.release()
        return {}, [
            {
                "candidate_id": "none",
                "usable_platform_count": 0,
                "total_duration_s": 0,
                "missing_ratio": 1,
                "score_total": 0,
                "rank": 1,
                "reject_reason": "no_seeds",
                "selected_for_multi_drop": False,
            }
        ]
    tracks: dict[str, list[dict[str, object]]] = {}
    summaries = []
    for seed_idx, track_seed in enumerate(seeds, start=1):
        seed = track_seed.blob
        cap.set(cv2.CAP_PROP_POS_FRAMES, track_seed.start_frame)
        current = seed
        motion = KalmanPointTracker(
            seed.x_px,
            seed.y_px,
            dt=1.0 / meta.fps if meta.fps else 1.0 / 30.0,
            process_noise=process_noise,
            measurement_noise=measurement_noise,
        )
        previous_gray: np.ndarray | None = None
        previous_point = (seed.x_px, seed.y_px)
        rows = []
        missing = 0
        consecutive_missing = 0
        for frame_idx in range(track_seed.start_frame, meta.frame_count):
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            predicted = motion.predict()
            lk_result = None
            if previous_gray is not None:
                lk_result = track_lk_bidirectional(
                    previous_gray,
                    gray,
                    previous_point,
                    window_size_px=lk_window,
                    pyramid_levels=lk_levels,
                    max_forward_backward_error_px=lk_fb_error,
                    max_photometric_error=lk_photo_error,
                )
            lk_point = lk_result[0] if lk_result is not None else None
            lk_prediction_gate = float(tracking_cfg.get("lk_prediction_gate_px", 12.0))
            if lk_point is not None and _point_distance(lk_point, predicted) > lk_prediction_gate:
                lk_point = None
            blobs = detect_blobs(
                frame,
                microscope_roi,
                min_area,
                max_area,
                grid=grid,
                min_grid_distance_px=min_grid_distance,
                min_roi_margin_px=min_roi_margin,
                nms_distance_px=nms_distance,
            )
            detection = _select_detection(blobs, predicted, lk_point, current, motion, tracking_cfg)
            if detection is not None:
                current = detection
                corrected = motion.correct((current.x_px, current.y_px))
                previous_point = corrected
                valid = True
                tracking_source = "detection"
                consecutive_missing = 0
            elif lk_point is not None:
                lk_weight = float(tracking_cfg.get("lk_measurement_weight", 0.25))
                fused_point = (
                    (1.0 - lk_weight) * predicted[0] + lk_weight * lk_point[0],
                    (1.0 - lk_weight) * predicted[1] + lk_weight * lk_point[1],
                )
                corrected = motion.correct(fused_point)
                current = Blob(
                    corrected[0],
                    corrected[1],
                    current.radius_px,
                    current.area_px,
                    current.brightness,
                    current.contrast,
                    current.circularity,
                    current.confidence,
                )
                previous_point = corrected
                valid = True
                tracking_source = "lk"
                consecutive_missing = 0
            else:
                missing += 1
                consecutive_missing += 1
                current = Blob(
                    predicted[0],
                    predicted[1],
                    current.radius_px,
                    current.area_px,
                    current.brightness,
                    current.contrast,
                    current.circularity,
                    current.confidence,
                )
                previous_point = predicted
                valid = False
                tracking_source = "kalman_prediction"
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
                    "tracking_source": tracking_source,
                }
            )
            previous_gray = gray
            if consecutive_missing > max_missing_frames:
                break
        missing_ratio = missing / max(len(rows), 1)
        total_duration = rows[-1]["time_s"] - rows[0]["time_s"] if len(rows) > 1 else 0.0
        x_values = np.asarray([float(row["x_px"]) for row in rows], dtype=float)
        y_values = np.asarray([float(row["y_px"]) for row in rows], dtype=float)
        steps = np.hypot(np.diff(x_values), np.diff(y_values))
        path_length = float(steps.sum())
        displacement = float(np.hypot(x_values[-1] - x_values[0], y_values[-1] - y_values[0])) if len(rows) > 1 else 0.0
        areas = np.asarray([float(row["area_px"]) for row in rows if bool(row["is_valid_detection"])], dtype=float)
        platform_count = len({row["platform_id"] for row in rows if row["platform_id"]})
        fit_usable_count, mean_r2, drift_score = _platform_fit_score(rows, platforms, config)
        coverage_basis = fit_usable_count if not platforms.empty else platform_count
        coverage_score = min(1.0, coverage_basis / max(len(platforms), 1)) if not platforms.empty else 0.0
        continuity_score = 1 - missing_ratio
        grid_clear_fraction = _grid_clear_fraction(rows, grid, min_grid_distance)
        roi_clear_fraction = _roi_clear_fraction(rows, microscope_roi, min_roi_margin)
        grid_score = 0.0 if grid_clear_fraction < min_grid_clear else grid_clear_fraction
        roi_score = 0.0 if roi_clear_fraction < min_roi_clear else roi_clear_fraction
        score = max(0.0, min(1.0, 0.25 * continuity_score + 0.30 * coverage_score + 0.20 * mean_r2 + 0.10 * drift_score + 0.075 * grid_score + 0.075 * roi_score))
        reject_reasons = []
        if not (fit_usable_count >= min(2, len(platforms)) or platforms.empty):
            reject_reasons.append("insufficient_stable_platform_fits")
        if grid_clear_fraction < min_grid_clear:
            reject_reasons.append("too_close_to_grid_lines")
        if roi_clear_fraction < min_roi_clear:
            reject_reasons.append("too_close_to_tracking_roi_edge")
        candidate_id = f"candidate_{seed_idx:03d}"
        tracks[candidate_id] = rows
        summaries.append(
            {
                "candidate_id": candidate_id,
                "usable_platform_count": platform_count,
                "total_duration_s": total_duration,
                "missing_ratio": missing_ratio,
                "score_total": score,
                "fit_usable_platform_count": fit_usable_count,
                "mean_speed_fit_r2": mean_r2,
                "drift_score": drift_score,
                "grid_clear_fraction": grid_clear_fraction,
                "roi_clear_fraction": roi_clear_fraction,
                "max_step_px": float(steps.max()) if steps.size else 0.0,
                "step_p95_px": float(np.percentile(steps, 95)) if steps.size else 0.0,
                "path_efficiency": displacement / max(path_length, 1e-9),
                "area_cv": float(areas.std() / max(areas.mean(), 1e-9)) if areas.size else 1.0,
                "rank": 0,
                "reject_reason": ",".join(reject_reasons),
                "selected_for_multi_drop": False,
            }
        )
    cap.release()
    summaries.sort(
        key=lambda row: (
            int(row["fit_usable_platform_count"]),
            int(row["usable_platform_count"]),
            float(row["total_duration_s"]),
            -float(row["missing_ratio"]),
            float(row["mean_speed_fit_r2"]),
            float(row["score_total"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(summaries, start=1):
        row["rank"] = rank
    return tracks, summaries


def _first_valid_point(rows: list[dict[str, object]]) -> tuple[float, float] | None:
    for row in rows:
        if bool(row.get("is_valid_detection")):
            return float(row["x_px"]), float(row["y_px"])
    if rows:
        return float(rows[0]["x_px"]), float(rows[0]["y_px"])
    return None


def _trajectory_distance(a: list[dict[str, object]], b: list[dict[str, object]]) -> float:
    by_frame = {int(row["frame_idx"]): row for row in b if bool(row.get("is_valid_detection"))}
    distances = []
    for row in a:
        if not bool(row.get("is_valid_detection")):
            continue
        other = by_frame.get(int(row["frame_idx"]))
        if other is None:
            continue
        distances.append(math.hypot(float(row["x_px"]) - float(other["x_px"]), float(row["y_px"]) - float(other["y_px"])))
    if not distances:
        first_a = _first_valid_point(a)
        first_b = _first_valid_point(b)
        if first_a is None or first_b is None:
            return 0.0
        return math.hypot(first_a[0] - first_b[0], first_a[1] - first_b[1])
    return float(np.median(distances))


def track_multiple_candidates(
    video_path: str | Path,
    video_id: str,
    microscope_roi: Roi,
    platforms: pd.DataFrame,
    config: dict,
    grid: GridCalibration | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    tracks, summaries = _track_seed_candidates(video_path, video_id, microscope_roi, platforms, config, grid)
    if not tracks:
        return pd.DataFrame(), pd.DataFrame(summaries)

    tracking_cfg = config["tracking"]
    max_drops = max(1, int(tracking_cfg.get("max_drops", 1)))
    min_distance = float(tracking_cfg.get("multi_drop_min_trajectory_distance_px", 20))
    selected_ids: list[str] = []
    selected_tracks: list[list[dict[str, object]]] = []
    for summary in summaries:
        candidate_id = str(summary["candidate_id"])
        rows = tracks.get(candidate_id, [])
        if not rows:
            continue
        if any(_trajectory_distance(rows, selected) < min_distance for selected in selected_tracks):
            summary["reject_reason"] = "duplicate_track"
            continue
        summary["selected_for_multi_drop"] = True
        selected_ids.append(candidate_id)
        selected_tracks.append(rows)
        if len(selected_ids) >= max_drops:
            break

    if not selected_tracks and summaries:
        best_id = str(summaries[0]["candidate_id"])
        if best_id in tracks:
            summaries[0]["selected_for_multi_drop"] = True
            selected_tracks.append(tracks[best_id])

    track_frame = pd.DataFrame([row for rows in selected_tracks for row in rows])
    return track_frame, pd.DataFrame(summaries)


def track_best_candidate(
    video_path: str | Path,
    video_id: str,
    microscope_roi: Roi,
    platforms: pd.DataFrame,
    config: dict,
    grid: GridCalibration | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    tracks, summaries = _track_seed_candidates(video_path, video_id, microscope_roi, platforms, config, grid)
    if not tracks:
        return pd.DataFrame(), pd.DataFrame(summaries)
    best_id = str(summaries[0]["candidate_id"])
    return pd.DataFrame(tracks[best_id]), pd.DataFrame(summaries)
