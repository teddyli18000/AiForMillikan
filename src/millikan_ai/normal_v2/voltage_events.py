from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChangePeak:
    frame_idx: int
    score: float


@dataclass(frozen=True)
class VoltageOperation:
    start_frame: int
    end_frame: int
    peak_score: float
    peak_count: int


@dataclass(frozen=True)
class NormalFallWindow:
    start_frame: int
    end_frame: int
    flags: list[str]
    operations: list[VoltageOperation]


def merge_change_operations(peaks: list[ChangePeak], *, fps: float, merge_window_s: float) -> list[VoltageOperation]:
    if fps <= 0:
        raise ValueError("fps must be positive")
    if not peaks:
        return []
    ordered = sorted(peaks, key=lambda item: item.frame_idx)
    max_gap = max(0, int(round(float(merge_window_s) * fps)))
    operations: list[VoltageOperation] = []
    start = end = int(ordered[0].frame_idx)
    score = float(ordered[0].score)
    count = 1
    for peak in ordered[1:]:
        if int(peak.frame_idx) - end <= max_gap:
            end = int(peak.frame_idx)
            score = max(score, float(peak.score))
            count += 1
        else:
            operations.append(VoltageOperation(start, end, score, count))
            start = end = int(peak.frame_idx)
            score = float(peak.score)
            count = 1
    operations.append(VoltageOperation(start, end, score, count))
    return operations


def normal_window_from_operations(
    operations: list[VoltageOperation],
    *,
    frame_count: int,
    fps: float,
    stable_after_s: float,
) -> NormalFallWindow:
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    if not operations:
        return NormalFallWindow(0, frame_count - 1, ["no_voltage_operation"], [])
    guard = int(round(stable_after_s * fps))
    start = min(frame_count - 1, operations[0].end_frame + guard)
    flags: list[str] = []
    if len(operations) >= 2:
        end = max(start, operations[1].start_frame - 1)
        flags.append("has_recovery_operation")
    else:
        end = frame_count - 1
        flags.append("no_recovery_operation")
    return NormalFallWindow(start, min(end, frame_count - 1), flags, operations)

