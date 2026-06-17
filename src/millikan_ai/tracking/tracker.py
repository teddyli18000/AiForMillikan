from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.segments.fitting import fit_line, select_stable_window
from millikan_ai.tracking import grid_mask as grid_mask_utils
from millikan_ai.tracking.trackpy_core import (
    SingleDropTrackingConfig,
    TrackpyDropState,
    locate_features_in_roi,
    preprocess_frame_for_droplets,
)
from millikan_ai.video.reader import inspect_video


@dataclass(frozen=True)
class TrackSeed:
    x_px: float
    y_px: float
    mass: float
    size: float
    ecc: float
    start_frame: int


def _point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _trackpy_config(tracking_cfg: dict) -> SingleDropTrackingConfig:
    return SingleDropTrackingConfig(
        diameter=grid_mask_utils.ensure_odd(int(tracking_cfg.get("trackpy_diameter", tracking_cfg.get("diameter", 5)))),
        invert=bool(tracking_cfg.get("trackpy_invert", False)),
        minmass=float(tracking_cfg.get("trackpy_minmass", 80.0)),
        local_search_radius=float(tracking_cfg.get("trackpy_local_search_radius_px", tracking_cfg.get("max_search_radius_px", 45.0))),
        max_accept_distance=float(tracking_cfg.get("trackpy_max_accept_distance_px", tracking_cfg.get("max_search_radius_px", 30.0))),
        single_memory=int(tracking_cfg.get("trackpy_memory_frames", tracking_cfg.get("max_missing_frames", 5))),
        local_topn=int(tracking_cfg.get("trackpy_local_topn", 20)),
        grid_reject_dilate_px=int(tracking_cfg.get("grid_reject_dilate_px", 0)),
        grid_occlusion_radius=int(tracking_cfg.get("grid_occlusion_radius_px", tracking_cfg.get("min_grid_line_distance_px", 0))),
        skip_detection_on_grid=bool(tracking_cfg.get("skip_detection_on_grid", True)),
        max_jump_px=float(tracking_cfg.get("trackpy_max_jump_px", 0.0)),
    )


def _near_roi_edge(x_px: float, y_px: float, roi: Roi, min_margin_px: float) -> bool:
    if min_margin_px <= 0:
        return False
    return min(x_px - roi.x, roi.x + roi.w - x_px, y_px - roi.y, roi.y + roi.h - y_px) < min_margin_px


def _near_grid_mask(x_px: float, y_px: float, grid_mask: np.ndarray | None, radius_px: float) -> bool:
    if grid_mask is None or radius_px <= 0:
        return False
    height, width = grid_mask.shape[:2]
    x = int(round(x_px))
    y = int(round(y_px))
    r = int(round(radius_px))
    x0 = max(0, x - r)
    y0 = max(0, y - r)
    x1 = min(width, x + r + 1)
    y1 = min(height, y + r + 1)
    return x0 < x1 and y0 < y1 and np.count_nonzero(grid_mask[y0:y1, x0:x1]) > 0


def _feature_value(row: pd.Series, name: str, default: float = float("nan")) -> float:
    return float(row[name]) if name in row.index and pd.notna(row[name]) else default


def _build_tracking_grid_mask(
    video_path: str | Path,
    frame_shape: tuple[int, int],
    grid: GridCalibration | None,
    tracking_cfg: dict,
) -> tuple[np.ndarray | None, dict[str, object]]:
    dilate_px = int(tracking_cfg.get("grid_reject_dilate_px", tracking_cfg.get("min_grid_line_distance_px", 0)))
    use_static = bool(tracking_cfg.get("trackpy_static_grid_mask_enabled", True))
    static_mask = None
    static_status = "disabled"
    if use_static:
        try:
            static_mask = grid_mask_utils.build_static_grid_mask(
                video_path,
                start_frame=0,
                max_frames=int(tracking_cfg.get("trackpy_grid_mask_max_frames", 160)),
                roi=None,
            )
            static_status = "ok" if static_mask is not None else "disabled_coverage"
        except Exception as exc:
            static_status = f"failed:{type(exc).__name__}"
            static_mask = None
    calibration_mask = grid_mask_utils.build_grid_mask_from_calibration(frame_shape, grid, dilate_px=dilate_px)
    if static_mask is not None and calibration_mask is not None:
        mask = cv2.bitwise_or(static_mask, calibration_mask)
        source = "static_or_calibration"
    elif static_mask is not None:
        mask = static_mask
        source = "static"
    else:
        mask = calibration_mask
        source = "calibration" if calibration_mask is not None else "none"
    diagnostics = {
        "source": source,
        "static_status": static_status,
        "coverage": float(np.count_nonzero(mask)) / float(mask.size) if mask is not None else 0.0,
    }
    return mask, diagnostics


