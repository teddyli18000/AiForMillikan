from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import pandas as pd

from millikan_ai.calibration.grid import Roi, calibrate_grid
from millikan_ai.config import load_config, save_config
from millikan_ai.elementary.estimate import estimate_elementary_charge
from millikan_ai.ocr.voltage import find_voltage_roi, read_voltage_from_frame
from millikan_ai.outputs.schemas import (
    BEST_TRACK_COLUMNS,
    CANDIDATE_SUMMARY_COLUMNS,
    PLATFORMS_COLUMNS,
    SEGMENT_COLUMNS,
    VOLTAGE_SAMPLE_COLUMNS,
    validate_columns,
)
from millikan_ai.physics.charge import compute_drop_result
from millikan_ai.reporting.markdown import write_analysis_report
from millikan_ai.segments.fitting import fit_track_segments
from millikan_ai.segments.platforms import VoltageSample, segment_voltage_platforms
from millikan_ai.tracking.overlay import render_overlay
from millikan_ai.tracking.tracker import track_best_candidate
from millikan_ai.video.reader import inspect_video, read_frame, save_diagnostic_frame


def _run_dir(config: dict, video_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(config["project"]["run_root"]) / f"{video_path.stem}_{stamp}"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_manual_platforms(config: dict) -> pd.DataFrame:
    rows = config.get("manual_platforms") or []
    return pd.DataFrame(rows, columns=PLATFORMS_COLUMNS) if rows else pd.DataFrame(columns=PLATFORMS_COLUMNS)


def _sample_voltage_series(
    video_path: Path,
    roi: Roi,
    config: dict,
    max_voltage: float = 1000.0,
    dynamic_roi: bool = False,
) -> tuple[list[VoltageSample], pd.DataFrame]:
    meta = inspect_video(video_path)
    every = int(config["ocr"]["sample_every_n_frames"])
    samples: list[VoltageSample] = []
    rows: list[dict[str, object]] = []
    for frame_idx in range(0, meta.frame_count, max(1, every)):
        frame = read_frame(video_path, frame_idx)
        sample_roi = find_voltage_roi(frame) if dynamic_roi else roi
        reading = read_voltage_from_frame(frame, sample_roi)
        voltage = reading.voltage_V
        source = reading.source
        confidence = reading.confidence
        accepted = True
        reject_reason = ""
        if voltage is None or abs(voltage) > max_voltage or reading.confidence < float(config["ocr"]["min_confidence"]):
            voltage = None
            source = "template_ocr_rejected"
            confidence = min(confidence, 0.2)
            accepted = False
            if reading.voltage_V is None:
                reject_reason = "no_voltage_value"
            elif abs(reading.voltage_V) > max_voltage:
                reject_reason = "voltage_out_of_range"
            else:
                reject_reason = "low_confidence"
        samples.append(VoltageSample(frame_idx, frame_idx / meta.fps if meta.fps else 0.0, voltage, confidence, source))
        rows.append(
            {
                "frame_idx": frame_idx,
                "time_s": frame_idx / meta.fps if meta.fps else 0.0,
                "voltage_V": voltage,
                "confidence": confidence,
                "source": source,
                "raw_text": reading.text,
                "accepted": accepted,
                "reject_reason": reject_reason,
                "roi_x": sample_roi.x,
                "roi_y": sample_roi.y,
                "roi_w": sample_roi.w,
                "roi_h": sample_roi.h,
            }
        )
    return samples, pd.DataFrame(rows, columns=VOLTAGE_SAMPLE_COLUMNS)


def run_pipeline(video: str | Path, config_path: str | Path, run_dir: str | Path | None = None) -> Path:
    config = load_config(config_path)
    video_path = Path(video)
    target = Path(run_dir) if run_dir else _run_dir(config, video_path)
    target.mkdir(parents=True, exist_ok=True)
    output_cfg = config["output"]
    meta = inspect_video(video_path)
    save_config(config, target / "run_config.yaml")
    diagnostics_dir = target / config["video"]["diagnostics_dir"]
    save_diagnostic_frame(video_path, diagnostics_dir / "first_frame.jpg", 0)
    first_frame = read_frame(video_path, 0)
    microscope_roi = Roi.from_config(config["roi"].get("microscope_roi"))
    configured_voltage_roi = Roi.from_config(config["roi"].get("voltage_roi"))
    voltage_roi = configured_voltage_roi or find_voltage_roi(first_frame)
    dynamic_voltage_roi = configured_voltage_roi is None and bool(config["ocr"].get("dynamic_voltage_roi", True))
    grid = calibrate_grid(
        first_frame,
        microscope_roi,
        float(config["calibration"]["measurement_distance_m"]),
        int(config["calibration"]["min_grid_lines"]),
    )
    manual_platforms = _load_manual_platforms(config)
    voltage_samples = pd.DataFrame(columns=VOLTAGE_SAMPLE_COLUMNS)
    if not manual_platforms.empty:
        platforms = manual_platforms
    else:
        samples, voltage_samples = _sample_voltage_series(video_path, voltage_roi, config, dynamic_roi=dynamic_voltage_roi)
        platforms = segment_voltage_platforms(
            samples,
            float(config["ocr"]["voltage_tolerance_V"]),
            float(config["ocr"]["min_platform_duration_s"]),
        )
    if platforms.empty:
        platforms = pd.DataFrame(columns=PLATFORMS_COLUMNS)
    voltage_samples.to_csv(target / output_cfg.get("voltage_samples_csv", "voltage_samples.csv"), index=False)
    platforms.to_csv(target / output_cfg["platforms_csv"], index=False)
    best_track, candidate_summary = track_best_candidate(video_path, video_path.stem, grid.roi, platforms, config)
    if best_track.empty:
        best_track = pd.DataFrame(columns=BEST_TRACK_COLUMNS)
    if candidate_summary.empty:
        candidate_summary = pd.DataFrame(columns=CANDIDATE_SUMMARY_COLUMNS)
    best_track.to_csv(target / output_cfg["best_track_csv"], index=False)
    candidate_summary.to_csv(target / output_cfg["candidate_tracks_summary_csv"], index=False)
    if grid.scale_y_m_per_px is not None and not best_track.empty and not platforms.empty:
        segments = fit_track_segments(best_track, platforms, grid.scale_y_m_per_px, config)
    else:
        segments = pd.DataFrame(columns=SEGMENT_COLUMNS)
    segments.to_csv(target / output_cfg["best_track_segments_csv"], index=False)
    overlay_written = False
    if not best_track.empty:
        overlay_written = render_overlay(video_path, best_track, grid, target / output_cfg["overlay_mp4"])
    drop_result = compute_drop_result(segments, config)
    _write_json(target / output_cfg["drop_results_json"], drop_result)
    quality_scores = {
        "implemented": "non_ml_hard_rule_summary",
        "ml_training": False,
        "best_candidate": candidate_summary.head(1).to_dict("records"),
        "ml_filtering": "not_in_scope",
        "drop_valid": bool(drop_result.get("valid")),
        "drop_flags": drop_result.get("flags", []),
    }
    _write_json(target / output_cfg["quality_scores_json"], quality_scores)
    elementary = estimate_elementary_charge([drop_result], config)
    _write_json(target / output_cfg["elementary_charge_result_json"], elementary)
    diagnostics = {
        "video": meta.to_dict(),
        "roi": {"microscope_roi": grid.roi.to_list(), "voltage_roi": voltage_roi.to_list(), "dynamic_voltage_roi": dynamic_voltage_roi},
        "grid": grid.to_dict(),
        "platform_count": int(len(platforms)),
        "track_rows": int(len(best_track)),
        "segment_rows": int(len(segments)),
        "overlay_written": overlay_written,
        "time_source": "opencv_fps_frame_index",
        "flags": [],
    }
    if platforms.empty:
        diagnostics["flags"].append("requires_manual_platforms")
    if grid.scale_y_m_per_px is None:
        diagnostics["flags"].append("requires_manual_grid_calibration")
    _write_json(target / output_cfg["diagnostics_json"], diagnostics)
    write_summary(target, config)
    write_analysis_report(target, config)
    return target


def validate_run(run_dir: str | Path, config_path: str | Path = "configs/default.yaml") -> list[str]:
    config = load_config(config_path)
    root = Path(run_dir)
    output = config["output"]
    errors: list[str] = []
    errors.extend(validate_columns(root / output.get("voltage_samples_csv", "voltage_samples.csv"), VOLTAGE_SAMPLE_COLUMNS))
    errors.extend(validate_columns(root / output["platforms_csv"], PLATFORMS_COLUMNS))
    errors.extend(validate_columns(root / output["best_track_csv"], BEST_TRACK_COLUMNS))
    errors.extend(validate_columns(root / output["best_track_segments_csv"], SEGMENT_COLUMNS))
    errors.extend(validate_columns(root / output["candidate_tracks_summary_csv"], CANDIDATE_SUMMARY_COLUMNS))
    for key in ["diagnostics_json", "drop_results_json", "quality_scores_json", "elementary_charge_result_json"]:
        path = root / output[key]
        if not path.exists():
            errors.append(f"missing file: {path.name}")
        else:
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid json {path.name}: {exc}")
    if not (root / output.get("analysis_report_md", "analysis_report.md")).exists():
        errors.append("missing file: analysis_report.md")
    return errors


def write_summary(run_dir: str | Path, config: dict | None = None) -> Path:
    root = Path(run_dir)
    config = config or load_config(root / "run_config.yaml")
    diagnostics_path = root / config["output"]["diagnostics_json"]
    drop_path = root / config["output"]["drop_results_json"]
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8")) if diagnostics_path.exists() else {}
    drop = json.loads(drop_path.read_text(encoding="utf-8")) if drop_path.exists() else {}
    lines = [
        f"Run: {root.name}",
        f"Video: {diagnostics.get('video', {}).get('path', '')}",
        f"Platforms: {diagnostics.get('platform_count', 0)}",
        f"Track rows: {diagnostics.get('track_rows', 0)}",
        f"Segment rows: {diagnostics.get('segment_rows', 0)}",
        f"Drop valid: {drop.get('valid')}",
        f"Flags: {', '.join(diagnostics.get('flags', []) + drop.get('flags', []))}",
    ]
    target = root / config["output"]["summary_txt"]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
