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
from millikan_ai.outputs.validity import build_validity_report
from millikan_ai.outputs.visualization import build_visualization_layers
from millikan_ai.physics.charge import compute_drop_result
from millikan_ai.reporting.markdown import write_analysis_report
from millikan_ai.segments.fitting import fit_track_segments
from millikan_ai.segments.platforms import VoltageSample, segment_voltage_platforms
from millikan_ai.tracking.overlay import render_diagnostic_overlay, render_overlay
from millikan_ai.tracking.tracker import track_multiple_candidates
from millikan_ai.video.reader import inspect_video, read_frame, save_diagnostic_frame


def _run_dir(config: dict, video_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    base = Path(config["project"]["run_root"]) / f"{video_path.stem}_{stamp}"
    if not base.exists():
        return base
    for index in range(1, 1000):
        candidate = Path(f"{base}_{index:03d}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot allocate unique run directory under {base.parent}")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_manual_platforms(config: dict) -> pd.DataFrame:
    rows = config.get("manual_platforms") or []
    return pd.DataFrame(rows, columns=PLATFORMS_COLUMNS) if rows else pd.DataFrame(columns=PLATFORMS_COLUMNS)


def _tracking_roi_from_grid(grid, config: dict) -> Roi:
    roi = grid.roi
    if not bool(config.get("tracking", {}).get("restrict_to_measurement_grid", True)):
        return roi
    x0 = int(grid.x_start_px) if grid.x_start_px is not None else roi.x
    x1 = int(grid.x_end_px) if grid.x_end_px is not None else roi.x + roi.w
    y0 = roi.y
    y1 = int(grid.y_end_px) if grid.y_end_px is not None else roi.y + roi.h
    if x1 <= x0 or y1 <= y0:
        return roi
    x0 = max(roi.x, x0)
    x1 = min(roi.x + roi.w, x1)
    y1 = min(roi.y + roi.h, y1)
    return Roi(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def _build_run_manifest(
    run_dir: Path,
    config: dict,
    diagnostics: dict,
    drop_result: dict,
    elementary: dict,
    quality_scores: dict,
) -> dict[str, object]:
    output = config["output"]
    flags = list(diagnostics.get("flags", [])) + list(drop_result.get("flags", [])) + list(elementary.get("flags", []))
    files = {key: str(run_dir / filename) for key, filename in output.items()}
    return {
        "schema_version": 1,
        "run_dir": str(run_dir),
        "status": {
            "video_readable": bool(diagnostics.get("video", {}).get("readable")),
            "valid_for_q": bool(drop_result.get("valid")),
            "drop_valid": bool(drop_result.get("valid")),
            "ml_training": bool(quality_scores.get("ml_training", False)),
            "flags": flags,
        },
        "counts": {
            "platforms": int(diagnostics.get("platform_count", 0)),
            "drops": int(diagnostics.get("drop_count", 0)),
            "track_rows": int(diagnostics.get("track_rows", 0)),
            "segments": int(diagnostics.get("segment_rows", 0)),
        },
        "coordinate_system": {
            "origin": "top_left_video_pixel",
            "x_positive": "right",
            "y_positive": "down",
            "time_s": "frame_idx / fps",
            "physical_y_velocity": "vy_px_s * scale_y_m_per_px",
        },
        "video": diagnostics.get("video", {}),
        "roi": diagnostics.get("roi", {}),
        "grid": diagnostics.get("grid", {}),
        "visualizations": diagnostics.get("visualizations", {}),
        "primary_results": {
            "charge_abs_C": drop_result.get("result", {}).get("charge_abs_C"),
            "charge_C": drop_result.get("result", {}).get("charge_C"),
            "sigma_charge_C": drop_result.get("result", {}).get("sigma_charge_C"),
            "radius_m": drop_result.get("result", {}).get("radius_m"),
            "elementary_charge": elementary.get("elementary_charge", {}),
        },
        "files": files,
        "frontend_panels": [
            {"id": "summary", "source": files.get("analysis_report_md")},
            {"id": "diagnostic_overlay", "source": files.get("diagnostic_overlay_jpg")},
            {"id": "track_overlay_video", "source": files.get("overlay_mp4")},
            {"id": "platform_editor", "source": files.get("platforms_csv")},
            {"id": "candidate_tracks", "source": files.get("candidate_tracks_summary_csv")},
            {"id": "stable_segments", "source": files.get("best_track_segments_csv")},
            {"id": "multi_drop_segments", "source": files.get("drop_track_segments_csv")},
            {"id": "charge_result", "source": files.get("drop_results_json")},
            {"id": "multi_drop_results", "source": files.get("multi_drop_results_json")},
            {"id": "quality", "source": files.get("quality_scores_json")},
            {"id": "validity", "source": files.get("validity_report_json")},
        ],
    }


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


def _fit_segments_for_tracks(drop_tracks: pd.DataFrame, platforms: pd.DataFrame, scale_y_m_per_px: float, config: dict) -> pd.DataFrame:
    if drop_tracks.empty or platforms.empty:
        return pd.DataFrame(columns=SEGMENT_COLUMNS)
    frames = []
    for _track_id, track in drop_tracks.groupby("track_id", sort=False):
        frames.append(fit_track_segments(track, platforms, scale_y_m_per_px, config))
    if not frames:
        return pd.DataFrame(columns=SEGMENT_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _compute_multi_drop_results(drop_segments: pd.DataFrame, config: dict) -> tuple[list[dict[str, object]], dict[str, object]]:
    drops: list[dict[str, object]] = []
    if not drop_segments.empty:
        for index, (track_id, segments) in enumerate(drop_segments.groupby("track_id", sort=False), start=1):
            result = compute_drop_result(segments, config)
            result["drop_id"] = f"drop_{index:03d}"
            result["track_id"] = str(track_id)
            drops.append(result)
    valid_drop_count = sum(1 for drop in drops if bool(drop.get("valid")))
    return drops, {
        "schema_version": 1,
        "num_total_drops": len(drops),
        "valid_drop_count": valid_drop_count,
        "drops": drops,
    }


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
    tracking_roi = _tracking_roi_from_grid(grid, config)
    drop_tracks, candidate_summary = track_multiple_candidates(video_path, video_path.stem, tracking_roi, platforms, config, grid)
    if drop_tracks.empty:
        drop_tracks = pd.DataFrame(columns=BEST_TRACK_COLUMNS)
    if candidate_summary.empty:
        candidate_summary = pd.DataFrame(columns=CANDIDATE_SUMMARY_COLUMNS)
    selected_ids = []
    if "selected_for_multi_drop" in candidate_summary:
        selected_ids = [str(row["candidate_id"]) for row in candidate_summary.to_dict("records") if bool(row.get("selected_for_multi_drop"))]
    best_track_id = selected_ids[0] if selected_ids else (str(candidate_summary.iloc[0]["candidate_id"]) if not candidate_summary.empty else "")
    if best_track_id and not drop_tracks.empty:
        best_track = drop_tracks[drop_tracks["track_id"] == best_track_id].copy()
    else:
        best_track = pd.DataFrame(columns=BEST_TRACK_COLUMNS)
    best_track.to_csv(target / output_cfg["best_track_csv"], index=False)
    drop_tracks.to_csv(target / output_cfg.get("drop_tracks_csv", "drop_tracks.csv"), index=False)
    candidate_summary.to_csv(target / output_cfg["candidate_tracks_summary_csv"], index=False)
    if grid.scale_y_m_per_px is not None and not drop_tracks.empty and not platforms.empty:
        drop_segments = _fit_segments_for_tracks(drop_tracks, platforms, grid.scale_y_m_per_px, config)
    else:
        drop_segments = pd.DataFrame(columns=SEGMENT_COLUMNS)
    if best_track_id and not drop_segments.empty:
        segments = drop_segments[drop_segments["track_id"] == best_track_id].copy()
    else:
        segments = pd.DataFrame(columns=SEGMENT_COLUMNS)
    segments.to_csv(target / output_cfg["best_track_segments_csv"], index=False)
    drop_segments.to_csv(target / output_cfg.get("drop_track_segments_csv", "drop_track_segments.csv"), index=False)
    overlay_written = False
    diagnostic_overlay_written = render_diagnostic_overlay(video_path, best_track, grid, tracking_roi, target / output_cfg["diagnostic_overlay_jpg"])
    if not best_track.empty:
        overlay_written = render_overlay(video_path, best_track, grid, target / output_cfg["overlay_mp4"])
    drop_results, multi_drop_results = _compute_multi_drop_results(drop_segments, config)
    drop_result = next((drop for drop in drop_results if drop.get("track_id") == best_track_id), None) or compute_drop_result(segments, config)
    _write_json(target / output_cfg["drop_results_json"], drop_result)
    _write_json(target / output_cfg.get("multi_drop_results_json", "multi_drop_results.json"), multi_drop_results)
    quality_scores = {
        "implemented": "non_ml_hard_rule_summary",
        "ml_training": False,
        "best_candidate": candidate_summary.head(1).to_dict("records"),
        "valid_drop_count": int(multi_drop_results["valid_drop_count"]),
        "total_drop_count": int(multi_drop_results["num_total_drops"]),
        "ml_filtering": "not_in_scope",
        "drop_valid": bool(drop_result.get("valid")),
        "drop_flags": drop_result.get("flags", []),
    }
    _write_json(target / output_cfg["quality_scores_json"], quality_scores)
    elementary = estimate_elementary_charge(drop_results or [drop_result], config)
    _write_json(target / output_cfg["elementary_charge_result_json"], elementary)
    visualization_layers = build_visualization_layers(meta, grid, tracking_roi, voltage_roi, best_track, platforms)
    _write_json(target / output_cfg["visualization_layers_json"], visualization_layers)
    diagnostics = {
        "video": meta.to_dict(),
        "roi": {
            "microscope_roi": grid.roi.to_list(),
            "tracking_roi": tracking_roi.to_list(),
            "voltage_roi": voltage_roi.to_list(),
            "dynamic_voltage_roi": dynamic_voltage_roi,
        },
        "grid": grid.to_dict(),
        "platform_count": int(len(platforms)),
        "drop_count": int(multi_drop_results["num_total_drops"]),
        "track_rows": int(len(best_track)),
        "all_track_rows": int(len(drop_tracks)),
        "segment_rows": int(len(segments)),
        "all_segment_rows": int(len(drop_segments)),
        "overlay_written": overlay_written,
        "diagnostic_overlay_written": diagnostic_overlay_written,
        "visualizations": {
            "visualization_layers_json": str(target / output_cfg["visualization_layers_json"]),
            "diagnostic_overlay_jpg": str(target / output_cfg["diagnostic_overlay_jpg"]),
            "overlay_mp4": str(target / output_cfg["overlay_mp4"]),
        },
        "time_source": "opencv_fps_frame_index",
        "flags": [],
    }
    if platforms.empty:
        diagnostics["flags"].append("requires_manual_platforms")
    if grid.scale_y_m_per_px is None:
        diagnostics["flags"].append("requires_manual_grid_calibration")
    _write_json(target / output_cfg["diagnostics_json"], diagnostics)
    validity_report = build_validity_report(diagnostics, drop_result, elementary, platforms, segments, candidate_summary)
    _write_json(target / output_cfg["validity_report_json"], validity_report)
    write_summary(target, config)
    write_analysis_report(target, config)
    manifest = _build_run_manifest(target, config, diagnostics, drop_result, elementary, quality_scores)
    _write_json(target / output_cfg.get("run_manifest_json", "run_manifest.json"), manifest)
    return target


def validate_run(run_dir: str | Path, config_path: str | Path = "configs/default.yaml") -> list[str]:
    config = load_config(config_path)
    root = Path(run_dir)
    output = config["output"]
    errors: list[str] = []
    errors.extend(validate_columns(root / output.get("voltage_samples_csv", "voltage_samples.csv"), VOLTAGE_SAMPLE_COLUMNS))
    errors.extend(validate_columns(root / output["platforms_csv"], PLATFORMS_COLUMNS))
    errors.extend(validate_columns(root / output["best_track_csv"], BEST_TRACK_COLUMNS))
    errors.extend(validate_columns(root / output.get("drop_tracks_csv", "drop_tracks.csv"), BEST_TRACK_COLUMNS))
    errors.extend(validate_columns(root / output["best_track_segments_csv"], SEGMENT_COLUMNS))
    errors.extend(validate_columns(root / output.get("drop_track_segments_csv", "drop_track_segments.csv"), SEGMENT_COLUMNS))
    errors.extend(validate_columns(root / output["candidate_tracks_summary_csv"], CANDIDATE_SUMMARY_COLUMNS))
    for key in [
        "diagnostics_json",
        "drop_results_json",
        "multi_drop_results_json",
        "quality_scores_json",
        "elementary_charge_result_json",
        "validity_report_json",
        "visualization_layers_json",
    ]:
        path = root / output[key]
        if not path.exists():
            errors.append(f"missing file: {path.name}")
        else:
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid json {path.name}: {exc}")
    manifest_path = root / output.get("run_manifest_json", "run_manifest.json")
    for path in [manifest_path]:
        if not path.exists():
            errors.append(f"missing file: {path.name}")
        else:
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid json {path.name}: {exc}")
    diagnostic_overlay = root / output.get("diagnostic_overlay_jpg", "diagnostic_overlay.jpg")
    if not diagnostic_overlay.exists():
        errors.append(f"missing file: {diagnostic_overlay.name}")
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
