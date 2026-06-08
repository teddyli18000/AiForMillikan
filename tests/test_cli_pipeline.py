import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml

from millikan_ai.cli.__main__ import _parse_platform_spec, _prompt_platform_rows
from millikan_ai.calibration.grid import GridCalibration, Roi
from millikan_ai.config import load_config, save_config
from millikan_ai import pipeline
from millikan_ai.pipeline import _select_primary_drop, _tracking_roi_from_grid, run_pipeline, validate_run
from millikan_ai.tracking.tracker import _grid_clear_fraction, _roi_clear_fraction, track_multiple_candidates


def _make_synthetic_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (30, y), (230, y), (255, 255, 255), 2)
        x = 90
        y = 50 + idx * 0.35
        cv2.circle(frame, (int(x), int(y)), 4, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def _make_synthetic_multi_drop_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for idx in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (30, y), (230, y), (255, 255, 255), 2)
        cv2.circle(frame, (90, int(48 + idx * 0.30)), 4, (255, 255, 255), -1)
        cv2.circle(frame, (155, int(58 + idx * 0.24)), 4, (230, 230, 230), -1)
        writer.write(frame)
    writer.release()


def _make_synthetic_three_valid_drop_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (340, 260))
    positions = [
        {"x": 75, "y": 42.0, "slow": 0.36, "fast": 0.18, "brightness": 255},
        {"x": 145, "y": 82.0, "slow": 0.44, "fast": 0.22, "brightness": 240},
        {"x": 215, "y": 122.0, "slow": 0.52, "fast": 0.26, "brightness": 225},
    ]
    for idx in range(180):
        frame = np.zeros((260, 340, 3), dtype=np.uint8)
        for y in [25, 65, 105, 145, 185, 225]:
            cv2.line(frame, (30, y), (280, y), (255, 255, 255), 2)
        for drop in positions:
            step = drop["slow"] if idx < 90 else drop["fast"]
            drop["y"] += step
            cv2.circle(frame, (int(drop["x"]), int(drop["y"])), 5, (drop["brightness"], drop["brightness"], drop["brightness"]), -1)
        writer.write(frame)
    writer.release()


