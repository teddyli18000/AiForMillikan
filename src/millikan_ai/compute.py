from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

import cv2


@dataclass(frozen=True)
class ComputeBackend:
    requested: str
    name: str
    gpu_available: bool
    device_index: int | None
    fallback_reason: str
    accelerated_stages: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["accelerated_stages"] = list(self.accelerated_stages)
        return data


def _opencv_cuda_device_count() -> int:
    try:
        return int(cv2.cuda.getCudaEnabledDeviceCount())
    except (AttributeError, cv2.error):
        return 0


def select_compute_backend(
    requested: str = "auto",
    *,
    cuda_device_count: Callable[[], int] = _opencv_cuda_device_count,
) -> ComputeBackend:
    requested = str(requested or "auto").lower()
    if requested not in {"auto", "cpu", "opencv_cuda"}:
        raise ValueError(f"Unsupported compute backend: {requested}")
    if requested == "cpu":
        return ComputeBackend(requested, "cpu", False, None, "")
    if cuda_device_count() > 0:
        return ComputeBackend(requested, "opencv_cuda", True, 0, "", ())
    return ComputeBackend(requested, "cpu", False, None, "opencv_cuda_unavailable")
