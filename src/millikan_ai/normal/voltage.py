from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from .video import inspect_video


@dataclass(frozen=True)
class VoltageChangeSample:
    frame: int
    time_s: float
    score: float


ProgressCallback = Callable[[str, str, int | None, int | None, str | None], None]


def suggest_zero_v_window(video_path: str | Path, cfg: dict[str, Any], progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
    meta = inspect_video(video_path)
    fps = float(meta.get("fps") or 30.0)
    frame_count = int(meta.get("frame_count") or 0)
    samples = sample_visual_changes(video_path, cfg, progress_callback)
    operations = merge_operations(samples, cfg)
    flags: list[str] = []
    if operations:
        first = operations[0]
        zero_start_frame = min(frame_count - 1, max(0, int(round(first["end_frame"] + float(cfg["voltage"].get("stable_after_s", 0.25)) * fps))))
        selection_frame = max(0, int(round(first["start_frame"] - 0.4 * fps)))
    else:
        flags.append("zero_v_operation_not_detected")
        zero_start_frame = 0
        selection_frame = 0
    if len(operations) >= 2:
        zero_end_frame = max(zero_start_frame, int(operations[1]["start_frame"]) - 1)
        end_source = "before_second_visual_operation"
    else:
        flags.append("zero_v_end_needs_review")
        zero_end_frame = max(zero_start_frame, frame_count - 2)
        end_source = "video_tail"
    return {
        "samples": [sample.__dict__ for sample in samples],
        "operations": operations,
        "suggestion": {
            "selection_frame": int(selection_frame),
            "selection_time_s": float(selection_frame / fps) if fps > 0 else 0.0,
            "zero_v_start_frame": int(zero_start_frame),
            "zero_v_start_s": float(zero_start_frame / fps) if fps > 0 else 0.0,
            "zero_v_end_frame": int(zero_end_frame),
            "zero_v_end_s": float(zero_end_frame / fps) if fps > 0 else 0.0,
            "source": "visual_change_suggestion",
            "end_source": end_source,
            "flags": flags,
        },
    }


def sample_visual_changes(video_path: str | Path, cfg: dict[str, Any], progress_callback: ProgressCallback | None = None) -> list[VoltageChangeSample]:
    vcfg = cfg["voltage"]
    stride = max(1, int(vcfg.get("sample_stride_frames", 5)))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    previous = None
    samples: list[VoltageChangeSample] = []
    sample_frames = list(range(0, frame_count, stride))
    total = len(sample_frames)
    for index, frame_idx in enumerate(sample_frames, start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            break
        desc = _descriptor(frame, vcfg)
        score = 0.0 if previous is None else float(np.mean(np.abs(desc - previous)) / 255.0)
        samples.append(VoltageChangeSample(frame=frame_idx, time_s=frame_idx / fps, score=score))
        previous = desc
        if progress_callback is not None:
            progress_callback("sample_voltage_region", "正在采样电压显示区域", index, total, "frames")
    cap.release()
    return samples


def merge_operations(samples: list[VoltageChangeSample], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if len(samples) < 2:
        return []
    scores = np.array([sample.score for sample in samples[1:]], dtype=float)
    median = float(np.median(scores)) if len(scores) else 0.0
    mad = float(np.median(np.abs(scores - median))) if len(scores) else 0.0
    threshold = max(float(cfg["voltage"].get("min_change_score", 0.08)), median + float(cfg["voltage"].get("change_threshold_sigma", 3.0)) * 1.4826 * mad)
    changed = [sample for sample in samples if sample.score >= threshold]
    if not changed:
        return []
    max_gap_s = float(cfg["voltage"].get("operation_gap_s", 0.8))
    runs: list[list[VoltageChangeSample]] = [[changed[0]]]
    for sample in changed[1:]:
        if sample.time_s - runs[-1][-1].time_s <= max_gap_s:
            runs[-1].append(sample)
        else:
            runs.append([sample])
    return [
        {
            "start_frame": int(run[0].frame),
            "end_frame": int(run[-1].frame),
            "start_time_s": float(run[0].time_s),
            "end_time_s": float(run[-1].time_s),
            "peak_score": float(max(row.score for row in run)),
            "sample_count": int(len(run)),
            "threshold": float(threshold),
            "source": "visual_change_merge",
        }
        for run in runs
    ]


def _descriptor(frame, cfg: dict[str, Any]) -> np.ndarray:
    h, w = frame.shape[:2]
    rx, ry, rw, rh = cfg.get("search_region", [0.45, 0.0, 0.55, 0.32])
    x0 = int(max(0, min(w - 1, round(float(rx) * w))))
    y0 = int(max(0, min(h - 1, round(float(ry) * h))))
    x1 = int(max(x0 + 1, min(w, round((float(rx) + float(rw)) * w))))
    y1 = int(max(y0 + 1, min(h, round((float(ry) + float(rh)) * h))))
    gray = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (int(cfg.get("descriptor_width", 96)), int(cfg.get("descriptor_height", 32))))
    return gray.astype(np.float32)
