from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import traceback
import zipfile
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from millikan_ai.api import (
    AnalysisRequest,
    ManualPlatformInput,
    analyze_video,
    prepare_auto_platform_config,
)
from millikan_ai.config import load_config
from millikan_ai.downstream import run_downstream_analysis
from millikan_ai.pipeline import validate_run
from millikan_ai.segments.voltage_change import detect_voltage_platform_changes
from millikan_ai.video.reader import inspect_video


Json = dict[str, Any]
_MISSING = object()


def _camel_case(key: str) -> str:
    head, *tail = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _value(payload: Json, key: str, default: Any = _MISSING) -> Any:
    for candidate in (key, _camel_case(key)):
        if candidate in payload:
            return payload[candidate]
    if default is not _MISSING:
        return default
    raise KeyError(key)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _read_json(path: Path) -> Json:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read_csv_records(path: Path, limit: int | None = None) -> list[Json]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[Json] = []
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            rows.append({key: _coerce_cell(value) for key, value in row.items()})
        return rows


def _coerce_cell(value: str | None) -> Any:
    if value is None or value == "":
        return None
    text = str(value)
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    try:
        if any(marker in text for marker in [".", "e", "E"]):
            number = float(text)
            return number if math.isfinite(number) else None
        return int(text)
    except ValueError:
        return text


def _manual_platforms(rows: list[Json] | None) -> tuple[ManualPlatformInput, ...]:
    platforms = []
    for row in rows or []:
        platforms.append(
            ManualPlatformInput(
                start_frame=int(_value(row, "start_frame")),
                end_frame=int(_value(row, "end_frame")),
                voltage_V=float(_value(row, "voltage_V")),
                source=str(_value(row, "source", "manual_ui") or "manual_ui"),
            )
        )
    return tuple(platforms)


