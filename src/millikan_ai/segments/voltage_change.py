from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from millikan_ai.calibration.grid import Roi
from millikan_ai.outputs.schemas import AUTO_PLATFORM_SUGGESTION_COLUMNS, VOLTAGE_SAMPLE_COLUMNS
from millikan_ai.video.reader import inspect_video


def _auto_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("auto_platform_detection", {}))


def _threshold_bright(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    floor = max(90, int(np.percentile(blurred, 88)))
    _, mask = cv2.threshold(blurred, floor, 255, cv2.THRESH_BINARY)
    return mask


def _clusters(indices: np.ndarray, max_gap: int = 2) -> list[tuple[int, int]]:
    if len(indices) == 0:
        return []
    groups: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for value in indices[1:]:
        current = int(value)
        if current - previous <= max_gap:
            previous = current
            continue
        groups.append((start, previous))
        start = previous = current
    groups.append((start, previous))
    return groups


def locate_voltage_change_roi(frame: np.ndarray, config: dict[str, Any]) -> Roi:
    configured = Roi.from_config(config.get("roi", {}).get("voltage_roi"))
    if configured is not None:
        return configured
    h, w = frame.shape[:2]
    cfg = _auto_config(config)
    rx, ry, rw, rh = cfg.get("search_region", [0.45, 0.0, 0.55, 0.32])
    search = Roi(int(w * rx), int(h * ry), max(1, int(w * rw)), max(1, int(h * rh)))
    crop = frame[search.y : search.y + search.h, search.x : search.x + search.w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = _threshold_bright(gray)

    row_mass = (mask > 0).sum(axis=1)
    line_rows = np.flatnonzero(row_mass > max(12, int(search.w * 0.18)))
    row_groups = _clusters(line_rows, max_gap=3)
    if len(row_groups) >= 2:
        top_line = row_groups[0][0]
        divider = row_groups[1][0]
        y1 = max(0, top_line - int(cfg.get("roi_expand_px", 10)))
        y2 = min(search.h, divider + int(cfg.get("roi_expand_px", 10)))
    else:
        y1 = 0
        y2 = max(24, min(search.h, int(h * 0.18)))

    band_mask = mask[y1:y2, :]
    col_mass = (band_mask > 0).sum(axis=0)
    columns = np.flatnonzero(col_mass > max(2, int((y2 - y1) * 0.06)))
    if len(columns) > 0:
        x1 = max(0, int(columns.min()) - int(cfg.get("roi_expand_px", 10)))
        x2 = min(search.w, int(columns.max()) + int(cfg.get("roi_expand_px", 10)))
    else:
        x1, x2 = 0, search.w

    if x2 - x1 < 40 or y2 - y1 < 20:
        return Roi(search.x, search.y, search.w, max(24, min(search.h, int(h * 0.18))))
    return Roi(search.x + x1, search.y + y1, x2 - x1, y2 - y1)


def _read_sampled_descriptors(video: Path, roi: Roi, config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    meta = inspect_video(video)
    cfg = _auto_config(config)
    stride = max(1, int(cfg.get("sample_stride_frames", 5)))
    out_w = max(16, int(cfg.get("descriptor_width", 96)))
    out_h = max(12, int(cfg.get("descriptor_height", 32)))
    cap = cv2.VideoCapture(str(video))
    samples: list[dict[str, Any]] = []
    descriptors: list[np.ndarray] = []
    reference: np.ndarray | None = None
    for frame_idx in range(0, max(0, meta.frame_count), stride):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        crop = frame[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (out_w, out_h), interpolation=cv2.INTER_AREA)
        equalized = cv2.equalizeHist(resized)
        if reference is None:
            reference = equalized.astype(np.float32)
            aligned = equalized
        else:
            current = equalized.astype(np.float32)
            shift, _response = cv2.phaseCorrelate(reference, current)
            dx, dy = shift
            if abs(dx) <= 6 and abs(dy) <= 6:
                matrix = np.float32([[1, 0, -dx], [0, 1, -dy]])
                aligned = cv2.warpAffine(equalized, matrix, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            else:
                aligned = equalized
        descriptor = cv2.GaussianBlur(aligned, (3, 3), 0).astype(np.float32) / 255.0
        samples.append(
            {
                "frame_idx": frame_idx,
                "time_s": frame_idx / meta.fps if meta.fps else 0.0,
                "voltage_V": np.nan,
                "confidence": 0.0,
                "source": "auto_change_detector",
                "raw_text": "",
                "accepted": True,
                "reject_reason": "",
                "roi_x": roi.x,
                "roi_y": roi.y,
                "roi_w": roi.w,
                "roi_h": roi.h,
            }
        )
        descriptors.append(descriptor)
    cap.release()
    return samples, descriptors


def _change_scores(descriptors: list[np.ndarray]) -> np.ndarray:
    if len(descriptors) < 2:
        return np.array([], dtype=float)
    scores = [float(np.mean(np.abs(descriptors[i] - descriptors[i - 1]))) for i in range(1, len(descriptors))]
    return np.asarray(scores, dtype=float)


def _candidate_change_groups(samples: list[dict[str, Any]], scores: np.ndarray, fps: float, config: dict[str, Any]) -> list[dict[str, Any]]:
    if len(samples) < 2 or len(scores) == 0:
        return []
    cfg = _auto_config(config)
    median = float(np.median(scores))
    mad = float(np.median(np.abs(scores - median)))
    sigma = max(mad * 1.4826, 1e-6)
    threshold = max(float(cfg.get("min_change_score", 0.08)), median + float(cfg.get("change_threshold_sigma", 3.0)) * sigma)
    hot = np.flatnonzero(scores >= threshold)
    if len(hot) == 0:
        hot = np.argsort(scores)[-max(1, min(4, len(scores))) :]
        hot.sort()
    groups = _clusters(hot, max_gap=1)
    result: list[dict[str, Any]] = []
    for start_score_idx, end_score_idx in groups:
        local = scores[start_score_idx : end_score_idx + 1]
        if len(local) == 0:
            continue
        offset = int(np.argmax(local))
        score_idx = start_score_idx + offset
        sample_idx = score_idx + 1
        frame_idx = int(samples[sample_idx]["frame_idx"])
        score = float(scores[score_idx])
        result.append(
            {
                "frame_idx": frame_idx,
                "sample_start_frame": int(samples[start_score_idx]["frame_idx"]),
                "sample_end_frame": int(samples[min(end_score_idx + 1, len(samples) - 1)]["frame_idx"]),
                "score": score,
                "above_threshold": bool(score >= threshold),
            }
        )
    result.sort(key=lambda item: item["score"], reverse=True)
    min_sep = int(max(1.0, fps) * float(cfg.get("min_change_separation_s", 1.0)))
    selected: list[dict[str, Any]] = []
    for item in result:
        if all(abs(int(item["frame_idx"]) - int(existing["frame_idx"])) >= min_sep for existing in selected):
            selected.append(item)
    selected.sort(key=lambda item: int(item["frame_idx"]))
    return selected


def _build_suggestions(
    changes: list[dict[str, Any]],
    expected_platform_count: int,
    frame_count: int,
    fps: float,
    roi: Roi,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = _auto_config(config)
    padding = int(round(float(cfg.get("transition_padding_s", 0.2)) * fps))
    min_duration = float(cfg.get("min_platform_duration_s", 1.0))
    selected = changes[: max(0, expected_platform_count - 1)]
    selected.sort(key=lambda item: int(item["frame_idx"]))
    rows: list[dict[str, Any]] = []
    start = 0
    reject_reasons: list[str] = []
    for index in range(expected_platform_count):
        transition_start = transition_end = -1
        if index < len(selected):
            change = selected[index]
            transition_start = max(start, int(change["sample_start_frame"]) - padding)
            transition_end = min(frame_count - 1, int(change["sample_end_frame"]) + padding)
            end = max(start, transition_start - 1)
        else:
            end = frame_count - 1
        duration = (end - start) / fps if fps else 0.0
        reject = ""
        confidence = 0.0
        if index == 0 and len(selected) < expected_platform_count - 1:
            reject = "insufficient_change_points"
        elif duration < min_duration:
            reject = "platform_too_short_after_transition_removal"
        if index < len(selected):
            confidence = min(1.0, float(selected[index]["score"]) / max(float(cfg.get("min_change_score", 0.08)), 1e-6))
        elif selected:
            confidence = float(np.mean([min(1.0, float(item["score"]) / max(float(cfg.get("min_change_score", 0.08)), 1e-6)) for item in selected]))
        else:
            confidence = 0.0
        if reject:
            reject_reasons.append(reject)
        rows.append(
            {
                "platform_id": f"P{index + 1:03d}",
                "start_frame": int(start),
                "end_frame": int(end),
                "start_time_s": start / fps if fps else 0.0,
                "end_time_s": end / fps if fps else 0.0,
                "confidence": confidence,
                "source": "auto_change_detector",
                "transition_start_frame": int(transition_start),
                "transition_end_frame": int(transition_end),
                "roi_x": roi.x,
                "roi_y": roi.y,
                "roi_w": roi.w,
                "roi_h": roi.h,
                "reject_reason": reject,
            }
        )
        if index < len(selected):
            start = min(frame_count - 1, transition_end + 1)
    detected = len(rows) if not reject_reasons and len(selected) == expected_platform_count - 1 else len(selected) + 1
    diagnostics = {
        "expected_platform_count": int(expected_platform_count),
        "detected_platform_count": int(detected),
        "change_points": selected,
        "roi": {"x": roi.x, "y": roi.y, "w": roi.w, "h": roi.h},
        "flags": sorted(set(reject_reasons)),
    }
    return pd.DataFrame(rows, columns=AUTO_PLATFORM_SUGGESTION_COLUMNS), diagnostics


def detect_voltage_platform_changes(video: str | Path, expected_platform_count: int, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if expected_platform_count <= 0:
        raise ValueError("expected_platform_count must be positive")
    video_path = Path(video)
    meta = inspect_video(video_path)
    cap = cv2.VideoCapture(str(video_path))
    ok, first_frame = cap.read()
    cap.release()
    if not ok:
        empty_suggestions = pd.DataFrame(columns=AUTO_PLATFORM_SUGGESTION_COLUMNS)
        empty_samples = pd.DataFrame(columns=VOLTAGE_SAMPLE_COLUMNS)
        return empty_suggestions, empty_samples, {
            "expected_platform_count": int(expected_platform_count),
            "detected_platform_count": 0,
            "flags": ["video_unreadable"],
            "roi": None,
        }
    roi = locate_voltage_change_roi(first_frame, config)
    sample_rows, descriptors = _read_sampled_descriptors(video_path, roi, config)
    scores = _change_scores(descriptors)
    for index, score in enumerate(scores, start=1):
        if index < len(sample_rows):
            sample_rows[index]["confidence"] = min(1.0, float(score) / max(float(_auto_config(config).get("min_change_score", 0.08)), 1e-6))
            sample_rows[index]["raw_text"] = f"change_score={score:.6f}"
    changes = _candidate_change_groups(sample_rows, scores, meta.fps, config)
    suggestions, diagnostics = _build_suggestions(changes, expected_platform_count, meta.frame_count, meta.fps, roi, config)
    samples = pd.DataFrame(sample_rows, columns=VOLTAGE_SAMPLE_COLUMNS)
    return suggestions, samples, diagnostics
