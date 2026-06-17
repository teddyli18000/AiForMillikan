from __future__ import annotations

from dataclasses import dataclass

import math
import numpy as np


@dataclass(frozen=True)
class VelocityUncertainty:
    standard_uncertainty_m_s: float
    ci95_m_s: list[float]
    method: str
    samples_used: int


def velocity_uncertainty_from_residuals(residuals: list[float], *, slope_m_s: float, sample_count: int) -> VelocityUncertainty:
    if sample_count <= 2 or not residuals:
        sigma = 0.0
    else:
        arr = np.asarray(residuals, dtype=float)
        sigma = float(np.std(arr, ddof=1) / math.sqrt(sample_count))
    return VelocityUncertainty(
        standard_uncertainty_m_s=sigma,
        ci95_m_s=[float(slope_m_s - 1.96 * sigma), float(slope_m_s + 1.96 * sigma)],
        method="residual_slope_standard_error",
        samples_used=int(sample_count),
    )

