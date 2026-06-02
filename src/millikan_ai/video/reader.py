from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_s: float
    readable: bool
    file_size_bytes: int
    warnings: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_video(video_path: str | Path) -> VideoMetadata:
    path = Path(video_path)
    warnings: list[str] = []
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {path}")
    cap = cv2.VideoCapture(str(path))
    readable = bool(cap.isOpened())
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    if not readable:
        warnings.append("opencv_cannot_open_video")
    if fps <= 0:
        warnings.append("missing_or_invalid_fps")
    duration_s = frame_count / fps if fps > 0 else 0.0
    return VideoMetadata(
        path=str(path),
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration_s=duration_s,
        readable=readable,
        file_size_bytes=path.stat().st_size,
        warnings=warnings,
    )


def read_frame(video_path: str | Path, frame_idx: int):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Cannot read frame {frame_idx} from {video_path}")
    return frame


def save_diagnostic_frame(video_path: str | Path, output_path: str | Path, frame_idx: int = 0) -> Path:
    frame = read_frame(video_path, frame_idx)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), frame)
    return target

