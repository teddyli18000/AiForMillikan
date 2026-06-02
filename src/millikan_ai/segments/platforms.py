from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class VoltageSample:
    frame_idx: int
    time_s: float
    voltage_V: float | None
    confidence: float
    source: str


def segment_voltage_platforms(
    samples: list[VoltageSample],
    voltage_tolerance_V: float,
    min_duration_s: float,
) -> pd.DataFrame:
    valid = [sample for sample in samples if sample.voltage_V is not None]
    if not valid:
        return pd.DataFrame(
            columns=[
                "platform_id",
                "start_frame",
                "end_frame",
                "start_time_s",
                "end_time_s",
                "voltage_V",
                "voltage_confidence",
                "source",
            ]
        )
    platforms: list[list[VoltageSample]] = [[valid[0]]]
    for sample in valid[1:]:
        current_values = [s.voltage_V for s in platforms[-1] if s.voltage_V is not None]
        median = sorted(current_values)[len(current_values) // 2]
        if abs(float(sample.voltage_V) - float(median)) <= voltage_tolerance_V:
            platforms[-1].append(sample)
        else:
            platforms.append([sample])
    rows = []
    for idx, group in enumerate(platforms, start=1):
        duration = group[-1].time_s - group[0].time_s
        if duration < min_duration_s:
            continue
        values = [float(s.voltage_V) for s in group if s.voltage_V is not None]
        values.sort()
        confidence = sum(s.confidence for s in group) / len(group)
        source = "manual" if any(s.source == "manual" for s in group) else group[0].source
        rows.append(
            {
                "platform_id": f"P{len(rows)+1:03d}",
                "start_frame": group[0].frame_idx,
                "end_frame": group[-1].frame_idx,
                "start_time_s": group[0].time_s,
                "end_time_s": group[-1].time_s,
                "voltage_V": values[len(values) // 2],
                "voltage_confidence": confidence,
                "source": source,
            }
        )
    return pd.DataFrame(rows)

