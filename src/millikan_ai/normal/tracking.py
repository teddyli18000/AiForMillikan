from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
import trackpy as tp

from .grid import build_grid_mask


@dataclass(frozen=True)
class TrackRequest:
    video_path: str
    target_frame: int
    fall_start_frame: int
    fall_end_frame: int
    source_center: tuple[float, float]
    source_video_box: dict[str, float]
    grid: dict[str, Any]
    run_dir: str
    config: dict[str, Any]


def run_tracking(request: TrackRequest) -> dict[str, Any]:
    run_dir = Path(request.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    frames, fps = _read_frames(request.video_path, request.target_frame, request.fall_end_frame)
    grid_mask = None
    if request.grid.get("grid_lines_y"):
        gray0 = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        grid_mask = build_grid_mask(gray0, [int(y) for y in request.grid["grid_lines_y"]], int(request.config["tracking"].get("grid_reject_dilate_px", 0)))
    track = track_single_drop_frames(
        frames=frames,
        initial_position=np.array(request.source_center, dtype=float),
        source_start_frame=request.target_frame,
        config=request.config["tracking"],
        grid_mask=grid_mask,
    )
    track = _mark_legal_and_fit_window(track, request.fall_start_frame, request.fall_end_frame, request.grid)
    crossings = crossing_events(track)
    fit = fit_fall_velocity(track, fps, request.config["fit"])
    layers = visualization_layers(track, crossings, request, fps)
    track_csv = run_dir / "track.csv"
    track_json = run_dir / "track.json"
    events_json = run_dir / "crossing_events.json"
    layers_json = run_dir / "visualization_layers.json"
    fit_json = run_dir / "fit_result.json"
    track.to_csv(track_csv, index=False)
    track_json.write_text(json.dumps(_records(track), ensure_ascii=False, indent=2), encoding="utf-8")
    events_json.write_text(json.dumps(crossings, ensure_ascii=False, indent=2), encoding="utf-8")
    layers_json.write_text(json.dumps(layers, ensure_ascii=False, indent=2), encoding="utf-8")
    fit_json.write_text(json.dumps(fit, ensure_ascii=False, indent=2), encoding="utf-8")
    overlay_path = run_dir / "overlay_review.mp4"
    make_overlay_video(request.video_path, track, overlay_path, request.target_frame, request.fall_end_frame, request.grid)
    return {
        "track_csv": str(track_csv),
        "track_json": str(track_json),
        "crossing_events_json": str(events_json),
        "visualization_layers_json": str(layers_json),
        "fit_result_json": str(fit_json),
        "overlay_mp4": str(overlay_path),
        "track": _records(track),
        "crossing_events": crossings,
        "visualization_layers": layers,
        "fit": fit,
    }


def track_single_drop_frames(frames: list, initial_position: np.ndarray, source_start_frame: int, config: dict[str, Any], grid_mask=None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    search_center = initial_position.astype(float)
    last_detected_position = initial_position.astype(float)
    last_detected_frame = 0
    velocity = np.array([0.0, 0.0], dtype=float)
    missing_count = 0
    was_missing = False
    for frame_id, frame in enumerate(frames):
        gray = preprocess(frame)
        if frame_id == 0:
            rows.append(_row(frame_id, source_start_frame, initial_position, initial_position, "tracking", 0, False, math.nan, "manual_target"))
            continue
        predicted = search_center + velocity
        search_radius = min(float(config.get("max_search_radius_px", 90.0)), float(config.get("local_search_radius_px", 45.0)) + missing_count * 4.0)
        near_grid = is_position_near_grid(predicted, grid_mask, int(config.get("grid_occlusion_radius_px", 0)))
        chosen = None if near_grid and bool(config.get("skip_detection_on_grid", True)) else choose_nearest_feature(
            locate_features_near_position(gray, predicted, search_radius, config, grid_mask),
            predicted,
            float(config.get("max_accept_distance_px", 30.0)) + missing_count * 3.0,
        )
        if chosen is None:
            missing_count += 1
            was_missing = True
            search_center = predicted.copy()
            rows.append(_row(frame_id, source_start_frame + frame_id, np.array([math.nan, math.nan]), predicted, "missing", missing_count, near_grid, math.nan, "grid" if near_grid else "not_found"))
            if missing_count > int(config.get("memory_frames", 5)):
                break
            continue
        current = np.array([float(chosen["x"]), float(chosen["y"])], dtype=float)
        frame_gap = max(1, frame_id - last_detected_frame)
        new_velocity = (current - last_detected_position) / frame_gap
        had_missing = was_missing
        state = "reacquired" if had_missing else "tracking"
        reason = ""
        if state == "reacquired":
            reason = _reacquire_reason(current, predicted, last_detected_position, new_velocity, velocity, config)
            if reason:
                rows.append(_row(frame_id, source_start_frame + frame_id, current, predicted, "rejected_reacquired", missing_count, near_grid, float(chosen.get("mass", math.nan)), reason))
                break
        velocity = new_velocity
        last_detected_position = current.copy()
        last_detected_frame = frame_id
        search_center = current.copy()
        rows.append(_row(frame_id, source_start_frame + frame_id, current, predicted, state, 0, near_grid, float(chosen.get("mass", math.nan)), reason))
        was_missing = False
        missing_count = 0
    return pd.DataFrame(rows)


def preprocess(frame) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (3, 3), 0)


def locate_features_near_position(gray, center, radius: float, config: dict[str, Any], grid_mask=None) -> pd.DataFrame:
    h, w = gray.shape[:2]
    cx, cy = float(center[0]), float(center[1])
    x0, y0 = max(0, int(cx - radius)), max(0, int(cy - radius))
    x1, y1 = min(w, int(cx + radius + 1)), min(h, int(cy + radius + 1))
    crop = gray[y0:y1, x0:x1].copy()
    diameter = _ensure_odd(int(config.get("diameter", 5)))
    if crop.shape[0] < diameter + 2 or crop.shape[1] < diameter + 2:
        return pd.DataFrame()
    reject_mask = None
    if grid_mask is not None:
        reject_mask = np.where(grid_mask[y0:y1, x0:x1] > 0, 255, 0).astype(np.uint8)
        if np.count_nonzero(reject_mask):
            valid_pixels = crop[reject_mask == 0]
            fill = np.median(valid_pixels) if valid_pixels.size else np.median(crop)
            crop[reject_mask > 0] = np.uint8(fill)
    features = tp.locate(
        crop,
        diameter=diameter,
        minmass=float(config.get("minmass", 80.0)),
        invert=bool(config.get("invert", False)),
        topn=int(config.get("local_topn", 20)),
        characterize=False,
    )
    if features is None or len(features) == 0:
        return pd.DataFrame()
    features = features.copy()
    if reject_mask is not None:
        keep = []
        for _, row in features.iterrows():
            lx, ly = int(round(row["x"])), int(round(row["y"]))
            keep.append(0 <= lx < reject_mask.shape[1] and 0 <= ly < reject_mask.shape[0] and reject_mask[ly, lx] == 0)
        features = features.loc[keep].copy()
    if len(features) == 0:
        return pd.DataFrame()
    features["x"] = features["x"] + x0
    features["y"] = features["y"] + y0
    return features


def choose_nearest_feature(features: pd.DataFrame, predicted_position: np.ndarray, max_distance: float):
    if features is None or len(features) == 0:
        return None
    features = features.copy()
    features["distance_to_prediction"] = np.hypot(features["x"] - predicted_position[0], features["y"] - predicted_position[1])
    nearest = features.sort_values("distance_to_prediction").iloc[0]
    return None if float(nearest["distance_to_prediction"]) > max_distance else nearest


def is_position_near_grid(position, grid_mask, radius: int) -> bool:
    if grid_mask is None:
        return False
    x, y = int(round(position[0])), int(round(position[1]))
    h, w = grid_mask.shape[:2]
    r = max(0, int(radius))
    x0, x1 = max(0, x - r), min(w, x + r + 1)
    y0, y1 = max(0, y - r), min(h, y + r + 1)
    return x0 < x1 and y0 < y1 and bool(np.count_nonzero(grid_mask[y0:y1, x0:x1]))


def fit_fall_velocity(track: pd.DataFrame, fps: float, cfg: dict[str, Any]) -> dict[str, Any]:
    usable = track[(track["use_for_fit"].astype(bool)) & (track["state"].isin(["tracking", "reacquired"]))].copy()
    flags: list[str] = []
    suggestions: list[str] = []
    if len(usable) < int(cfg.get("min_points", 12)):
        flags.append("too_few_fit_points")
        suggestions.append("重新选择更清晰的油滴，或把结束时间向前调到追踪仍稳定的位置。")
    if len(usable) >= 2:
        t = usable["source_frame"].to_numpy(float) / fps
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
        x_drift = float(np.max(x) - np.min(x))
        if duration < float(cfg.get("min_duration_s", 0.8)):
            flags.append("duration_too_short")
            suggestions.append("把结束时间向后移动到合法区域内，增加下落持续时间。")
        if displacement < float(cfg.get("min_displacement_px", 8.0)):
            flags.append("motion_too_small")
            suggestions.append("选择下落更明显的油滴，或检查是否选在平衡阶段。")
        if r2 < float(cfg.get("min_r2", 0.90)):
            flags.append("low_r2")
            suggestions.append("调整结束时间，排除串号、出界或穿越后不稳定尾段。")
        if rmse > float(cfg.get("max_rmse_px", 3.5)):
            flags.append("rmse_too_high")
        if x_drift > float(cfg.get("max_x_drift_px", 30.0)):
            flags.append("x_drift_too_large")
            suggestions.append("疑似串到其他油滴；请重新框选目标或缩短追踪窗口。")
        missing_ratio = float((track["state"] == "missing").sum() / max(1, len(track)))
        if missing_ratio > float(cfg.get("max_missing_ratio", 0.35)):
            flags.append("missing_ratio_too_high")
        if len(usable) >= 6:
            mid = len(usable) // 2
            s1 = np.polyfit(t[:mid], y[:mid], 1)[0]
            s2 = np.polyfit(t[mid:], y[mid:], 1)[0]
            ratio = max(abs(s1), abs(s2)) / max(1e-9, min(abs(s1), abs(s2)))
            if ratio > float(cfg.get("max_half_velocity_ratio", 2.2)):
                flags.append("half_velocity_inconsistent")
        velocity_m_s = float(slope * float(track.attrs.get("scale_y_m_per_px", 1.0)))
    else:
        duration = displacement = r2 = rmse = x_drift = velocity_m_s = math.nan
        flags.append("too_few_fit_points")
    if math.isfinite(velocity_m_s) and velocity_m_s <= 0:
        flags.append("non_positive_downward_velocity")
        suggestions.append("请确认视频方向和窗口：0V 下落段应表现为 +Y 方向下落。")
    return {
        "valid": len(flags) == 0,
        "velocity_m_s": velocity_m_s,
        "duration_s": duration,
        "displacement_px": displacement,
        "r2": r2,
        "rmse_px": rmse,
        "x_drift_px": x_drift,
        "fit_start_frame": int(usable["source_frame"].min()) if len(usable) else None,
        "fit_end_frame": int(usable["source_frame"].max()) if len(usable) else None,
        "fit_point_count": int(len(usable)),
        "flags": list(dict.fromkeys(flags)),
        "recovery_suggestions": list(dict.fromkeys(suggestions)) or ["保留为诊断记录，重新测量另一颗油滴。"],
    }


def crossing_events(track: pd.DataFrame) -> list[dict[str, Any]]:
    events = []
    missing_runs = []
    current = []
    for _, row in track.iterrows():
        if row["state"] == "missing":
            current.append(int(row["source_frame"]))
        elif current:
            missing_runs.append(current)
            current = []
    if current:
        missing_runs.append(current)
    for index, run in enumerate(missing_runs):
        before = max(0, run[0] - 6)
        after = run[-1] + 8
        events.append({
            "id": f"crossing_{index+1:03d}",
            "start_frame": int(run[0]),
            "end_frame": int(run[-1]),
            "review_start_frame": int(before),
            "review_end_frame": int(after),
            "kind": "missing_reacquire_window",
        })
    return events


def visualization_layers(track: pd.DataFrame, crossings: list[dict[str, Any]], request: TrackRequest, fps: float) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "frame": {"fps": fps},
        "target_box": request.source_video_box,
        "grid": {
            "second_line_y": request.grid.get("second_line_y"),
            "penultimate_line_y": request.grid.get("penultimate_line_y"),
            "grid_lines_y": request.grid.get("grid_lines_y", []),
        },
        "fit_window": {"start_frame": request.fall_start_frame, "end_frame": request.fall_end_frame},
        "track": _records(track),
        "crossing_events": crossings,
    }


