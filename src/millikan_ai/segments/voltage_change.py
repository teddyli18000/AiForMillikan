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
    col_median = np.median(gray, axis=0)
    dark_threshold = max(70.0, min(155.0, float(np.percentile(col_median, 70))))
    dark_columns = np.flatnonzero(col_median < dark_threshold)
    screen_right = int(dark_columns.max()) if len(dark_columns) else search.w - 1

    horizontal_full = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, search.w // 5), 1)))
    row_mass = (horizontal_full > 0).sum(axis=1)
    line_rows = np.flatnonzero(row_mass > max(12, int(search.w * 0.18)))
    row_groups = _clusters(line_rows, max_gap=3)
    if len(row_groups) >= 2 and row_groups[0][0] > int(search.h * 0.12):
        y1 = 0
        y2 = min(search.h, row_groups[0][0] + int(cfg.get("roi_expand_px", 10)))
    elif len(row_groups) >= 2:
        top_line = row_groups[0][0]
        divider = row_groups[1][0]
        y1 = max(0, top_line - int(cfg.get("roi_expand_px", 10)))
        y2 = min(search.h, divider + int(cfg.get("roi_expand_px", 10)))
    elif len(row_groups) == 1:
        y1 = 0
        y2 = min(search.h, row_groups[0][0] + int(cfg.get("roi_expand_px", 10)))
    else:
        y1 = 0
        y2 = max(24, min(search.h, int(h * 0.18)))

    band_mask = mask[y1:y2, :]
    horizontal = cv2.morphologyEx(band_mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, search.w // 8), 1)))
    vertical = cv2.morphologyEx(band_mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(12, (y2 - y1) // 2))))
    text_mask = cv2.subtract(cv2.subtract(band_mask, horizontal), vertical)
    text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 2)))
    if 0 <= screen_right < text_mask.shape[1] - 1:
        text_mask[:, screen_right + 1 :] = 0
    valid_components: list[dict[str, int]] = []
    component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats((text_mask > 0).astype(np.uint8), 8)
    for label in range(1, component_count):
        x, y, width, height, area = stats[label]
        if area < 8:
            continue
        if not (2 <= width <= 90 and 6 <= height <= max(8, int((y2 - y1) * 0.78))):
            continue
        valid_components.append({"label": label, "x": int(x), "y": int(y), "w": int(width), "h": int(height), "area": int(area), "cy": int(y + height / 2)})
    component_mask = np.zeros_like(text_mask)
    if valid_components:
        centers = np.asarray(sorted(component["cy"] for component in valid_components), dtype=int)
        row_groups = _clusters(centers, max_gap=14)
        selected_components: list[dict[str, int]] = []
        best_score = -1.0
        for group in row_groups:
            members = [component for component in valid_components if group[0] <= component["cy"] <= group[1]]
            x_centers = np.asarray(sorted(component["x"] + component["w"] // 2 for component in members), dtype=int)
            x_groups = _clusters(x_centers, max_gap=95)
            row_best_members: list[dict[str, int]] = []
            row_best_score = -1.0
            for x_group in x_groups:
                x_members = [component for component in members if x_group[0] <= component["x"] + component["w"] // 2 <= x_group[1]]
                if len(x_members) < 3:
                    continue
                score = float(sum(component["area"] for component in x_members)) + 100.0 * len(x_members)
                if score > row_best_score:
                    row_best_score = score
                    row_best_members = x_members
            if row_best_members and sum(component["area"] for component in row_best_members) >= 600:
                selected_components = row_best_members
                break
            if not row_best_members:
                continue
            score = row_best_score - 0.2 * float(group[0])
            if score > best_score:
                best_score = score
                selected_components = row_best_members
        if not selected_components:
            selected_components = valid_components
        for component in selected_components:
            component_mask[labels == component["label"]] = 255
    if int((component_mask > 0).sum()) >= 12:
        text_mask = component_mask
    col_mass = (text_mask > 0).sum(axis=0)
    columns = np.flatnonzero(col_mass > max(1, int((y2 - y1) * 0.03)))
    if len(columns) > 0:
        x2 = min(search.w, screen_right + int(cfg.get("roi_expand_px", 10)), int(columns.max()) + int(cfg.get("roi_expand_px", 10)))
        max_text_width = int(cfg.get("max_voltage_text_width_px", 380))
        x1 = max(0, int(columns.min()) - int(cfg.get("roi_expand_px", 10)))
        if x2 - x1 > max_text_width:
            x1 = max(0, x2 - max_text_width)
        row_mass_text = (text_mask[:, x1:x2] > 0).sum(axis=1)
        rows = np.flatnonzero(row_mass_text > 0)
        if len(rows) > 0:
            y1 = max(y1, y1 + int(rows.min()) - int(cfg.get("roi_expand_px", 10)))
            y2 = min(y2, y1 + int(rows.max() - rows.min()) + 2 * int(cfg.get("roi_expand_px", 10)))
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
    for frame_idx in range(0, max(0, meta.frame_count), stride):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        current_roi = roi
        if bool(cfg.get("dynamic_roi_per_sample", True)):
            candidate_roi = locate_voltage_change_roi(frame, config)
            max_shift = float(cfg.get("max_dynamic_roi_shift_px", 120))
            roi_center = np.asarray([roi.x + roi.w / 2, roi.y + roi.h / 2], dtype=float)
            candidate_center = np.asarray([candidate_roi.x + candidate_roi.w / 2, candidate_roi.y + candidate_roi.h / 2], dtype=float)
            size_ok = 0.45 <= candidate_roi.w / max(roi.w, 1) <= 1.8 and 0.45 <= candidate_roi.h / max(roi.h, 1) <= 1.8
            if size_ok and float(np.linalg.norm(candidate_center - roi_center)) <= max_shift:
                current_roi = candidate_roi
        crop = frame[current_roi.y : current_roi.y + current_roi.h, current_roi.x : current_roi.x + current_roi.w]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        mask = _threshold_bright(gray)
        horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, current_roi.w // 4), 1)))
        vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, current_roi.h // 2))))
        text_mask = cv2.subtract(cv2.subtract(mask, horizontal), vertical)
        text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 2)))
        ys, xs = np.nonzero(text_mask)
        if len(xs) >= 8 and len(ys) >= 8:
            x1 = max(0, int(xs.min()) - 2)
            x2 = min(text_mask.shape[1], int(xs.max()) + 3)
            y1 = max(0, int(ys.min()) - 2)
            y2 = min(text_mask.shape[0], int(ys.max()) + 3)
            glyph = text_mask[y1:y2, x1:x2]
        else:
            glyph = mask
        binary = cv2.resize(glyph, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
        descriptor = binary.astype(np.float32) / 255.0
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
                "roi_x": current_roi.x,
                "roi_y": current_roi.y,
                "roi_w": current_roi.w,
                "roi_h": current_roi.h,
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
    hot = set(int(index) for index in np.flatnonzero(scores >= threshold))
    top_count = max(4, min(12, len(scores) // 5 if len(scores) >= 5 else len(scores)))
    for index in np.argsort(scores)[-top_count:]:
        hot.add(int(index))
    hot = np.asarray(sorted(hot), dtype=int)
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


def _smooth_labels(labels: np.ndarray, window: int = 5) -> np.ndarray:
    if len(labels) == 0:
        return labels
    radius = max(1, window // 2)
    smoothed = labels.copy()
    for index in range(len(labels)):
        chunk = labels[max(0, index - radius) : min(len(labels), index + radius + 1)]
        values, counts = np.unique(chunk, return_counts=True)
        smoothed[index] = values[int(np.argmax(counts))]
    return smoothed


def _runs_from_labels(labels: np.ndarray) -> list[dict[str, int]]:
    if len(labels) == 0:
        return []
    runs: list[dict[str, int]] = []
    start = 0
    current = int(labels[0])
    for index, label in enumerate(labels[1:], start=1):
        if int(label) == current:
            continue
        runs.append({"label": current, "start_sample": start, "end_sample": index - 1})
        start = index
        current = int(label)
    runs.append({"label": current, "start_sample": start, "end_sample": len(labels) - 1})
    return runs


def _cluster_platform_suggestions(
    samples: list[dict[str, Any]],
    descriptors: list[np.ndarray],
    expected_platform_count: int,
    frame_count: int,
    fps: float,
    roi: Roi,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    if len(descriptors) < expected_platform_count * 2:
        return None
    cfg = _auto_config(config)
    stride = max(1, int(cfg.get("sample_stride_frames", 5)))
    min_samples = max(2, int(round(float(cfg.get("min_platform_duration_s", 1.0)) * fps / stride)))
    data = np.asarray([descriptor.reshape(-1) for descriptor in descriptors], dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.01)
    try:
        compactness, labels, centers = cv2.kmeans(data, expected_platform_count, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    except cv2.error:
        return None
    del compactness, centers
    labels = _smooth_labels(labels.reshape(-1).astype(int), window=5)
    runs = _runs_from_labels(labels)
    stable_runs = [run for run in runs if run["end_sample"] - run["start_sample"] + 1 >= min_samples]
    if len(stable_runs) != expected_platform_count:
        return None
    rows: list[dict[str, Any]] = []
    reject_reasons: list[str] = []
    for index, run in enumerate(stable_runs):
        start_frame = int(samples[run["start_sample"]]["frame_idx"])
        end_frame = int(samples[run["end_sample"]]["frame_idx"])
        if index == len(stable_runs) - 1:
            end_frame = frame_count - 1
        duration = (end_frame - start_frame) / fps if fps else 0.0
        reject = ""
        if duration < float(cfg.get("min_platform_duration_s", 1.0)):
            reject = "platform_too_short_after_transition_removal"
            reject_reasons.append(reject)
        transition_start = transition_end = -1
        if index < len(stable_runs) - 1:
            transition_start = min(frame_count - 1, int(samples[run["end_sample"]]["frame_idx"]) + stride)
            transition_end = max(transition_start, int(samples[stable_runs[index + 1]["start_sample"]]["frame_idx"]) - stride)
        rows.append(
            {
                "platform_id": f"P{index + 1:03d}",
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_time_s": start_frame / fps if fps else 0.0,
                "end_time_s": end_frame / fps if fps else 0.0,
                "confidence": 0.8,
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
    diagnostics = {
        "expected_platform_count": int(expected_platform_count),
        "detected_platform_count": int(len(rows) if not reject_reasons else max(0, len(rows) - len(reject_reasons))),
        "method": "descriptor_kmeans_runs",
        "runs": stable_runs,
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
    clustered = _cluster_platform_suggestions(sample_rows, descriptors, expected_platform_count, meta.frame_count, meta.fps, roi, config)
    scores = _change_scores(descriptors)
    for index, score in enumerate(scores, start=1):
        if index < len(sample_rows):
            sample_rows[index]["confidence"] = min(1.0, float(score) / max(float(_auto_config(config).get("min_change_score", 0.08)), 1e-6))
            sample_rows[index]["raw_text"] = f"change_score={score:.6f}"
    samples = pd.DataFrame(sample_rows, columns=VOLTAGE_SAMPLE_COLUMNS)
    if clustered is not None:
        suggestions, diagnostics = clustered
        return suggestions, samples, diagnostics
    changes = _candidate_change_groups(sample_rows, scores, meta.fps, config)
    suggestions, diagnostics = _build_suggestions(changes, expected_platform_count, meta.frame_count, meta.fps, roi, config)
    return suggestions, samples, diagnostics
