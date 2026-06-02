from __future__ import annotations

import argparse
import json
from pathlib import Path

from millikan_ai.config import load_config
from millikan_ai.pipeline import run_pipeline, validate_run, write_summary
from millikan_ai.video.reader import inspect_video, save_diagnostic_frame


def _cmd_inspect(args: argparse.Namespace) -> int:
    meta = inspect_video(args.video)
    print(json.dumps(meta.to_dict(), indent=2, ensure_ascii=False))
    if args.save_frame:
        target = Path(args.save_frame)
        save_diagnostic_frame(args.video, target)
        print(f"diagnostic_frame={target}")
    return 0 if meta.readable else 1


def _cmd_run(args: argparse.Namespace) -> int:
    run_dir = run_pipeline(args.video, args.config, args.run_dir)
    print(f"run_dir={run_dir}")
    errors = validate_run(run_dir, args.config)
    if errors:
        print("validation_errors=" + json.dumps(errors, ensure_ascii=False))
        return 2
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    run_dir = run_pipeline(args.video, args.config, args.run_dir)
    report = Path(run_dir) / "analysis_report.md"
    print(f"run_dir={run_dir}")
    print(f"analysis_report={report}")
    errors = validate_run(run_dir, args.config)
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
    run.set_defaults(func=_cmd_run)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--video", required=True)
    analyze.add_argument("--config", default="configs/default.yaml")
    analyze.add_argument("--run-dir")
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