def make_overlay_video(video_path: str, track: pd.DataFrame, out_path: Path, start_frame: int, end_frame: int, grid: dict[str, Any]) -> None:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    ok, first = cap.read()
    if not ok:
        raise RuntimeError("cannot read overlay first frame")
    h, w = first.shape[:2]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    by_frame = {int(row.source_frame): row for row in track.itertuples()}
    points: list[tuple[int, int]] = []
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    for frame_idx in range(start_frame, end_frame + 1):
        ok, frame = cap.read()
        if not ok:
            break
        for y in [grid.get("second_line_y"), grid.get("penultimate_line_y")]:
            if y is not None:
                cv2.line(frame, (0, int(y)), (w - 1, int(y)), (255, 180, 0), 2)
        row = by_frame.get(frame_idx)
        if row is not None:
            color = (0, 220, 0) if row.state == "tracking" else (255, 180, 0) if row.state == "reacquired" else (0, 220, 255)
            x = row.x if math.isfinite(float(row.x)) else row.pred_x
            y = row.y if math.isfinite(float(row.y)) else row.pred_y
            cv2.circle(frame, (int(round(x)), int(round(y))), 7, color, 2)
            if row.state in {"tracking", "reacquired"}:
                points.append((int(round(row.x)), int(round(row.y))))
        for a, b in zip(points[:-1], points[1:]):
            cv2.line(frame, a, b, (60, 160, 255), 2)
        writer.write(frame)
    cap.release()
    writer.release()


