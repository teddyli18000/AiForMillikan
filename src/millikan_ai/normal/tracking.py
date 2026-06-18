from __future__ import annotations

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
    zero_v_start_frame: int
    zero_v_end_frame: int
    source_center: tuple[float, float]
    grid: dict[str, Any]
    run_dir: str
    config: dict[str, Any]


def run_tracking(request: TrackRequest) -> dict[str, Any]:
    run_dir = Path(request.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    start = max(0, min(int(request.target_frame), int(request.zero_v_start_frame)))
    end = max(start, int(request.zero_v_end_frame))
    frames, fps = _read_frames(request.video_path, start, end)
    grid_mask = None
    if request.grid.get("grid_lines_y"):
        gray0 = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        grid_mask = build_grid_mask(gray0, [int(y) for y in request.grid.get("grid_lines_y", [])], int(request.config["grid"].get("mask_dilate_px", 5)))
    local_initial = np.array(request.source_center, dtype=float)
    track = track_single_drop_frames(frames, local_initial, start, request.config["tracking"], grid_mask)
    track = _mark_fit_window(track, request.zero_v_start_frame, request.zero_v_end_frame, request.grid)
    crossings = crossing_events(track, request.grid, fps)
    track_csv = run_dir / "track.csv"
    events_json = run_dir / "crossing_events.json"
    layers_json = run_dir / "visualization_layers.json"
    overlay_mp4 = run_dir / "overlay_review.mp4"
    track.to_csv(track_csv, index=False)
    events_json.write_text(json.dumps(crossings, ensure_ascii=False, indent=2), encoding="utf-8")
    layers = visualization_layers(track, crossings, request, fps)
    layers_json.write_text(json.dumps(layers, ensure_ascii=False, indent=2), encoding="utf-8")
    make_overlay_video(request.video_path, track, overlay_mp4, start, end, request.grid)
    return {
        "track_csv": str(track_csv),
        "crossing_events_json": str(events_json),
        "visualization_layers_json": str(layers_json),
        "overlay_mp4": str(overlay_mp4),
        "track": _records(track),
        "crossing_events": crossings,
        "visualization_layers": layers,
        "fps": float(fps),
    }


def track_single_drop_frames(frames: list, initial_position: np.ndarray, source_start_frame: int, cfg: dict[str, Any], grid_mask=None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    search_center = initial_position.astype(float)
    last_detected = initial_position.astype(float)
    last_detected_frame = 0
    velocity = np.array([0.0, 0.0], dtype=float)
    missed = 0
    for frame_id, frame in enumerate(frames):
        gray = _preprocess(frame)
        source_frame = int(source_start_frame) + int(frame_id)
        if frame_id == 0:
            rows.append(_row(frame_id, source_frame, initial_position, initial_position, "tracking", 0, False, math.nan, "manual_target"))
            continue
        predicted = search_center + velocity
        near_grid = is_position_near_grid(predicted, grid_mask, int(cfg.get("grid_occlusion_radius_px", 2)))
        chosen = None
        if not (near_grid and bool(cfg.get("skip_detection_on_grid", True))):
            features = locate_features_near_position(gray, predicted, float(cfg.get("local_search_radius_px", 45.0)), cfg, grid_mask)
            chosen = choose_nearest_feature(features, predicted, float(cfg.get("max_accept_distance_px", 30.0)))
        if chosen is None:
            missed += 1
            search_center = predicted.copy()
            rows.append(_row(frame_id, source_frame, np.array([math.nan, math.nan]), predicted, "missing", missed, near_grid, math.nan, "grid" if near_grid else "not_found"))
            if missed > int(cfg.get("memory_frames", 8)):
                break
            continue
        current = np.array([float(chosen["x"]), float(chosen["y"])], dtype=float)
        frame_gap = max(1, frame_id - last_detected_frame)
        velocity = (current - last_detected) / frame_gap
        state = "reacquired" if missed else "tracking"
        rows.append(_row(frame_id, source_frame, current, predicted, state, 0, near_grid, float(chosen.get("mass", math.nan)), ""))
        search_center = current.copy()
        last_detected = current.copy()
        last_detected_frame = frame_id
        missed = 0
    return pd.DataFrame(rows)


def locate_features_near_position(gray, center, radius: float, cfg: dict[str, Any], grid_mask=None) -> pd.DataFrame:
    h, w = gray.shape[:2]
    cx, cy = float(center[0]), float(center[1])
    x0, y0 = max(0, int(round(cx - radius))), max(0, int(round(cy - radius)))
    x1, y1 = min(w, int(round(cx + radius + 1))), min(h, int(round(cy + radius + 1)))
    crop = gray[y0:y1, x0:x1].copy()
    diameter = _ensure_odd(int(cfg.get("diameter", 5)))
    if crop.shape[0] < diameter + 2 or crop.shape[1] < diameter + 2:
        return pd.DataFrame()
    reject_mask = None
    if grid_mask is not None:
        reject_mask = np.where(grid_mask[y0:y1, x0:x1] > 0, 255, 0).astype(np.uint8)
        if np.count_nonzero(reject_mask):
            valid = crop[reject_mask == 0]
            crop[reject_mask > 0] = np.uint8(np.median(valid) if valid.size else np.median(crop))
    features = tp.locate(
        crop,
        diameter=diameter,
        minmass=float(cfg.get("minmass", 80.0)),
        invert=bool(cfg.get("invert", False)),
        topn=int(cfg.get("local_topn", 20)),
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


def choose_nearest_feature(features: pd.DataFrame, predicted: np.ndarray, max_distance: float):
    if features is None or len(features) == 0:
        return None
    features = features.copy()
    features["distance_to_prediction"] = np.hypot(features["x"] - predicted[0], features["y"] - predicted[1])
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


def crossing_events(track: pd.DataFrame, grid: dict[str, Any], fps: float) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    runs: list[list[pd.Series]] = []
    current: list[pd.Series] = []
    for _, row in track.iterrows():
        if bool(row.get("blocked_by_grid", False)) or row.get("state") in {"missing", "reacquired"}:
            current.append(row)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    for idx, run in enumerate(runs, start=1):
        start_frame = int(run[0]["source_frame"])
        end_frame = int(run[-1]["source_frame"])
        points = [row for row in run if math.isfinite(float(row.get("x", math.nan))) and math.isfinite(float(row.get("y", math.nan)))]
        center_x = float(points[-1]["x"]) if points else float(run[-1].get("pred_x", 0.0))
        center_y = float(points[-1]["y"]) if points else float(run[-1].get("pred_y", 0.0))
        event_id = f"crossing_{idx:03d}"
        events.append(
            {
                "id": event_id,
                "event_id": event_id,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_time_s": start_frame / fps,
                "end_time_s": end_frame / fps,
                "review_start_time_s": max(0.0, start_frame / fps - 1.0),
                "review_end_time_s": end_frame / fps + 1.0,
                "center_x_px": center_x,
                "center_y_px": center_y,
                "kind": "grid_crossing_or_reacquire",
                "confirmed_same_drop": None,
            }
        )
    return events


def visualization_layers(track: pd.DataFrame, crossings: list[dict[str, Any]], request: TrackRequest, fps: float) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "frame": {"fps": fps},
        "grid": {
            "grid_lines_y": request.grid.get("grid_lines_y", []),
            "second_line_y": request.grid.get("second_line_y"),
            "penultimate_line_y": request.grid.get("penultimate_line_y"),
        },
        "zero_v_window": {"start_frame": request.zero_v_start_frame, "end_frame": request.zero_v_end_frame},
        "target": {"x": request.source_center[0], "y": request.source_center[1], "frame": request.target_frame},
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
        for y in grid.get("grid_lines_y", []) or []:
            cv2.line(frame, (0, int(y)), (w - 1, int(y)), (60, 90, 120), 1)
        for y in [grid.get("second_line_y"), grid.get("penultimate_line_y")]:
            if y is not None:
                cv2.line(frame, (0, int(y)), (w - 1, int(y)), (255, 180, 0), 2)
        row = by_frame.get(frame_idx)
        if row is not None:
            x = row.x if math.isfinite(float(row.x)) else row.pred_x
            y = row.y if math.isfinite(float(row.y)) else row.pred_y
            color = (40, 220, 40) if row.state == "tracking" else (0, 200, 255)
            cv2.circle(frame, (int(round(x)), int(round(y))), 7, color, 2)
            if row.state in {"tracking", "reacquired"}:
                points.append((int(round(row.x)), int(round(row.y))))
        for a, b in zip(points[:-1], points[1:]):
            cv2.line(frame, a, b, (60, 160, 255), 2)
        writer.write(frame)
    cap.release()
    writer.release()


def _mark_fit_window(track: pd.DataFrame, zero_start: int, zero_end: int, grid: dict[str, Any]) -> pd.DataFrame:
    out = track.copy()
    penultimate = grid.get("penultimate_line_y")
    legal = []
    out_of_region = False
    for _, row in out.iterrows():
        if row.get("state") in {"tracking", "reacquired"} and penultimate is not None and float(row["y"]) > float(penultimate):
            out_of_region = True
        legal.append(not out_of_region)
    out["legal_region"] = legal
    out["in_zero_v_window"] = (out["source_frame"] >= int(zero_start)) & (out["source_frame"] <= int(zero_end))
    out["use_for_fit"] = out["legal_region"] & out["in_zero_v_window"] & out["state"].isin(["tracking", "reacquired"])
    return out


def _read_frames(video_path: str, start: int, end: int) -> tuple[list, float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames = []
    for _frame_idx in range(start, end + 1):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if not frames:
        raise RuntimeError("no tracking frames")
    return frames, fps


def _preprocess(frame) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (3, 3), 0)


def _row(frame, source_frame, pos, pred, state, missed, blocked, mass, reason) -> dict[str, Any]:
    return {
        "frame_idx": int(frame),
        "source_frame": int(source_frame),
        "time_s": math.nan,
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


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.replace({np.nan: None}).to_json(orient="records"))
