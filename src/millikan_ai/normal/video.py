from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import cv2


def inspect_video(video_path: str | Path) -> dict[str, Any]:
    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    readable = cap.isOpened()
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) if readable else 0
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) if readable else 0
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) if readable else 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) if readable else 0
    cap.release()
    duration_s = frame_count / fps if fps > 0 else 0.0
    return {
        "path": str(path),
        "readable": bool(readable),
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
        "duration_s": duration_s,
        "sha256_16": file_sha256(path)[:16] if path.exists() else "",
    }


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_frame(video_path: str | Path, frame_index: int):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_index)))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"cannot read frame {frame_index}")
    return frame


def read_frames(video_path: str | Path, start_frame: int, end_frame: int) -> list:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    start = max(0, int(start_frame))
    end = max(start, int(end_frame))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames = []
    for _frame_idx in range(start, end + 1):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if not frames:
        raise RuntimeError("no frames read")
    return frames