def _collect_trackpy_seeds(
    video_path: str | Path,
    frame_count: int,
    microscope_roi: Roi,
    tracking_cfg: dict,
    track_config: SingleDropTrackingConfig,
    grid_mask: np.ndarray | None,
) -> list[TrackSeed]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    sample_count = max(1, min(int(tracking_cfg.get("seed_sample_frames", 6)), frame_count))
    frame_indices = sorted(set(np.linspace(0, max(frame_count - 1, 0), sample_count, dtype=int).tolist()))
    min_roi_margin = float(tracking_cfg.get("min_tracking_roi_margin_px", 0))
    min_grid_distance = float(tracking_cfg.get("seed_min_grid_line_distance_px", tracking_cfg.get("min_grid_line_distance_px", 0)))
    candidates: list[TrackSeed] = []
    for frame_idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = preprocess_frame_for_droplets(frame, None)
        features = locate_features_in_roi(gray, microscope_roi, track_config, grid_mask=grid_mask)
        if features.empty:
            continue
        sort_column = "mass" if "mass" in features.columns else "signal"
        if sort_column in features.columns:
            features = features.sort_values(sort_column, ascending=False)
        for _, row in features.iterrows():
            x = float(row["x"])
            y = float(row["y"])
            if _near_roi_edge(x, y, microscope_roi, min_roi_margin):
                continue
            if _near_grid_mask(x, y, grid_mask, min_grid_distance):
                continue
            candidates.append(
                TrackSeed(
                    x_px=x,
                    y_px=y,
                    mass=_feature_value(row, "mass"),
                    size=_feature_value(row, "size"),
                    ecc=_feature_value(row, "ecc"),
                    start_frame=int(frame_idx),
                )
            )
    cap.release()
    candidates.sort(key=lambda seed: (seed.start_frame, -float(seed.mass if np.isfinite(seed.mass) else 0.0)))
    merge_distance = float(tracking_cfg.get("seed_merge_distance_px", 18))
    seeds: list[TrackSeed] = []
    for candidate in candidates:
        if any(_point_distance((candidate.x_px, candidate.y_px), (existing.x_px, existing.y_px)) < merge_distance for existing in seeds):
            continue
        seeds.append(candidate)
        if len(seeds) >= int(tracking_cfg.get("top_k_seeds", 30)):
            break
    return seeds


def _platform_fit_score(rows: list[dict[str, object]], platforms: pd.DataFrame, config: dict) -> tuple[int, float, float]:
    if not rows or platforms.empty:
        return 0, 0.0, 0.0
    frame = pd.DataFrame(rows)
    min_duration = float(config["segment"]["stable_min_duration_s"])
    min_points = int(config["segment"]["min_valid_points"])
    min_r2 = float(config["segment"]["min_fit_r2"])
    min_displacement = float(config["segment"].get("min_motion_displacement_px", 0))
    usable = 0
    r2_values = []
    vx_values = []
    for platform in platforms.to_dict("records"):
        start = float(platform["start_time_s"])
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


