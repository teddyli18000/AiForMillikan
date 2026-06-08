from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from millikan_ai.config import load_config, save_config
from millikan_ai.pipeline import run_pipeline, validate_run
from millikan_ai.segments.voltage_change import detect_voltage_platform_changes
from millikan_ai.video.reader import inspect_video

ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class ManualPlatformInput:
    start_frame: int
    end_frame: int
    voltage_V: float
    source: str = "manual_ui"


@dataclass(frozen=True)
class AnalysisRequest:
    video_path: str | Path
    config_path: str | Path = "configs/default.yaml"
    run_dir: str | Path | None = None
    manual_platforms: tuple[ManualPlatformInput, ...] = ()
    progress_callback: ProgressCallback | None = None


@dataclass(frozen=True)
class AnalysisResult:
    run_dir: Path
    config_path: Path
    manifest: dict[str, object]
    validation_errors: list[str]


def manual_platform_row(platform: ManualPlatformInput, fps: float, index: int, frame_count: int | None = None) -> dict[str, object]:
    if platform.start_frame < 0 or platform.end_frame < platform.start_frame:
        raise ValueError(f"invalid platform frame range: {platform.start_frame}:{platform.end_frame}")
    if frame_count is not None and frame_count > 0 and platform.end_frame >= frame_count:
        raise ValueError(f"platform end_frame {platform.end_frame} exceeds video last frame {frame_count - 1}")
    return {
        "platform_id": f"P{index:03d}",
        "start_frame": int(platform.start_frame),
        "end_frame": int(platform.end_frame),
        "start_time_s": platform.start_frame / fps if fps else 0.0,
        "end_time_s": platform.end_frame / fps if fps else 0.0,
        "voltage_V": float(platform.voltage_V),
        "voltage_confidence": 1.0,
        "source": platform.source,
    }


def parse_manual_platform_spec(spec: str, source: str = "manual_cli") -> ManualPlatformInput:
    parts = [part.strip() for part in spec.split(":")]
    if len(parts) != 3:
        raise ValueError(f"platform spec must be START_FRAME:END_FRAME:VOLTAGE, got: {spec}")
    return ManualPlatformInput(int(parts[0]), int(parts[1]), float(parts[2]), source=source)


def manual_platform_rows(platforms: Iterable[ManualPlatformInput], fps: float, frame_count: int | None = None) -> list[dict[str, object]]:
    return [manual_platform_row(platform, fps, index, frame_count) for index, platform in enumerate(platforms, start=1)]


def prepare_analysis_config(video_path: str | Path, config_path: str | Path, manual_platforms: Iterable[ManualPlatformInput]) -> Path:
    platforms = tuple(manual_platforms)
    if not platforms:
        return Path(config_path)
    config = load_config(config_path)
    meta = inspect_video(video_path)
    config["manual_platforms"] = manual_platform_rows(platforms, meta.fps, meta.frame_count)
    target = Path(config["project"]["run_root"]) / "manual_configs" / f"{Path(video_path).stem}_manual_platforms.yaml"
    save_config(config, target)
    return target


def _clean_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    cleaned: list[dict[str, object]] = []
    for record in records:
        row: dict[str, object] = {}
        for key, value in record.items():
            if isinstance(value, float) and value != value:
                row[key] = None
            else:
                row[key] = value
        cleaned.append(row)
    return cleaned


def prepare_auto_platform_config(
    video_path: str | Path,
    config_path: str | Path,
    expected_platform_count: int,
    platform_values: Iterable[float],
) -> Path:
    values = [float(value) for value in platform_values]
    if len(values) != expected_platform_count:
        raise ValueError(f"expected {expected_platform_count} platform voltage values, got {len(values)}")
    config = load_config(config_path)
    meta = inspect_video(video_path)
    suggestions, samples, diagnostics = detect_voltage_platform_changes(video_path, expected_platform_count, config)
    if int(diagnostics.get("detected_platform_count", 0)) != expected_platform_count:
        raise ValueError(f"auto platform detection found {diagnostics.get('detected_platform_count', 0)} platforms; expected {expected_platform_count}")
    bad = [str(row.get("reject_reason", "")) for row in suggestions.to_dict("records") if str(row.get("reject_reason", ""))]
    if bad:
        raise ValueError("auto platform detection rejected suggestions: " + ",".join(sorted(set(bad))))
    platform_rows: list[dict[str, object]] = []
    for index, (suggestion, voltage) in enumerate(zip(suggestions.to_dict("records"), values), start=1):
        platform_rows.append(
            {
                "platform_id": f"P{index:03d}",
                "start_frame": int(suggestion["start_frame"]),
                "end_frame": int(suggestion["end_frame"]),
                "start_time_s": float(suggestion["start_time_s"]),
                "end_time_s": float(suggestion["end_time_s"]),
                "voltage_V": float(voltage),
                "voltage_confidence": float(suggestion.get("confidence", 1.0) or 0.0),
                "source": "auto_boundary_manual_voltage",
            }
        )
    config["manual_platforms"] = manual_platform_rows(
        [ManualPlatformInput(int(row["start_frame"]), int(row["end_frame"]), float(row["voltage_V"]), source=str(row["source"])) for row in platform_rows],
        meta.fps,
        meta.frame_count,
    )
    for row, confidence in zip(config["manual_platforms"], [row["voltage_confidence"] for row in platform_rows]):
        row["voltage_confidence"] = confidence
    config["auto_platform_suggestions"] = _clean_records(suggestions.to_dict("records"))
    config["auto_voltage_samples"] = _clean_records(samples.to_dict("records"))
    config["auto_platform_detection_result"] = diagnostics
    target = Path(config["project"]["run_root"]) / "manual_configs" / f"{Path(video_path).stem}_auto_platforms.yaml"
    save_config(config, target)
    return target


def analyze_video(request: AnalysisRequest) -> AnalysisResult:
    prepared_config = prepare_analysis_config(request.video_path, request.config_path, request.manual_platforms)
    run_dir = run_pipeline(request.video_path, prepared_config, request.run_dir, progress_callback=request.progress_callback)
    errors = validate_run(run_dir, prepared_config)
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return AnalysisResult(run_dir=run_dir, config_path=prepared_config, manifest=manifest, validation_errors=errors)
