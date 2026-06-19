from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import pandas as pd
import trackpy as tp


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


ProgressCallback = Callable[[str, str, int | None, int | None, str | None], None]

GRID_SAMPLE_FRAMES = 40
GRID_SAMPLE_STRIDE = 3
GRID_MIN_HORIZONTAL_LINE_LEN_PX = 600
GRID_MIN_VERTICAL_LINE_LEN_PX = 360
GRID_MASK_DILATE_PX = 5
GRID_INPAINT_RADIUS = 4
GRID_MASK_HARD_MAX_COVERAGE = 0.45
GRID_TOPHAT_KERNEL = 31
GRID_ADAPTIVE_BLOCK_SIZE = 51
GRID_ADAPTIVE_BRIGHT_C = 8
GRID_TOPHAT_PERCENTILE = 75.0
GRID_MIN_TOPHAT_RESPONSE = 8


def run_tracking(request: TrackRequest, progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
    run_dir = Path(request.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    start = max(0, int(request.target_frame))
    end = max(start, int(request.zero_v_end_frame))
    frames, fps = _read_frames(request.video_path, start, end, progress_callback)
    grid_mask = None
    if bool(request.config["tracking"].get("grid_mask_for_tracking_enabled", True)):
        grid_mask = build_static_grid_mask(request.video_path, start_frame=start, max_frames=end - start + 1)
    local_initial = np.array(request.source_center, dtype=float)
    track = track_single_drop_frames(frames, local_initial, start, request.config["tracking"], grid_mask, progress_callback)
    if not track.empty:
        track["time_s"] = track["source_frame"].astype(float) / float(fps)
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


def track_single_drop_frames(frames: list, initial_position: np.ndarray, source_start_frame: int, cfg: dict[str, Any], grid_mask=None, progress_callback: ProgressCallback | None = None) -> pd.DataFrame:
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
            if progress_callback is not None:
                progress_callback("track_frames", "正在逐帧追踪油滴", frame_id + 1, len(frames), "frames")
            continue
        predicted = search_center + velocity
        near_grid = is_position_near_grid(predicted, grid_mask, int(cfg.get("grid_occlusion_radius_px", 0)))
        chosen = None
        if not (near_grid and bool(cfg.get("skip_detection_on_grid", True))):
            features = locate_features_near_position(gray, predicted, float(cfg.get("local_search_radius_px", 45.0)), cfg, grid_mask)
            chosen = choose_nearest_feature(features, predicted, float(cfg.get("max_accept_distance_px", 30.0)))
        if chosen is None:
            missed += 1
            search_center = predicted.copy()
            rows.append(_row(frame_id, source_frame, np.array([math.nan, math.nan]), predicted, "missing", missed, near_grid, math.nan, "grid" if near_grid else "not_found"))
            if progress_callback is not None:
                progress_callback("track_frames", "正在逐帧追踪油滴", frame_id + 1, len(frames), "frames")
            if missed > int(cfg.get("memory_frames", 5)):
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
        if progress_callback is not None:
            progress_callback("track_frames", "正在逐帧追踪油滴", frame_id + 1, len(frames), "frames")
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
    grid_lines = [float(y) for y in (grid.get("grid_lines_y") or grid.get("line_y_px") or []) if _is_finite_number(y)]
    detected = track[track["detected"].astype(bool)].copy() if not track.empty and "detected" in track else pd.DataFrame()
    if len(detected) >= 2 and grid_lines:
        prior = None
        for _, row in detected.iterrows():
            if prior is None:
                prior = row
                continue
            y0 = float(prior["y"])
            y1 = float(row["y"])
            if not math.isfinite(y0) or not math.isfinite(y1) or y0 == y1:
                prior = row
                continue
            low, high = sorted((y0, y1))
            crossed = [line for line in grid_lines if low <= line <= high]
            for line in crossed:
                start_frame = int(prior["source_frame"])
                end_frame = int(row["source_frame"])
                if any(abs(float(event["start_frame"]) - start_frame) <= 1 and abs(float(event["end_frame"]) - end_frame) <= 1 for event in events):
                    continue
                event_id = f"crossing_{len(events) + 1:03d}"
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
                        "center_x_px": float(row["x"]),
                        "center_y_px": float(line),
                        "grid_line_y_px": float(line),
                        "kind": "grid_line_crossing",
                        "confirmed_same_drop": None,
                    }
                )
            prior = row
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
        row = by_frame.get(frame_idx)
        if row is not None:
            detected = bool(row.detected)
            x = row.x if detected and math.isfinite(float(row.x)) else row.pred_x
            y = row.y if detected and math.isfinite(float(row.y)) else row.pred_y
            if detected:
                color = (0, 255, 0)
                label = "target"
            else:
                color = (0, 255, 255)
                label = "missing"
            origin = (int(round(x)), int(round(y)))
            cv2.circle(frame, origin, 7, color, 2)
            cv2.putText(frame, label, (origin[0] + 10, origin[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
            if row.state in {"tracking", "reacquired"}:
                points.append(origin)
        for a, b in zip(points[:-1], points[1:]):
            cv2.line(frame, a, b, (255, 0, 0), 2)
        writer.write(frame)
    cap.release()
    writer.release()


def make_crossing_review_clip(video_path: str, event: dict[str, Any], out_path: Path, track_rows: list[dict[str, Any]] | None = None, crop_size: int = 96, scale: int = 3) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    start_frame = max(0, int(round(float(event.get("review_start_time_s", 0.0)) * fps)))
    end_frame = min(max(0, frame_count - 1), int(round(float(event.get("review_end_time_s", 0.0)) * fps)))
    if end_frame < start_frame:
        end_frame = start_frame
    center_x = float(event.get("center_x_px", 0.0))
    center_y = float(event.get("center_y_px", 0.0))
    half = max(16, int(crop_size // 2))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    ok, first = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("cannot read crossing review first frame")
    height, width = first.shape[:2]
    x0 = max(0, min(width - 1, int(round(center_x - half))))
    y0 = max(0, min(height - 1, int(round(center_y - half))))
    x1 = min(width, max(x0 + 1, int(round(center_x + half))))
    y1 = min(height, max(y0 + 1, int(round(center_y + half))))
    if x1 - x0 < crop_size:
        x0 = max(0, min(x0, width - crop_size))
        x1 = min(width, x0 + crop_size)
    if y1 - y0 < crop_size:
        y0 = max(0, min(y0, height - crop_size))
        y1 = min(height, y0 + crop_size)
    out_size = (max(1, (x1 - x0) * scale), max(1, (y1 - y0) * scale))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = out_path.parent / f"{out_path.stem}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, out_size)
    by_frame = {int(row.get("source_frame")): row for row in (track_rows or []) if row.get("source_frame") is not None}
    trail: list[tuple[int, int]] = []
    review_frames: list[dict[str, Any]] = []
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    for frame_idx in range(start_frame, end_frame + 1):
        ok, frame = cap.read()
        if not ok:
            break
        crop = frame[y0:y1, x0:x1].copy()
        row = by_frame.get(frame_idx)
        if row:
            detected = bool(row.get("detected"))
            rx = row.get("x") if detected and row.get("x") is not None else row.get("pred_x", center_x)
            ry = row.get("y") if detected and row.get("y") is not None else row.get("pred_y", center_y)
            local_x = int(round(float(rx) - x0))
            local_y = int(round(float(ry) - y0))
            color = (0, 255, 0) if detected else (0, 255, 255)
            label = "target" if detected else "missing"
            if detected:
                trail.append((local_x, local_y))
        else:
            local_x = int(round(center_x - x0))
            local_y = int(round(center_y - y0))
            color = (0, 255, 255)
            label = "missing"
        for a, b in zip(trail[:-1], trail[1:]):
            cv2.line(crop, a, b, (255, 0, 0), 1)
        cv2.circle(crop, (local_x, local_y), 8, color, 2)
        cv2.putText(crop, label, (local_x + 10, max(14, local_y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        rendered = cv2.resize(crop, out_size, interpolation=cv2.INTER_NEAREST)
        writer.write(rendered)
        image_path = frames_dir / f"frame_{len(review_frames):04d}.jpg"
        if not cv2.imwrite(str(image_path), rendered):
            raise RuntimeError(f"cannot write crossing review frame: {image_path}")
        review_frames.append(
            {
                "frame_index": frame_idx,
                "time_s": frame_idx / fps if fps > 0 else 0.0,
                "image_path": str(image_path),
                "source_video_box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
            }
        )
    cap.release()
    writer.release()
    manifest_path = frames_dir / "frames_manifest.json"
    manifest_path.write_text(json.dumps(review_frames, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "clip_path": str(out_path),
        "start_frame": start_frame,
        "end_frame": end_frame,
        "start_time_s": start_frame / fps if fps > 0 else 0.0,
        "end_time_s": end_frame / fps if fps > 0 else 0.0,
        "source_video_box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
        "scale": scale,
        "frames_manifest_path": str(manifest_path),
        "review_frames": review_frames,
    }


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


def _read_frames(video_path: str, start: int, end: int, progress_callback: ProgressCallback | None = None) -> tuple[list, float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames = []
    total = max(1, end - start + 1)
    for _frame_idx in range(start, end + 1):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
        if progress_callback is not None:
            progress_callback("read_tracking_frames", "正在读取追踪帧", len(frames), total, "frames")
    cap.release()
    if not frames:
        raise RuntimeError("no tracking frames")
    return frames, fps


def _preprocess(frame) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (3, 3), 0)


def build_static_grid_mask(video_path: str, start_frame: int = 0, max_frames: int | None = None) -> np.ndarray | None:
    samples = _read_grid_sample_frames(video_path, start_frame, max_frames)
    if not samples:
        return None
    first_shape = samples[0].shape
    if any(frame.shape != first_shape for frame in samples):
        return None
    stack = np.stack(samples, axis=0).astype(np.uint8)
    background_bgr = np.median(stack, axis=0).astype(np.uint8)
    gray = cv2.cvtColor(background_bgr, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray_blur = cv2.GaussianBlur(gray_eq, (3, 3), 0)
    tophat_kernel_size = _ensure_odd(GRID_TOPHAT_KERNEL)
    adaptive_block_size = _ensure_odd(GRID_ADAPTIVE_BLOCK_SIZE)
    tophat_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (tophat_kernel_size, tophat_kernel_size))
    tophat = cv2.morphologyEx(gray_blur, cv2.MORPH_TOPHAT, tophat_kernel)
    nz = tophat[tophat > 0]
    percentile_threshold = float(np.percentile(nz, float(GRID_TOPHAT_PERCENTILE))) if nz.size else 0.0
    tophat_threshold = max(float(GRID_MIN_TOPHAT_RESPONSE), percentile_threshold)
    bright_seed_tophat = np.where(tophat >= tophat_threshold, 255, 0).astype(np.uint8)
    bright_seed_adaptive = cv2.adaptiveThreshold(
        gray_blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        adaptive_block_size,
        -int(GRID_ADAPTIVE_BRIGHT_C),
    )
    small_clean_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    bright_seed_tophat = cv2.morphologyEx(bright_seed_tophat, cv2.MORPH_OPEN, small_clean_kernel, iterations=1)
    bright_seed_adaptive = cv2.morphologyEx(bright_seed_adaptive, cv2.MORPH_OPEN, small_clean_kernel, iterations=1)
    bright_seed_combined = cv2.bitwise_or(bright_seed_tophat, bright_seed_adaptive)
    height, width = bright_seed_combined.shape[:2]
    horizontal_len = max(int(GRID_MIN_HORIZONTAL_LINE_LEN_PX), width // 12)
    vertical_len = max(int(GRID_MIN_VERTICAL_LINE_LEN_PX), height // 8)
    horizontal_seed = cv2.morphologyEx(
        bright_seed_combined,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)),
        iterations=1,
    )
    vertical_seed = cv2.morphologyEx(
        bright_seed_combined,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15)),
        iterations=1,
    )
    horizontal_lines = cv2.morphologyEx(
        horizontal_seed,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_len, 3)),
        iterations=1,
    )
    vertical_lines = cv2.morphologyEx(
        vertical_seed,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, vertical_len)),
        iterations=1,
    )
    grid_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
    if GRID_MASK_DILATE_PX > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * GRID_MASK_DILATE_PX + 1, 2 * GRID_MASK_DILATE_PX + 1))
        grid_mask = cv2.dilate(grid_mask, kernel, iterations=1)
    grid_mask = np.where(grid_mask > 0, 255, 0).astype(np.uint8)
    coverage = float(np.count_nonzero(grid_mask)) / float(grid_mask.size)
    if coverage > GRID_MASK_HARD_MAX_COVERAGE:
        return None
    return grid_mask


def _read_grid_sample_frames(video_path: str, start_frame: int, max_frames: int | None) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(start_frame)))
    samples: list[np.ndarray] = []
    local_frame_index = 0
    while len(samples) < GRID_SAMPLE_FRAMES:
        if max_frames is not None and local_frame_index >= max_frames:
            break
        ok, frame = cap.read()
        if not ok:
            break
        if local_frame_index % GRID_SAMPLE_STRIDE == 0:
            samples.append(frame)
        local_frame_index += 1
    cap.release()
    return samples


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


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
