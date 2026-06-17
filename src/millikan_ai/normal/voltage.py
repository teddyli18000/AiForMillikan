from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

from millikan_ai.config import load_config
from millikan_ai.segments.voltage_change import (
    _candidate_change_groups,
    _change_scores,
    _read_sampled_descriptors,
    locate_voltage_change_roi,
)
from millikan_ai.video.reader import inspect_video


@dataclass(frozen=True)
class VoltageChangeOperation:
    start_frame: int
    end_frame: int
    representative_frame: int
    score: float

    def to_dict(self, fps: float) -> dict[str, object]:
        return {
            "start_frame": int(self.start_frame),
            "end_frame": int(self.end_frame),
            "representative_frame": int(self.representative_frame),
            "start_time_s": self.start_frame / fps if fps else 0.0,
            "end_time_s": self.end_frame / fps if fps else 0.0,
            "score": float(self.score),
        }


def merge_change_operations(changes: list[dict[str, Any]], fps: float, merge_window_s: float) -> list[VoltageChangeOperation]:
    if not changes:
        return []
    ordered = sorted(changes, key=lambda item: int(item["frame_idx"]))
    merge_gap = max(0, int(round(float(fps) * float(merge_window_s))))
    operations: list[VoltageChangeOperation] = []
    current_start = int(ordered[0].get("sample_start_frame", ordered[0]["frame_idx"]))
    current_end = int(ordered[0].get("sample_end_frame", ordered[0]["frame_idx"]))
    representative = int(ordered[0]["frame_idx"])
    score = float(ordered[0].get("score", 0.0))
    for change in ordered[1:]:
        start = int(change.get("sample_start_frame", change["frame_idx"]))
        end = int(change.get("sample_end_frame", change["frame_idx"]))
        frame = int(change["frame_idx"])
        item_score = float(change.get("score", 0.0))
        if start - current_end <= merge_gap:
            current_end = max(current_end, end)
            if item_score > score:
                score = item_score
                representative = frame
            continue
        operations.append(VoltageChangeOperation(current_start, current_end, representative, score))
        current_start = start
        current_end = end
        representative = frame
        score = item_score
    operations.append(VoltageChangeOperation(current_start, current_end, representative, score))
    return operations


def normal_window_from_operations(
    operations: list[VoltageChangeOperation],
    frame_count: int,
    fps: float,
    *,
    stable_after_s: float = 0.2,
) -> dict[str, object]:
    pad = max(0, int(round(float(stable_after_s) * float(fps))))
    if not operations:
        start = 0
        end = max(0, int(frame_count) - 1)
        flags = ["no_voltage_change_detected"]
    else:
        start = min(max(0, operations[0].end_frame + pad), max(0, int(frame_count) - 1))
        if len(operations) >= 2:
            end = max(start, min(max(0, int(frame_count) - 1), operations[1].start_frame - 1))
            flags = []
        else:
            end = max(0, int(frame_count) - 1)
            flags = ["no_recovery_voltage_detected"]
    return {
        "fall_start_frame": int(start),
        "fall_end_frame": int(end),
        "fall_start_time_s": start / fps if fps else 0.0,
        "fall_end_time_s": end / fps if fps else 0.0,
        "flags": flags,
        "operation_count": len(operations),
    }


def suggest_normal_fall_window(video: str | Path, config_path: str | Path = "configs/default.yaml") -> dict[str, object]:
    config = load_config(config_path)
    cfg = dict(config.get("normal_mode", {}))
    meta = inspect_video(video)
    cap = cv2.VideoCapture(str(video))
    ok, first = cap.read()
    cap.release()
    if not ok:
        return {
            "video_readable": False,
            "flags": ["video_unreadable"],
            "operations": [],
            "suggested_window": {},
        }
    roi = locate_voltage_change_roi(first, config)
    samples, descriptors = _read_sampled_descriptors(Path(video), roi, config)
    scores = _change_scores(descriptors)
    changes = _candidate_change_groups(samples, scores, meta.fps, config)
    operations = merge_change_operations(
        changes,
        meta.fps,
        float(cfg.get("change_merge_window_s", config.get("auto_platform_detection", {}).get("min_change_separation_s", 1.0))),
    )
    suggested = normal_window_from_operations(
        operations,
        meta.frame_count,
        meta.fps,
        stable_after_s=float(cfg.get("stable_after_change_s", config.get("auto_platform_detection", {}).get("transition_padding_s", 0.2))),
    )
    return {
        "video_readable": True,
        "roi": roi.to_list(),
        "operations": [operation.to_dict(meta.fps) for operation in operations],
        "suggested_window": suggested,
        "samples": samples,
    }

