from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from millikan_ai.normal.session import (
    confirm_boundary as normal_confirm_boundary,
    export_session as normal_export_session,
    initialize_session as normal_initialize_session,
    inspect_video_only as normal_inspect_video,
    prepare_video as normal_prepare_video,
    prepare_crossing_review as normal_prepare_crossing_review,
    review_crossing as normal_review_crossing,
    run_inversion as normal_run_inversion,
    save_measurement as normal_save_measurement,
    select_target as normal_select_target,
    start_next_droplet as normal_start_next_droplet,
    update_record_selection as normal_update_record_selection,
)


Json = dict[str, Any]
_MISSING = object()


def _configure_utf8_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


_configure_utf8_stdio()


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


def _write_line(payload: Json) -> None:
    sys.stdout.write(json.dumps(_json_safe(payload), ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _normal_config_overrides(payload: Json) -> dict[str, Any] | None:
    value = _value(payload, "config_overrides", None)
    return value if isinstance(value, dict) else None


def _op_normal_initialize(payload: Json, _request_id: str) -> Json:
    return normal_initialize_session(
        session_root=_value(payload, "session_root", None),
        run_root=_value(payload, "run_root", None),
        config_overrides=_normal_config_overrides(payload),
    )


def _op_normal_inspect_video(payload: Json, _request_id: str) -> Json:
    return normal_inspect_video(str(_value(payload, "video_path")))


def _op_normal_prepare_video(payload: Json, _request_id: str) -> Json:
    return normal_prepare_video(
        video_path=str(_value(payload, "video_path")),
        session_root=_value(payload, "session_root", None),
        run_root=_value(payload, "run_root", None),
        config_overrides=_normal_config_overrides(payload),
        progress_callback=_normal_progress_emitter(_request_id, "prepare_video"),
    )


def _op_normal_confirm_boundary(payload: Json, _request_id: str) -> Json:
    return normal_confirm_boundary(payload, config_overrides=_normal_config_overrides(payload))


def _op_normal_select_target(payload: Json, _request_id: str) -> Json:
    return normal_select_target(payload, config_overrides=_normal_config_overrides(payload))


def _op_normal_save_measurement(payload: Json, _request_id: str) -> Json:
    return normal_save_measurement(
        payload,
        config_overrides=_normal_config_overrides(payload),
        progress_callback=_normal_progress_emitter(_request_id, "save_measurement"),
    )


def _op_normal_prepare_crossing_review(payload: Json, _request_id: str) -> Json:
    return normal_prepare_crossing_review(payload)


def _op_normal_review_crossing(payload: Json, _request_id: str) -> Json:
    return normal_review_crossing(payload)


def _op_normal_select_record(payload: Json, _request_id: str) -> Json:
    return normal_update_record_selection(
        session_root=_value(payload, "session_root", None),
        record_id=str(_value(payload, "record_id")),
        kept=bool(_value(payload, "kept", _value(payload, "selected", True))),
    )["session"]


def _op_normal_start_next_droplet(payload: Json, _request_id: str) -> Json:
    return normal_start_next_droplet(payload)


def _op_normal_run_inversion(payload: Json, _request_id: str) -> Json:
    return normal_run_inversion(
        session_root=_value(payload, "session_root", None),
        config_overrides=_normal_config_overrides(payload),
        progress_callback=_normal_progress_emitter(_request_id, "run_inversion"),
    )


def _op_normal_export(payload: Json, _request_id: str) -> Json:
    return normal_export_session(
        session_root=_value(payload, "session_root", None),
        export_root=str(_value(payload, "export_root")),
    )


def _normal_progress_emitter(request_id: str, operation: str) -> Callable[[Json], None]:
    def emit(payload: Json) -> None:
        current = payload.get("current")
        total = payload.get("total")
        indeterminate = bool(payload.get("indeterminate", current is None or total in {None, 0}))
        fraction = None
        if not indeterminate and current is not None and total:
            fraction = max(0.0, min(1.0, float(current) / float(total)))
        _write_line(
            {
                "id": request_id,
                "type": "progress",
                "payload": {
                    "request_id": request_id,
                    "operation": operation,
                    "stage": payload.get("stage") or payload.get("phase") or "unknown",
                    "label": str(payload.get("label") or payload.get("stage") or "处理中"),
                    "current": current,
                    "total": total,
                    "unit": payload.get("unit"),
                    "fraction": fraction,
                    "indeterminate": indeterminate,
                },
            }
        )

    return emit


OPS: dict[str, Callable[[Json, str], Json]] = {
    "normal.initialize": _op_normal_initialize,
    "normal.inspectVideo": _op_normal_inspect_video,
    "normal.prepareVideo": _op_normal_prepare_video,
    "normal.confirmBoundary": _op_normal_confirm_boundary,
    "normal.selectTarget": _op_normal_select_target,
    "normal.saveMeasurement": _op_normal_save_measurement,
    "normal.prepareCrossingReview": _op_normal_prepare_crossing_review,
    "normal.reviewCrossing": _op_normal_review_crossing,
    "normal.updateRecordSelection": _op_normal_select_record,
    "normal.startNextDroplet": _op_normal_start_next_droplet,
    "normal.runInversion": _op_normal_run_inversion,
    "normal.exportSession": _op_normal_export,
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
    parser = argparse.ArgumentParser(prog="millikan-normal-worker")
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
