from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class VoltageSample:
    frame: int
    time_s: float
    score: float


def suggest_balance_fall_boundaries(video_path: str | Path, cfg: dict[str, Any]) -> dict[str, Any]:
    samples = sample_voltage_changes(video_path, cfg)
    operations = merge_change_operations(samples, cfg)
    meta = _video_meta(video_path)
    fps = meta["fps"] or 30.0
    if operations:
        first = operations[0]
        fall_start = int(round(first["end_frame"] + float(cfg["voltage"].get("stable_after_s", 0.35)) * fps))
        selection_frame = max(0, int(first["start_frame"] - round(0.6 * fps)))
    else:
        fall_start = 0
        selection_frame = 0
    if len(operations) >= 2:
        fall_end = max(fall_start, int(operations[1]["start_frame"] - 1))
        end_source = "before_leave_zero_operation"
    else:
        fall_end = max(fall_start, meta["frame_count"] - 2)
        end_source = "no_recovery_detected_video_tail"
    return {
        "samples": [sample.__dict__ for sample in samples],
        "operations": operations,
        "suggestion": {
            "selection_frame": selection_frame,
            "selection_time_s": selection_frame / fps,
            "fall_start_frame": fall_start,
            "fall_start_time_s": fall_start / fps,
            "fall_end_frame": fall_end,
            "fall_end_time_s": fall_end / fps,
            "end_source": end_source,
            "flags": [] if operations else ["voltage_operation_not_detected"],
        },
    }


def sample_voltage_changes(video_path: str | Path, cfg: dict[str, Any]) -> list[VoltageSample]:
    vcfg = cfg["voltage"]
    stride = max(1, int(vcfg.get("sample_stride_frames", 5)))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    previous = None
    rows: list[VoltageSample] = []
    for frame_idx in range(0, frame_count, stride):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            break
        desc = _descriptor(frame, vcfg)
        score = 0.0 if previous is None else float(np.mean(np.abs(desc - previous)) / 255.0)
        rows.append(VoltageSample(frame=frame_idx, time_s=frame_idx / fps, score=score))
        previous = desc
    cap.release()
    return rows


def merge_change_operations(samples: list[VoltageSample], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if not samples:
        return []
    vcfg = cfg["voltage"]
    scores = np.array([sample.score for sample in samples[1:]], dtype=float)
    median = float(np.median(scores)) if scores.size else 0.0
    mad = float(np.median(np.abs(scores - median))) if scores.size else 0.0
    robust_sigma = 1.4826 * mad
    threshold = max(float(vcfg.get("min_change_score", 0.08)), median + float(vcfg.get("change_threshold_sigma", 3.0)) * robust_sigma)
    change_samples = [sample for sample in samples if sample.score >= threshold]
    if not change_samples:
        return []
    sample_dt = float(np.median(np.diff([sample.time_s for sample in samples]))) if len(samples) > 1 else 0.2
    max_gap_s = min(
        float(vcfg.get("operation_gap_max_s", 2.8)),
        max(float(vcfg.get("operation_gap_min_s", 0.7)), sample_dt * float(vcfg.get("operation_gap_multiplier", 2.5))),
    )
    operations: list[dict[str, Any]] = []
    current = [change_samples[0]]
    for sample in change_samples[1:]:
        if sample.time_s - current[-1].time_s <= max_gap_s:
            current.append(sample)
        else:
            operations.append(_operation(current, threshold))
            current = [sample]
    operations.append(_operation(current, threshold))
    return operations


def _operation(samples: list[VoltageSample], threshold: float) -> dict[str, Any]:
    return {
        "start_frame": int(samples[0].frame),
        "end_frame": int(samples[-1].frame),
        "start_time_s": float(samples[0].time_s),
        "end_time_s": float(samples[-1].time_s),
        "peak_score": float(max(sample.score for sample in samples)),
        "sample_count": int(len(samples)),
        "threshold": float(threshold),
        "source": "visual_operation_merge",
    }


def _descriptor(frame, cfg: dict[str, Any]) -> np.ndarray:
    h, w = frame.shape[:2]
    rx, ry, rw, rh = cfg.get("search_region", [0.45, 0.0, 0.55, 0.32])
    x0 = int(max(0, min(w - 1, round(rx * w))))
    y0 = int(max(0, min(h - 1, round(ry * h))))
    x1 = int(max(x0 + 1, min(w, round((rx + rw) * w))))
    y1 = int(max(y0 + 1, min(h, round((ry + rh) * h))))
    gray = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (int(cfg.get("descriptor_width", 96)), int(cfg.get("descriptor_height", 32))))
    return gray.astype(np.float32)


def _video_meta(video_path: str | Path) -> dict[str, float | int]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return {"fps": fps, "frame_count": frame_count}