def test_pipeline_with_manual_platforms_on_synthetic_video(tmp_path: Path):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)
    config = load_config("configs/default.yaml")
    config["roi"]["microscope_roi"] = [20, 20, 240, 200]
    config["manual_platforms"] = [
        {"platform_id": "P001", "start_frame": 0, "end_frame": 59, "start_time_s": 0.0, "end_time_s": 1.97, "voltage_V": 0.0, "voltage_confidence": 1.0, "source": "manual"},
        {"platform_id": "P002", "start_frame": 60, "end_frame": 119, "start_time_s": 2.0, "end_time_s": 3.97, "voltage_V": 200.0, "voltage_confidence": 1.0, "source": "manual"},
    ]
    config["segment"]["stable_min_duration_s"] = 0.5
    config["segment"]["transient_drop_s"] = 0.1
    config["segment"]["min_valid_points"] = 10
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)
    run_dir = run_pipeline(video, config_path, tmp_path / "run")
    errors = validate_run(run_dir, config_path)
    assert errors == []
    diagnostics = json.loads((run_dir / "diagnostics.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    layers = json.loads((run_dir / "visualization_layers.json").read_text(encoding="utf-8"))
    validity = json.loads((run_dir / "validity_report.json").read_text(encoding="utf-8"))
    assert diagnostics["track_rows"] > 0
    assert diagnostics["diagnostic_overlay_written"] is True
    assert (run_dir / "diagnostic_overlay.jpg").exists()
    assert (run_dir / "overlay_best_track.mp4").exists()
    assert manifest["schema_version"] == 1
    assert manifest["coordinate_system"]["y_positive"] == "down"
    assert manifest["files"]["diagnostic_overlay_jpg"].endswith("diagnostic_overlay.jpg")
    assert any(panel["id"] == "platform_editor" for panel in manifest["frontend_panels"])
    assert any(panel["id"] == "validity" for panel in manifest["frontend_panels"])
    layer_ids = {layer["id"] for layer in layers["layers"]}
    assert {"pixel_axes", "tracking_roi", "best_track"}.issubset(layer_ids)
    assert layers["coordinate_system"]["x_positive"] == "right"
    assert isinstance(validity["overall_valid_for_q"], bool)
    assert isinstance(validity["blocking_failed_checks"], list)
    assert "drop_q_valid" in {check["id"] for check in validity["checks"]}


def test_pipeline_mainline_no_longer_exposes_ocr_sampling():
    assert not hasattr(pipeline, "_sample_voltage_series")
    assert not hasattr(pipeline, "read_voltage_from_frame")
    assert not hasattr(pipeline, "find_voltage_roi")


def test_pipeline_reports_progress_stages(tmp_path: Path):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)
    config = load_config("configs/default.yaml")
    config["roi"]["microscope_roi"] = [20, 20, 240, 200]
    config["manual_platforms"] = [
        {"platform_id": "P001", "start_frame": 0, "end_frame": 59, "start_time_s": 0.0, "end_time_s": 1.97, "voltage_V": 0.0, "voltage_confidence": 1.0, "source": "manual"},
        {"platform_id": "P002", "start_frame": 60, "end_frame": 119, "start_time_s": 2.0, "end_time_s": 3.97, "voltage_V": 200.0, "voltage_confidence": 1.0, "source": "manual"},
    ]
    config["segment"]["stable_min_duration_s"] = 0.5
    config["segment"]["transient_drop_s"] = 0.1
    config["segment"]["min_valid_points"] = 10
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)
    events: list[tuple[float, str]] = []

    run_pipeline(video, config_path, tmp_path / "run", progress_callback=lambda percent, label: events.append((percent, label)))

    labels = [label for _percent, label in events]
    assert labels[0] == "inspect video"
    assert "tracking droplets" in labels
    assert labels[-1] == "write manifest"
    assert all(0.0 <= percent <= 1.0 for percent, _label in events)


