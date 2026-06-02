from __future__ import annotations

import argparse
import json
from pathlib import Path

from millikan_ai.config import load_config, save_config
from millikan_ai.pipeline import run_pipeline, validate_run, write_summary
from millikan_ai.video.reader import inspect_video, save_diagnostic_frame


def _parse_platform_spec(spec: str, fps: float, index: int) -> dict[str, object]:
    parts = [part.strip() for part in spec.split(":")]
    if len(parts) != 3:
        raise ValueError(f"platform spec must be START_FRAME:END_FRAME:VOLTAGE, got: {spec}")
    start_frame = int(parts[0])
    end_frame = int(parts[1])
    voltage = float(parts[2])
    if start_frame < 0 or end_frame < start_frame:
        raise ValueError(f"invalid platform frame range: {spec}")
    return {
        "platform_id": f"P{index:03d}",
        "start_frame": start_frame,
        "end_frame": end_frame,
        "start_time_s": start_frame / fps if fps else 0.0,
        "end_time_s": end_frame / fps if fps else 0.0,
        "voltage_V": voltage,
        "voltage_confidence": 1.0,
        "source": "manual_cli",
    }


def _prompt_platform_specs() -> list[str]:
    count_text = input("platform count: ").strip()
    count = int(count_text)
    specs = []
    for index in range(1, count + 1):
        specs.append(input(f"platform {index} START_FRAME:END_FRAME:VOLTAGE: ").strip())
    return specs


def _prepare_config(args: argparse.Namespace) -> str:
    specs = list(args.platform or [])
    if getattr(args, "interactive_platforms", False):
        specs.extend(_prompt_platform_specs())
    if not specs:
        return args.config
    config = load_config(args.config)
    meta = inspect_video(args.video)
    config["manual_platforms"] = [_parse_platform_spec(spec, meta.fps, idx) for idx, spec in enumerate(specs, start=1)]
    target = Path(config["project"]["run_root"]) / "manual_configs" / f"{Path(args.video).stem}_manual_platforms.yaml"
    save_config(config, target)
    return str(target)


def _cmd_inspect(args: argparse.Namespace) -> int:
    meta = inspect_video(args.video)
    print(json.dumps(meta.to_dict(), indent=2, ensure_ascii=False))
    if args.save_frame:
        target = save_diagnostic_frame(args.video, Path(args.save_frame))
        print(f"diagnostic_frame={target}")
    return 0 if meta.readable else 1


def _cmd_run(args: argparse.Namespace) -> int:
    config_path = _prepare_config(args)
    run_dir = run_pipeline(args.video, config_path, args.run_dir)
    print(f"run_dir={run_dir}")
    print(f"config={config_path}")
    errors = validate_run(run_dir, config_path)
    if errors:
        print("validation_errors=" + json.dumps(errors, ensure_ascii=False))
        return 2
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    config_path = _prepare_config(args)
    run_dir = run_pipeline(args.video, config_path, args.run_dir)
    report = Path(run_dir) / "analysis_report.md"
    print(f"run_dir={run_dir}")
    print(f"config={config_path}")
    print(f"analysis_report={report}")
    errors = validate_run(run_dir, config_path)
    if errors:
        print("validation_errors=" + json.dumps(errors, ensure_ascii=False))
        return 2
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    errors = validate_run(args.run_dir, args.config)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({"valid": True, "errors": []}, indent=2, ensure_ascii=False))
    return 0


def _cmd_summarize(args: argparse.Namespace) -> int:
    summary = write_summary(args.run_dir, load_config(args.config) if args.config else None)
    print(summary.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="millikan-ai")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("video")
    inspect.add_argument("--save-frame")
    inspect.set_defaults(func=_cmd_inspect)
    run = sub.add_parser("run")
    run.add_argument("--video", required=True)
    run.add_argument("--config", default="configs/default.yaml")
    run.add_argument("--run-dir")
    run.add_argument("--non-interactive", action="store_true")
    run.add_argument("--platform", action="append", help="Manual platform as START_FRAME:END_FRAME:VOLTAGE; repeat for multiple platforms.")
    run.add_argument("--interactive-platforms", action="store_true", help="Prompt for manual platform ranges before running.")
    run.set_defaults(func=_cmd_run)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--video", required=True)
    analyze.add_argument("--config", default="configs/default.yaml")
    analyze.add_argument("--run-dir")
    analyze.add_argument("--platform", action="append", help="Manual platform as START_FRAME:END_FRAME:VOLTAGE; repeat for multiple platforms.")
    analyze.add_argument("--interactive-platforms", action="store_true", help="Prompt for manual platform ranges before running.")
    analyze.set_defaults(func=_cmd_analyze)
    validate = sub.add_parser("validate")
    validate.add_argument("--run-dir", required=True)
    validate.add_argument("--config", default="configs/default.yaml")
    validate.set_defaults(func=_cmd_validate)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--run-dir", required=True)
    summarize.add_argument("--config", default=None)
    summarize.set_defaults(func=_cmd_summarize)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
