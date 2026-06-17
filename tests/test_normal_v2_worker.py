from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def _send_worker(message: dict) -> list[dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd() / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "millikan_ai.desktop_worker"],
        input=json.dumps(message, ensure_ascii=False) + "\n",
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def _make_normal_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (240, 180))
    for frame_idx in range(70):
        frame = np.zeros((180, 240, 3), dtype=np.uint8)
        for y in [20, 50, 80, 110, 140]:
            cv2.line(frame, (20, y), (220, y), (80, 80, 80), 1)
        x = 70
        y = int(55 + frame_idx * 0.8)
        if frame_idx not in {25, 26, 27}:
            cv2.circle(frame, (x, y), 4, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def test_worker_runs_normal_v2_single_drop_and_writes_artifacts(tmp_path: Path):
    video = tmp_path / "normal_v2.mp4"
    _make_normal_video(video)
    run_dir = tmp_path / "normal_run"

    messages = _send_worker(
        {
            "id": "normal-run",
            "op": "normalV2.runSingleDrop",
            "payload": {
                "video_path": str(video),
                "run_dir": str(run_dir),
                "balance_voltage_V": 240.0,
                "target": {"x": 70.0, "y": 55.0, "frame": 0, "box": [64, 49, 12, 12]},
                "confirmed_window": {"start_frame": 0, "end_frame": 65},
                "grid_lines_y": [20, 50, 80, 110, 140],
            },
        }
    )

    result = messages[-1]
    assert result["type"] == "result"
    payload = result["payload"]
    assert payload["manifest"]["mode"] == "normal_v2"
    assert payload["q_record"]["record_id"].startswith("q_")
    assert payload["q_record"]["valid"] is True
    assert Path(payload["files"]["normal_track_csv"]).exists()
    statuses = {row["status"] for row in payload["track_points"]}
    assert {"tracking", "missing", "reacquired"} <= statuses


def test_worker_normal_v2_session_roundtrip_and_report(tmp_path: Path):
    session_path = tmp_path / "session.json"
    run_dir = tmp_path / "run_a"
    run_dir.mkdir()
    for name in [
        "normal_track.csv",
        "normal_track.json",
        "normal_result.json",
        "normal_visualization_layers.json",
        "normal_report.md",
        "normal_manifest.json",
    ]:
        (run_dir / name).write_text(name, encoding="utf-8")
    records = [
        {"record_id": "a", "video_path": "v.mp4", "target_frame": 1, "window": {}, "q_C": 3.204e-19, "sigma_q_C": 0.04e-19, "valid": True, "selected": True, "flags": [], "run_dir": str(run_dir)},
        {"record_id": "b", "video_path": "v.mp4", "target_frame": 2, "window": {}, "q_C": 4.806e-19, "sigma_q_C": 0.04e-19, "valid": True, "selected": True, "flags": [], "run_dir": None},
        {"record_id": "c", "video_path": "v.mp4", "target_frame": 3, "window": {}, "q_C": 8.010e-19, "sigma_q_C": 0.04e-19, "valid": True, "selected": True, "flags": [], "run_dir": None},
    ]

    saved = _send_worker({"id": "save", "op": "normalV2.sessionSave", "payload": {"session_path": str(session_path), "records": records}})[-1]
    assert saved["payload"]["counts"]["selected_valid"] == 3

    loaded = _send_worker({"id": "load", "op": "normalV2.sessionLoad", "payload": {"session_path": str(session_path)}})[-1]
    assert len(loaded["payload"]["session"]["records"]) == 3

    estimate = _send_worker({"id": "estimate", "op": "normalV2.estimateElementary", "payload": {"records": records}})[-1]
    assert estimate["payload"]["normal_algorithm"]["valid"] is True
    assert "experimental_algorithm" in estimate["payload"]

    report_path = tmp_path / "report.md"
    report = _send_worker(
        {
            "id": "report",
            "op": "normalV2.sessionReport",
            "payload": {"session": {"records": records}, "inversion": estimate["payload"], "report_path": str(report_path)},
        }
    )[-1]
    assert "Blind inversion" in report_path.read_text(encoding="utf-8")
    assert report["payload"]["report_path"] == str(report_path)

    export_dir = tmp_path / "export"
    exported = _send_worker(
        {
            "id": "export",
            "op": "normalV2.exportBundle",
            "payload": {
                "destination_dir": str(export_dir),
                "session": {"records": records},
                "inversion": estimate["payload"],
            },
        }
    )[-1]
    assert exported["type"] == "result"
    relative_files = {
        Path(path).relative_to(export_dir).as_posix()
        for path in exported["payload"]["files"]
    }
    assert {
        "normal_v2_session.json",
        "normal_v2_q_records.json",
        "normal_v2_report.md",
        "normal_v2_manifest.json",
        "file_list.txt",
        "measurements/a/normal_track.csv",
        "measurements/a/normal_track.json",
        "measurements/a/normal_result.json",
        "measurements/a/normal_visualization_layers.json",
        "measurements/a/normal_report.md",
        "measurements/a/normal_manifest.json",
    } <= relative_files
    file_list = (export_dir / "file_list.txt").read_text(encoding="utf-8")
    assert "measurements/a/normal_track.csv" in file_list