def test_root_interactive_entry_collects_manual_platforms(monkeypatch, tmp_path: Path, capsys):
    video = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video)
    config = load_config("configs/default.yaml")
    config["project"]["run_root"] = str(tmp_path / "runs")
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)
    run_dir = tmp_path / "run_result"
    (run_dir / "analysis_report.md").parent.mkdir(parents=True)
    (run_dir / "analysis_report.md").write_text("# report\n", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(json.dumps({"schema_version": 1, "files": {}}), encoding="utf-8")

    import run_millikan

    captured = {}

    def fake_analyze_video(request):
        captured["request"] = request
        return run_millikan.AnalysisResult(run_dir=run_dir, config_path=Path(request.config_path), manifest={"schema_version": 1}, validation_errors=[])

    answers = iter(
        [
            str(video),
            str(config_path),
            "",
            "",
            "",
            "2",
            "0",
            "59",
            "0",
            "60",
            "119",
            "175",
            "y",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(run_millikan, "analyze_video", fake_analyze_video)

    exit_code = run_millikan.run_interactive()

    out = capsys.readouterr().out
    request = captured["request"]
    assert exit_code == 0
    assert Path(request.video_path) == video
    assert len(request.manual_platforms) == 2
    assert request.manual_platforms[0].source == "manual_cli"
    assert str(run_dir) in out
    assert "analysis_report.md" in out


def test_root_platform_prompt_defaults_split_frame_ranges(monkeypatch):
    import run_millikan

    answers = iter(["2", "", "", "0", "", "", "175"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    platforms = run_millikan._prompt_platforms(fps=30.0, frame_count=120)

    assert platforms[0].start_frame == 0
    assert platforms[0].end_frame == 59
    assert platforms[1].start_frame == 60
    assert platforms[1].end_frame == 119


def test_track_multiple_candidates_returns_distinct_tracks(tmp_path: Path):
    video = tmp_path / "multi.mp4"
    _make_synthetic_multi_drop_video(video)
    config = load_config("configs/default.yaml")
    config["segment"]["stable_min_duration_s"] = 0.5
    config["segment"]["transient_drop_s"] = 0.1
    config["segment"]["min_valid_points"] = 10
    config["segment"]["min_fit_r2"] = 0.5
    config["segment"]["min_motion_displacement_px"] = 1
    config["tracking"]["top_k_seeds"] = 10
    config["tracking"]["max_drops"] = 3
    roi = Roi(20, 20, 240, 200)
    platforms = pd.DataFrame(
        [
            {"platform_id": "P001", "start_frame": 0, "end_frame": 59, "start_time_s": 0.0, "end_time_s": 1.97, "voltage_V": 0.0, "voltage_confidence": 1.0, "source": "manual"},
            {"platform_id": "P002", "start_frame": 60, "end_frame": 119, "start_time_s": 2.0, "end_time_s": 3.97, "voltage_V": 200.0, "voltage_confidence": 1.0, "source": "manual"},
        ]
    )

    tracks, summary = track_multiple_candidates(video, "multi", roi, platforms, config)

    assert tracks["track_id"].nunique() >= 2
    assert summary["selected_for_multi_drop"].sum() >= 2
    first_points = tracks.sort_values("frame_idx").groupby("track_id").first()
    assert first_points["x_px"].max() - first_points["x_px"].min() > 40


def test_pipeline_writes_multi_drop_outputs(tmp_path: Path):
    video = tmp_path / "multi_pipeline.mp4"
    _make_synthetic_multi_drop_video(video)
    config = load_config("configs/default.yaml")
    config["roi"]["microscope_roi"] = [20, 20, 240, 200]
    config["manual_platforms"] = [
        {"platform_id": "P001", "start_frame": 0, "end_frame": 59, "start_time_s": 0.0, "end_time_s": 1.97, "voltage_V": 0.0, "voltage_confidence": 1.0, "source": "manual"},
        {"platform_id": "P002", "start_frame": 60, "end_frame": 119, "start_time_s": 2.0, "end_time_s": 3.97, "voltage_V": 200.0, "voltage_confidence": 1.0, "source": "manual"},
    ]
    config["segment"]["stable_min_duration_s"] = 0.5
    config["segment"]["transient_drop_s"] = 0.1
    config["segment"]["min_valid_points"] = 10
    config["segment"]["min_fit_r2"] = 0.5
    config["segment"]["min_motion_displacement_px"] = 1
    config["tracking"]["top_k_seeds"] = 10
    config["tracking"]["max_drops"] = 3
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    run_dir = run_pipeline(video, config_path, tmp_path / "run")

    drop_tracks = pd.read_csv(run_dir / "drop_tracks.csv")
    drop_segments = pd.read_csv(run_dir / "drop_track_segments.csv")
    candidate_summary = pd.read_csv(run_dir / "candidate_tracks_summary.csv")
    multi_results = json.loads((run_dir / "multi_drop_results.json").read_text(encoding="utf-8"))
    quality = json.loads((run_dir / "quality_scores.json").read_text(encoding="utf-8"))
    quality_rows = pd.read_csv(run_dir / "trajectory_quality_scores.csv")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    layers = json.loads((run_dir / "visualization_layers.json").read_text(encoding="utf-8"))
    validity = json.loads((run_dir / "validity_report.json").read_text(encoding="utf-8"))
    report = (run_dir / "analysis_report.md").read_text(encoding="utf-8")
    assert drop_tracks["track_id"].nunique() >= 2
    assert drop_segments["track_id"].nunique() >= 2
    assert multi_results["num_total_drops"] >= 2
    assert len(multi_results["drops"]) >= 2
    assert manifest["counts"]["drops"] >= 2
    assert manifest["counts"]["valid_drops"] == multi_results["valid_drop_count"]
    assert manifest["counts"]["quality_kept_drops"] == int(quality_rows["keep"].astype(bool).sum())
    assert quality["mode"] == "mock_rule_adapter"
    assert quality["trained"] is False
    assert {"track_id", "trajectory_score", "physics_quality_score", "quality_score", "keep", "reject_reasons"}.issubset(quality_rows.columns)
    assert {"drop_id", "q_valid", "physics_flags", "charge_abs_C"}.issubset(candidate_summary.columns)
    assert candidate_summary["q_valid"].astype(bool).sum() == multi_results["valid_drop_count"]
    drop_track_layer = next(layer for layer in layers["layers"] if layer["id"] == "drop_tracks")
    assert len(drop_track_layer["tracks"]) >= 2
    assert all({"quality_score", "keep", "q_valid", "reject_reasons"}.issubset(track) for track in drop_track_layer["tracks"])
    checks = {check["id"]: check for check in validity["checks"]}
    assert checks["multi_drop_q_results"]["details"]["valid_drop_count"] == multi_results["valid_drop_count"]
    assert checks["elementary_charge_ready"]["details"]["required_drop_count"] == config["elementary"]["min_drops"]
    assert "elementary_charge_ready" not in validity["blocking_failed_checks"]
    assert "多油滴结果" in report
    assert "multi_drop_results.json" in report


def test_pipeline_estimates_elementary_charge_from_three_valid_drops(tmp_path: Path):
    video = tmp_path / "three_valid.mp4"
    _make_synthetic_three_valid_drop_video(video)
    config = load_config("configs/default.yaml")
    config["roi"]["microscope_roi"] = [20, 15, 300, 230]
    config["manual_platforms"] = [
        {"platform_id": "P001", "start_frame": 0, "end_frame": 89, "start_time_s": 0.0, "end_time_s": 89 / 30.0, "voltage_V": 0.0, "voltage_confidence": 1.0, "source": "manual"},
        {"platform_id": "P002", "start_frame": 90, "end_frame": 179, "start_time_s": 90 / 30.0, "end_time_s": 179 / 30.0, "voltage_V": 200.0, "voltage_confidence": 1.0, "source": "manual"},
    ]
    config["segment"]["stable_min_duration_s"] = 0.8
    config["segment"]["transient_drop_s"] = 0.1
    config["segment"]["min_valid_points"] = 18
    config["segment"]["min_fit_r2"] = 0.5
    config["segment"]["min_motion_displacement_px"] = 1
    config["tracking"]["top_k_seeds"] = 12
    config["tracking"]["max_drops"] = 3
    config["tracking"]["min_grid_clear_fraction"] = 0.0
    config["tracking"]["min_roi_clear_fraction"] = 0.0
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    run_dir = run_pipeline(video, config_path, tmp_path / "run")

    elementary = json.loads((run_dir / "elementary_charge_result.json").read_text(encoding="utf-8"))
    multi = json.loads((run_dir / "multi_drop_results.json").read_text(encoding="utf-8"))
    quality_rows = pd.read_csv(run_dir / "trajectory_quality_scores.csv")
    validity = json.loads((run_dir / "validity_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert multi["valid_drop_count"] == 3
    assert elementary["valid"] is True
    assert elementary["num_used_drops"] == int(quality_rows["keep"].astype(bool).sum()) == 3
    assert validity["overall_valid_for_elementary_charge"] is True
    assert manifest["status"]["valid_for_elementary_charge"] is True


def test_primary_drop_selection_prefers_valid_q_over_top_tracking_score():
    candidate_summary = pd.DataFrame(
        [
            {"candidate_id": "candidate_001", "score_total": 0.95},
            {"candidate_id": "candidate_002", "score_total": 0.75},
        ]
    )
    drops = [
        {"drop_id": "drop_001", "track_id": "candidate_001", "valid": False, "quality_score": 0.2},
        {"drop_id": "drop_002", "track_id": "candidate_002", "valid": True, "quality_score": 0.8},
    ]

    selected_id, selected_drop = _select_primary_drop(drops, candidate_summary, "candidate_001")

    assert selected_id == "candidate_002"
    assert selected_drop["drop_id"] == "drop_002"


def test_cli_help_runs():
    result = subprocess.run(
        [".venv/Scripts/python", "-m", "millikan_ai.cli", "--help"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "inspect" in result.stdout


def test_parse_cli_platform_spec_uses_frame_time():
    platform = _parse_platform_spec("30:90:175", fps=30.0, index=2)
    assert platform["platform_id"] == "P002"
    assert platform["start_time_s"] == 1.0
    assert platform["end_time_s"] == 3.0
    assert platform["voltage_V"] == 175.0
    assert platform["source"] == "manual_cli"


def test_parse_cli_platform_spec_rejects_out_of_range_end_frame():
    try:
        _parse_platform_spec("0:120:175", fps=30.0, index=1, frame_count=120)
    except ValueError as exc:
        assert "exceeds video last frame" in str(exc)
    else:
        raise AssertionError("expected out-of-range platform to be rejected")


def test_interactive_platform_wizard_prompts_for_ranges_and_voltage(monkeypatch):
    answers = iter(["2", "", "59", "0", "60", "", "175"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    rows = _prompt_platform_rows(fps=30.0, frame_count=120)

    assert rows[0]["platform_id"] == "P001"
    assert rows[0]["start_frame"] == 0
    assert rows[0]["end_frame"] == 59
    assert rows[0]["voltage_V"] == 0.0
    assert rows[1]["platform_id"] == "P002"
    assert rows[1]["start_frame"] == 60
    assert rows[1]["end_frame"] == 119
    assert rows[1]["end_time_s"] == 119 / 30.0
    assert rows[1]["voltage_V"] == 175.0


def test_tracking_roi_is_clipped_to_measurement_grid_bottom():
    config = load_config("configs/default.yaml")
    grid = GridCalibration(
        roi=Roi(10, 20, 300, 400),
        grid_lines_x=[30, 120, 220],
        grid_lines_y=[40, 120, 220, 320],
        x_start_px=30,
        x_end_px=220,
        y_start_px=120,
        y_end_px=320,
        measurement_distance_m=0.0015,
        scale_y_m_per_px=0.0015 / 200,
        warnings=[],
    )

    roi = _tracking_roi_from_grid(grid, config)

    assert roi.to_list() == [30, 20, 190, 300]


def test_grid_clear_fraction_penalizes_grid_line_highlights():
    grid = GridCalibration(
        roi=Roi(0, 0, 300, 300),
        grid_lines_x=[100, 200],
        grid_lines_y=[80, 160],
        x_start_px=100,
        x_end_px=200,
        y_start_px=80,
        y_end_px=160,
        measurement_distance_m=0.0015,
        scale_y_m_per_px=0.0015 / 80,
        warnings=[],
    )
    grid_line_rows = [{"x_px": 100.5, "y_px": 120, "is_valid_detection": True} for _ in range(10)]
    droplet_rows = [{"x_px": 135, "y_px": 120, "is_valid_detection": True} for _ in range(10)]

    assert _grid_clear_fraction(grid_line_rows, grid, min_distance_px=8) == 0.0
    assert _grid_clear_fraction(droplet_rows, grid, min_distance_px=8) == 1.0


def test_roi_clear_fraction_penalizes_edge_highlights():
    roi = Roi(100, 50, 300, 200)
    edge_rows = [{"x_px": 105, "y_px": 120, "is_valid_detection": True} for _ in range(10)]
    inner_rows = [{"x_px": 180, "y_px": 120, "is_valid_detection": True} for _ in range(10)]

    assert _roi_clear_fraction(edge_rows, roi, min_margin_px=20) == 0.0
    assert _roi_clear_fraction(inner_rows, roi, min_margin_px=20) == 1.0