def _mark_legal_and_fit_window(track: pd.DataFrame, fall_start_frame: int, fall_end_frame: int, grid: dict[str, Any]) -> pd.DataFrame:
    out = track.copy()
    scale = float(grid.get("scale_y_m_per_px") or 1.0)
    out.attrs["scale_y_m_per_px"] = scale
    penultimate = grid.get("penultimate_line_y")
    legal = []
    permanently_out = False
    for _, row in out.iterrows():
        measured = row["state"] in {"tracking", "reacquired"}
        if measured and penultimate is not None and float(row["y"]) > float(penultimate):
            permanently_out = True
        legal.append(not permanently_out)
    out["legal_region"] = legal
    out["in_fall_window"] = (out["source_frame"] >= int(fall_start_frame)) & (out["source_frame"] <= int(fall_end_frame))
    out["use_for_fit"] = out["legal_region"] & out["in_fall_window"] & out["state"].isin(["tracking", "reacquired"])
    return out


def _reacquire_reason(current, predicted, last_detected, new_velocity, old_velocity, config: dict[str, Any]) -> str:
    if abs(float(current[0] - predicted[0])) > float(config.get("max_reacquire_dx_px", 18.0)):
        return "reacquired_x_offset_too_large"
    if float(current[1] - last_detected[1]) < float(config.get("min_reacquire_trend_dy_px", -2.0)):
        return "reacquired_y_trend_inconsistent"
    old_norm = float(np.linalg.norm(old_velocity))
    new_norm = float(np.linalg.norm(new_velocity))
    if old_norm > 1e-6 and new_norm / old_norm > float(config.get("max_velocity_jump_ratio", 3.5)):
        return "reacquired_velocity_jump"
    return ""


def _row(frame, source_frame, pos, pred, state, missed, blocked, mass, reason) -> dict[str, Any]:
    return {
        "frame": int(frame),
        "source_frame": int(source_frame),
        "x": float(pos[0]),
        "y": float(pos[1]),
        "pred_x": float(pred[0]),
        "pred_y": float(pred[1]),
        "state": state,
        "detected": state in {"tracking", "reacquired"},
        "missed_count": int(missed),
        "blocked_by_grid": bool(blocked),
        "mass": mass,
        "reason": reason,
    }


def _ensure_odd(value: int) -> int:
    value = max(3, int(value))
    return value if value % 2 else value + 1


def _read_frames(video_path: str, start: int, end: int) -> tuple[list, float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(start)))
    frames = []
    for _idx in range(max(0, int(start)), max(int(start), int(end)) + 1):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if not frames:
        raise RuntimeError("no tracking frames")
    return frames, fps


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.replace({np.nan: None}).to_json(orient="records"))
