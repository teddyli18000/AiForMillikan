from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import cv2


def inspect_video(video_path: str | Path) -> dict[str, Any]:
    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    readable = cap.isOpened()
    width = height = frame_count = 0
    fps = duration_s = 0.0
    if readable:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_s = float(frame_count / fps) if fps > 0 else 0.0
    cap.release()
    return {
        "path": str(path),
        "readable": readable,
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
        "duration_s": duration_s,
    }


def read_frame(video_path: str | Path, frame_index: int):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_index)))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"cannot read frame {frame_index}: {video_path}")
    return frame


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_url(path: str | Path) -> str:
    return Path(path).resolve().as_uri()