def _write_line(payload: Json) -> None:
    sys.stdout.write(json.dumps(_json_safe(payload), ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _progress_emitter(request_id: str) -> Callable[[float, str], None]:
    def emit(percent: float, label: str) -> None:
        _write_line(
            {
                "id": request_id,
                "type": "progress",
                "payload": {"percent": float(percent), "label": str(label)},
            }
        )

    return emit


def _artifact_bundle(run_dir: Path, limit_tables: int = 400) -> Json:
    manifest = _read_json(run_dir / "run_manifest.json")
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}

    def file_path(key: str, fallback: str) -> Path:
        value = files.get(key)
        return Path(value) if value else run_dir / fallback

    return {
        "run_dir": str(run_dir),
        "manifest": manifest,
        "summary": _read_text(file_path("summary_txt", "summary.txt")),
        "analysis_report_md": _read_text(file_path("analysis_report_md", "analysis_report.md")),
        "diagnostics": _read_json(file_path("diagnostics_json", "diagnostics.json")),
        "validity_report": _read_json(file_path("validity_report_json", "validity_report.json")),
        "visualization_layers": _read_json(file_path("visualization_layers_json", "visualization_layers.json")),
        "drop_results": _read_json(file_path("drop_results_json", "drop_results.json")),
        "multi_drop_results": _read_json(file_path("multi_drop_results_json", "multi_drop_results.json")),
        "elementary_charge_result": _read_json(file_path("elementary_charge_result_json", "elementary_charge_result.json")),
        "model_comparison": _read_json(file_path("model_comparison_json", "model_comparison.json")),
        "uncertainty_details": _read_json(file_path("uncertainty_details_json", "uncertainty_details.json")),
        "quality_scores": _read_json(file_path("quality_scores_json", "quality_scores.json")),
        "plots_data": _read_json(file_path("plots_data_json", "plots_data.json")),
        "tables": {
            "platforms": _read_csv_records(file_path("platforms_csv", "platforms.csv"), limit_tables),
            "auto_platform_suggestions": _read_csv_records(file_path("auto_platform_suggestions_csv", "auto_platform_suggestions.csv"), limit_tables),
            "candidate_tracks_summary": _read_csv_records(file_path("candidate_tracks_summary_csv", "candidate_tracks_summary.csv"), limit_tables),
            "best_track_segments": _read_csv_records(file_path("best_track_segments_csv", "best_track_segments.csv"), limit_tables),
            "drop_track_segments": _read_csv_records(file_path("drop_track_segments_csv", "drop_track_segments.csv"), limit_tables),
            "drop_charge_results": _read_csv_records(file_path("drop_charge_results_csv", "drop_charge_results.csv"), limit_tables),
            "platform_velocity_results": _read_csv_records(file_path("platform_velocity_results_csv", "platform_velocity_results.csv"), limit_tables),
            "trajectory_quality_scores": _read_csv_records(file_path("trajectory_quality_scores_csv", "trajectory_quality_scores.csv"), limit_tables),
        },
    }


def _op_video_inspect(payload: Json, _request_id: str) -> Json:
    meta = inspect_video(_value(payload, "video_path"))
    return {"metadata": meta.to_dict()}


def _op_platform_detect_boundaries(payload: Json, _request_id: str) -> Json:
    config_path = _value(payload, "config_path", None) or "configs/default.yaml"
    config = load_config(config_path)
    suggestions, samples, diagnostics = detect_voltage_platform_changes(
        _value(payload, "video_path"),
        int(_value(payload, "expected_platform_count")),
        config,
    )
    return {
        "diagnostics": diagnostics,
        "suggestions": suggestions.to_dict("records"),
        "samples": samples.to_dict("records"),
    }


def _op_analysis_run(payload: Json, request_id: str) -> Json:
    result = analyze_video(
        AnalysisRequest(
            video_path=_value(payload, "video_path"),
            config_path=_value(payload, "config_path", None) or "configs/default.yaml",
            run_dir=_value(payload, "run_dir", None),
            manual_platforms=_manual_platforms(_value(payload, "manual_platforms", None)),
            progress_callback=_progress_emitter(request_id),
        )
    )
    return {
        "run_dir": result.run_dir,
        "config_path": result.config_path,
        "manifest": result.manifest,
        "validation_errors": result.validation_errors,
        "artifacts": _artifact_bundle(result.run_dir),
    }


def _op_analysis_run_auto(payload: Json, request_id: str) -> Json:
    config_path = prepare_auto_platform_config(
        _value(payload, "video_path"),
        _value(payload, "config_path", None) or "configs/default.yaml",
        int(_value(payload, "expected_platform_count")),
        _value(payload, "platform_values", []) or [],
    )
    result = analyze_video(
        AnalysisRequest(
            video_path=_value(payload, "video_path"),
            config_path=config_path,
            run_dir=_value(payload, "run_dir", None),
            progress_callback=_progress_emitter(request_id),
        )
    )
    return {
        "run_dir": result.run_dir,
        "config_path": result.config_path,
        "manifest": result.manifest,
        "validation_errors": result.validation_errors,
        "artifacts": _artifact_bundle(result.run_dir),
    }


def _op_analysis_load_run(payload: Json, _request_id: str) -> Json:
    return {"artifacts": _artifact_bundle(Path(_value(payload, "run_dir")))}


def _op_analysis_validate(payload: Json, _request_id: str) -> Json:
    errors = validate_run(_value(payload, "run_dir"), _value(payload, "config_path", None) or "configs/default.yaml")
    return {"valid": not errors, "errors": errors}


def _frame_from_records(records: list[Json]) -> pd.DataFrame:
    return pd.DataFrame(records or [])


def _op_downstream_run(payload: Json, _request_id: str) -> Json:
    config = load_config(_value(payload, "config_path", None) or "configs/default.yaml")
    config_overrides = _value(payload, "config_overrides", None)
    if isinstance(config_overrides, dict):
        _merge_dict(config, config_overrides)
    result = run_downstream_analysis(
        trajectories=_frame_from_records(_value(payload, "trajectories", []) or []),
        platforms=_frame_from_records(_value(payload, "platforms", []) or []),
        scale_y_m_per_px=float(_value(payload, "scale_y_m_per_px")),
        config=config,
        run_dir=_value(payload, "run_dir", None),
    )
    run_dir = Path(result["run_dir"])
    return {
        "run_dir": run_dir,
        "multi_drop_results": result["multi_drop_results"],
        "elementary": result["elementary"],
        "plots_data": result["plots_data"],
        "artifacts": _artifact_bundle(run_dir),
    }


def _merge_dict(base: Json, overrides: Json) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_dict(base[key], value)
        else:
            base[key] = value


def _op_report_export(payload: Json, _request_id: str) -> Json:
    run_dir = Path(_value(payload, "run_dir"))
    destination = Path(_value(payload, "destination_dir"))
    destination.mkdir(parents=True, exist_ok=True)
    mode = str(_value(payload, "mode", None) or "folder")
    exported = _export_run_package(run_dir, destination)
    if mode == "zip":
        zip_path = destination / f"{run_dir.name}_millikan_package.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in exported:
                archive.write(path, path.relative_to(destination))
        return {"destination": destination, "zip_path": zip_path, "files": exported}
    return {"destination": destination, "files": exported}


def _export_run_package(run_dir: Path, destination: Path) -> list[Path]:
    manifest = _read_json(run_dir / "run_manifest.json")
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    keys = [
        "analysis_report_md",
        "run_manifest_json",
        "validity_report_json",
        "plots_data_json",
        "visualization_layers_json",
        "diagnostic_overlay_jpg",
        "overlay_mp4",
        "platforms_csv",
        "candidate_tracks_summary_csv",
        "drop_charge_results_csv",
        "platform_velocity_results_csv",
        "multi_drop_results_json",
        "elementary_charge_result_json",
        "model_comparison_json",
        "uncertainty_details_json",
    ]
    exported: list[Path] = []
    for key in keys:
        source = Path(files[key]) if key in files else run_dir / _fallback_name(key)
        if source.exists():
            target = destination / source.name
            shutil.copy2(source, target)
            exported.append(target)
    package_manifest = destination / "export_manifest.json"
    package_manifest.write_text(
        json.dumps(
            {
                "source_run_dir": str(run_dir),
                "exported_files": [path.name for path in exported],
                "frontend_note": "PDF is generated by the Electron renderer when requested.",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    exported.append(package_manifest)
    return exported


def _fallback_name(key: str) -> str:
    return {
        "analysis_report_md": "analysis_report.md",
        "run_manifest_json": "run_manifest.json",
        "validity_report_json": "validity_report.json",
        "plots_data_json": "plots_data.json",
        "visualization_layers_json": "visualization_layers.json",
        "diagnostic_overlay_jpg": "diagnostic_overlay.jpg",
        "overlay_mp4": "overlay_best_track.mp4",
        "platforms_csv": "platforms.csv",
        "candidate_tracks_summary_csv": "candidate_tracks_summary.csv",
        "drop_charge_results_csv": "drop_charge_results.csv",
        "platform_velocity_results_csv": "platform_velocity_results.csv",
        "multi_drop_results_json": "multi_drop_results.json",
        "elementary_charge_result_json": "elementary_charge_result.json",
        "model_comparison_json": "model_comparison.json",
        "uncertainty_details_json": "uncertainty_details.json",
    }.get(key, key)


OPS: dict[str, Callable[[Json, str], Json]] = {
    "video.inspect": _op_video_inspect,
    "platform.detectBoundaries": _op_platform_detect_boundaries,
    "analysis.run": _op_analysis_run,
    "analysis.runAuto": _op_analysis_run_auto,
    "analysis.loadRun": _op_analysis_load_run,
    "analysis.validate": _op_analysis_validate,
    "downstream.run": _op_downstream_run,
    "report.export": _op_report_export,
}


def handle_message(message: Json) -> None:
    request_id = str(message.get("id") or "")
    op = str(message.get("op") or "")
    try:
        if op not in OPS:
            raise ValueError(f"unknown operation: {op}")
        payload = OPS[op](message.get("payload") or {}, request_id)
        _write_line({"id": request_id, "type": "result", "payload": payload})
    except Exception as exc:
        _write_line(
            {
                "id": request_id,
                "type": "error",
                "error": {
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            }
        )


def run_stdio() -> int:
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError as exc:
            _write_line({"id": "", "type": "error", "error": {"message": f"invalid json: {exc}"}})
            continue
        handle_message(message)
    return 0


def run_once(op: str, payload_path: str) -> int:
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    handle_message({"id": "once", "op": op, "payload": payload})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="millikan-desktop-worker")
    parser.add_argument("--once", choices=sorted(OPS), help="Run one operation using --payload-json.")
    parser.add_argument("--payload-json", help="Path to a JSON payload for --once.")
    args = parser.parse_args(argv)
    if args.once:
        if not args.payload_json:
            parser.error("--payload-json is required with --once")
        return run_once(args.once, args.payload_json)
    return run_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