def _summarize_track(
    candidate_id: str,
    rows: list[dict[str, object]],
    platforms: pd.DataFrame,
    config: dict,
    grid: GridCalibration | None,
    roi: Roi,
) -> dict[str, object]:
    valid_rows = [row for row in rows if bool(row.get("is_valid_detection"))]
    invalid_count = len(rows) - len(valid_rows)
    missing_ratio = invalid_count / max(len(rows), 1)
    total_duration = float(rows[-1]["time_s"] - rows[0]["time_s"]) if len(rows) > 1 else 0.0
    if valid_rows:
        x_values = np.asarray([float(row["x_px"]) for row in valid_rows], dtype=float)
        y_values = np.asarray([float(row["y_px"]) for row in valid_rows], dtype=float)
        times = np.asarray([float(row["time_s"]) for row in valid_rows], dtype=float)
    else:
        x_values = np.asarray([], dtype=float)
        y_values = np.asarray([], dtype=float)
        times = np.asarray([], dtype=float)
    steps = np.hypot(np.diff(x_values), np.diff(y_values)) if len(x_values) > 1 else np.asarray([], dtype=float)
    path_length = float(steps.sum()) if steps.size else 0.0
    displacement = float(np.hypot(x_values[-1] - x_values[0], y_values[-1] - y_values[0])) if len(x_values) > 1 else 0.0
    platform_count = len({row["platform_id"] for row in valid_rows if row.get("platform_id")})
    fit_usable_count, mean_r2, drift_score = _platform_fit_score(rows, platforms, config)
    coverage_basis = fit_usable_count if not platforms.empty else platform_count
    coverage_score = min(1.0, coverage_basis / max(len(platforms), 1)) if not platforms.empty else min(1.0, total_duration / 3.0)
    continuity_score = 1.0 - missing_ratio
    min_grid_distance = float(config["tracking"].get("min_grid_line_distance_px", 0))
    min_grid_clear = float(config["tracking"].get("min_grid_clear_fraction", 0))
    min_roi_margin = float(config["tracking"].get("min_tracking_roi_margin_px", 0))
    min_roi_clear = float(config["tracking"].get("min_roi_clear_fraction", 0))
    grid_clear_fraction = _grid_clear_fraction(rows, grid, min_grid_distance)
    roi_clear_fraction = _roi_clear_fraction(rows, roi, min_roi_margin)
    grid_score = 0.0 if grid_clear_fraction < min_grid_clear else grid_clear_fraction
    roi_score = 0.0 if roi_clear_fraction < min_roi_clear else roi_clear_fraction
    masses = np.asarray([float(row["mass"]) for row in valid_rows if np.isfinite(float(row.get("mass", np.nan)))], dtype=float)
    mass_cv = float(masses.std() / max(abs(masses.mean()), 1e-9)) if masses.size else 1.0
    if len(times) >= 2:
        y_fit = fit_line(times, y_values)
        x_fit = fit_line(times, x_values)
    else:
        y_fit = {"slope": 0.0, "r2": 0.0, "rmse": 0.0}
        x_fit = {"slope": 0.0}
    morphology_score = 1.0 / (1.0 + mass_cv)
    score = max(
        0.0,
        min(
            1.0,
            0.24 * continuity_score
            + 0.26 * coverage_score
            + 0.18 * max(0.0, min(1.0, float(y_fit["r2"])))
            + 0.10 * drift_score
            + 0.08 * grid_score
            + 0.08 * roi_score
            + 0.06 * morphology_score,
        ),
    )
    reject_reasons = []
    if not (fit_usable_count >= min(2, len(platforms)) or platforms.empty):
        reject_reasons.append("insufficient_stable_platform_fits")
    if grid_clear_fraction < min_grid_clear:
        reject_reasons.append("too_close_to_grid_lines")
    if roi_clear_fraction < min_roi_clear:
        reject_reasons.append("too_close_to_tracking_roi_edge")
    end_reason = str(rows[-1].get("end_reason") or "video_end") if rows else "empty"
    return {
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
        "num_points": len(valid_rows),
        "duration_s": total_duration,
        "blocked_by_grid_count": sum(1 for row in rows if bool(row.get("blocked_by_grid"))),
        "max_step_px": float(steps.max()) if steps.size else 0.0,
        "step_p95_px": float(np.percentile(steps, 95)) if steps.size else 0.0,
        "path_efficiency": displacement / max(path_length, 1e-9),
        "vy_px_s": float(y_fit["slope"]),
        "vx_px_s": float(x_fit["slope"]),
        "r2_y": float(y_fit["r2"]),
        "rmse_y": float(y_fit["rmse"]),
        "mass_cv": mass_cv,
        "end_reason": end_reason,
        "rank": 0,
        "reject_reason": ",".join(reject_reasons),
        "duplicate_of": "",
        "selected_for_multi_drop": False,
    }


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
    track_config = _trackpy_config(tracking_cfg)
    ok, first_frame = cap.read()
    if not ok:
        cap.release()
        return {}, []
    frame_shape = first_frame.shape[:2]
    grid_mask, _grid_mask_diagnostics = _build_tracking_grid_mask(video_path, frame_shape, grid, tracking_cfg)
    seeds = _collect_trackpy_seeds(video_path, meta.frame_count, microscope_roi, tracking_cfg, track_config, grid_mask)
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

    seeds_by_frame: dict[int, list[tuple[int, TrackSeed]]] = {}
    for seed_idx, seed in enumerate(seeds, start=1):
        seeds_by_frame.setdefault(seed.start_frame, []).append((seed_idx, seed))

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    active: list[TrackpyDropState] = []
    completed: list[TrackpyDropState] = []
    for frame_idx in range(meta.frame_count):
        ok, frame = cap.read()
        if not ok:
            break
        gray = preprocess_frame_for_droplets(frame, None)
        for seed_idx, seed in seeds_by_frame.get(frame_idx, []):
            active.append(
                TrackpyDropState(
                    track_id=f"candidate_{seed_idx:03d}",
                    video_id=video_id,
                    start_frame=frame_idx,
                    initial_position=np.array([seed.x_px, seed.y_px], dtype=float),
                    config=track_config,
                    roi=microscope_roi,
                    fps=meta.fps or 30.0,
                )
            )
        next_active = []
        for state in active:
            state.step(gray, frame_idx, grid_mask=grid_mask, platforms=platforms)
            if state.active:
                next_active.append(state)
            else:
                completed.append(state)
        active = next_active
    cap.release()
    for state in active:
        state.finish_at_video_end()
        completed.append(state)

    tracks: dict[str, list[dict[str, object]]] = {}
    summaries: list[dict[str, object]] = []
    for state in completed:
        if not state.rows:
            continue
        tracks[state.track_id] = state.rows
        summaries.append(_summarize_track(state.track_id, state.rows, platforms, config, grid, microscope_roi))
    summaries.sort(
        key=lambda row: (
            int(row.get("fit_usable_platform_count", 0)),
            int(row.get("usable_platform_count", 0)),
            float(row.get("score_total", 0.0)),
            float(row.get("total_duration_s", 0.0)),
            -float(row.get("missing_ratio", 1.0)),
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
            return float("inf")
        return math.hypot(first_a[0] - first_b[0], first_a[1] - first_b[1])
    return float(np.median(distances))


def _deduplicate_track_candidates(
    tracks: dict[str, list[dict[str, object]]],
    summaries: list[dict[str, object]],
    max_drops: int,
    min_distance_px: float,
) -> list[str]:
    selected_ids: list[str] = []
    selected_tracks: list[list[dict[str, object]]] = []
    for summary in summaries:
        candidate_id = str(summary.get("candidate_id", ""))
        rows = tracks.get(candidate_id, [])
        if not rows:
            continue
        if not _summary_selectable_for_evaluation(summary):
            summary["selected_for_multi_drop"] = False
            continue
        duplicate_of = ""
        for selected_id, selected_rows in zip(selected_ids, selected_tracks):
            if _trajectory_distance(rows, selected_rows) < min_distance_px:
                duplicate_of = selected_id
                break
        if duplicate_of:
            summary["reject_reason"] = "duplicate_track"
            summary["duplicate_of"] = duplicate_of
            summary["selected_for_multi_drop"] = False
            continue
        summary["selected_for_multi_drop"] = True
        selected_ids.append(candidate_id)
        selected_tracks.append(rows)
        if len(selected_ids) >= max_drops:
            break
    return selected_ids


def _summary_selectable_for_evaluation(summary: dict[str, object]) -> bool:
    if int(summary.get("usable_platform_count", 0) or 0) > 0 and int(summary.get("fit_usable_platform_count", 0) or 0) <= 0:
        return False
    return True


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
    selected_ids = _deduplicate_track_candidates(
        tracks,
        summaries,
        max_drops=max(1, int(tracking_cfg.get("max_drops", 1))),
        min_distance_px=float(tracking_cfg.get("multi_drop_min_trajectory_distance_px", 20)),
    )
    if not selected_ids and summaries:
        best_id = str(summaries[0]["candidate_id"])
        if best_id in tracks:
            summaries[0]["selected_for_multi_drop"] = True
            selected_ids = [best_id]
    selected_tracks = [tracks[track_id] for track_id in selected_ids if track_id in tracks]
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
