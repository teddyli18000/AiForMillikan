"""End-to-end probe for the packaged Normal worker.

Generates a deterministic synthetic video, then drives the real worker through
initialize -> prepare -> boundary -> target -> measurement -> crossing review ->
accept -> inversion -> export. It checks response contracts and exported files,
not physical accuracy.

Usage (from `normal/`):

    .venv\\Scripts\\python scripts\\probe_packaged_worker.py --worker apps\\desktop\\dist-worker\\millikan-normal-worker.exe

Omit `--worker` to run the source module instead.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

OVERRIDES: dict[str, Any] = {
    "grid": {"measurement_distance_m": 0.0015, "mask_dilate_px": 1},
    "tracking": {"minmass": 20, "memory_frames": 4, "grid_occlusion_radius_px": 1},
    "fit": {"min_points": 8, "min_duration_s": 0.4, "min_displacement_px": 2.0, "min_r2": 0.2},
}


def make_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for index in range(120):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for y in [30, 70, 110, 150, 190]:
            cv2.line(frame, (24, y), (296, y), (190, 190, 190), 1)
        # 0.5 px/frame from y=52 reaches the y=110 grid line inside the 0-3.8 s window.
        cv2.circle(frame, (92, int(52 + index * 0.5)), 5, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def worker_call(command: list[str], env: dict[str, str], op: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    message = json.dumps({"id": "probe", "op": op, "payload": payload}, ensure_ascii=False)
    completed = subprocess.run(
        command,
        input=message + "\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f"{op}: worker exited with {completed.returncode}\n{completed.stderr[-4000:]}")
    messages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    terminal = [message for message in messages if message.get("type") in {"result", "error"}]
    if not terminal:
        raise SystemExit(f"{op}: no result or error message\n{completed.stdout[-4000:]}")
    last = terminal[-1]
    if last["type"] == "error":
        raise SystemExit(f"{op} failed: {last['error']}")
    return last["payload"]


def target_payload(session_root: str) -> dict[str, Any]:
    return {
        "session_root": session_root,
        "balance_voltage_V": 239.0,
        "balance_confirmed": True,
        "target": {
            "target_frame": 0,
            "target_time_s": 0.0,
            "source_center": {"x": 92.0, "y": 52.0},
            "source_video_box": {"x": 78.0, "y": 38.0, "width": 28.0, "height": 28.0},
        },
        "parameter_overrides": OVERRIDES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, help="Packaged worker executable; omit for the source module.")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    command = [str(args.worker.resolve())] if args.worker else [sys.executable, "-m", "millikan_ai.desktop_worker"]

    with tempfile.TemporaryDirectory(prefix="millikan_normal_probe_") as tmp:
        tmp_path = Path(tmp)
        video = tmp_path / "synthetic.mp4"
        make_video(video)
        session_root = tmp_path / "session"
        run_root = tmp_path / "records"
        export_root = tmp_path / "export"

        env = {key: value for key, value in os.environ.items()}
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")]).strip(os.pathsep)

        initialized = worker_call(
            command,
            env,
            "normal.initialize",
            {"session_root": str(session_root), "run_root": str(run_root), "config_overrides": OVERRIDES},
            args.timeout,
        )
        session_root_text = str(initialized["session_root"])

        accepted_records: list[dict[str, Any]] = []
        reviewed_crossings = 0
        for index in range(3):
            prepared = worker_call(
                command,
                env,
                "normal.prepareVideo",
                {"video_path": str(video), "session_root": session_root_text, "config_overrides": OVERRIDES},
                args.timeout,
            )
            if not prepared["metadata"]["readable"] or not prepared["grid"]["valid"]:
                raise SystemExit("prepareVideo returned unusable metadata or grid")

            worker_call(
                command,
                env,
                "normal.confirmBoundary",
                {
                    "session_root": session_root_text,
                    "boundary": {"zero_v_start_s": 0.0, "zero_v_end_s": 3.8, "source": "ci_probe"},
                },
                args.timeout,
            )
            worker_call(command, env, "normal.selectTarget", target_payload(session_root_text), args.timeout)
            measured = worker_call(
                command,
                env,
                "normal.saveMeasurement",
                {"session_root": session_root_text, "config_overrides": OVERRIDES},
                args.timeout,
            )
            record = measured["record"]
            if record["q_C"] <= 0 or record["sigma_q_C"] <= 0:
                raise SystemExit(f"record {record['record_id']} has no usable q")

            crossings = record.get("crossings", [])
            if not crossings:
                raise SystemExit(f"record {record['record_id']} produced no crossing event")
            for crossing in crossings:
                review = worker_call(
                    command,
                    env,
                    "normal.prepareCrossingReview",
                    {
                        "session_root": session_root_text,
                        "record_id": record["record_id"],
                        "event_id": crossing["event_id"],
                    },
                    args.timeout,
                )
                if not review["event"].get("review_frames"):
                    raise SystemExit("crossing review returned no frames")
                worker_call(
                    command,
                    env,
                    "normal.reviewCrossing",
                    {
                        "session_root": session_root_text,
                        "record_id": record["record_id"],
                        "event_id": crossing["event_id"],
                        "result": "same_drop",
                    },
                    args.timeout,
                )
                reviewed_crossings += 1

            accepted = worker_call(
                command,
                env,
                "normal.updateRecordSelection",
                {"session_root": session_root_text, "record_id": record["record_id"], "kept": True},
                args.timeout,
            )
            accepted_record = [row for row in accepted["records"] if row["record_id"] == record["record_id"]][0]
            if accepted_record["status"] != "accepted":
                raise SystemExit(f"record {record['record_id']} was not accepted")
            accepted_records.append(accepted_record)

            if index < 2:
                worker_call(
                    command,
                    env,
                    "normal.startNextDroplet",
                    {"session_root": session_root_text, "record_id": record["record_id"], "mode": "same_video"},
                    args.timeout,
                )

        if reviewed_crossings < 3:
            raise SystemExit(f"only {reviewed_crossings} crossing events were reviewed; expected at least one per record")

        inversion = worker_call(
            command,
            env,
            "normal.runInversion",
            {"session_root": session_root_text, "config_overrides": OVERRIDES},
            args.timeout,
        )
        result = inversion["inversion"]
        if result["valid_q_count"] != 3:
            raise SystemExit(f"inversion used {result['valid_q_count']} q records instead of 3")
        if result["e_hat_C"] <= 0 or result["sigma_e_C"] <= 0:
            raise SystemExit("inversion returned a non-positive estimate")

        exported = worker_call(
            command,
            env,
            "normal.exportSession",
            {"session_root": session_root_text, "export_root": str(export_root)},
            args.timeout,
        )
        destination = Path(exported["destination"])
        if not (destination / "export_manifest.json").exists():
            raise SystemExit("export_manifest.json missing")
        if not (destination / "normal_session_report.md").exists():
            raise SystemExit("normal_session_report.md missing")
        if not (destination / "normal_inversion.json").exists():
            raise SystemExit("normal_inversion.json missing")

        print(
            json.dumps(
                {
                    "ok": True,
                    "worker": str(args.worker) if args.worker else "source-module",
                    "accepted_records": [row["record_id"] for row in accepted_records],
                    "e_hat_C": result["e_hat_C"],
                    "sigma_e_C": result["sigma_e_C"],
                    "destination": str(destination),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
