from __future__ import annotations

import math
from typing import Any


DEFAULT_REFERENCE_TEMPERATURE_K = 293.15
DEFAULT_REFERENCE_VISCOSITY_PA_S = 1.81e-5
DEFAULT_SUTHERLAND_CONSTANT_K = 110.4


def sutherland_air_viscosity(
    air_temperature_C: float,
    *,
    reference_temperature_K: float = DEFAULT_REFERENCE_TEMPERATURE_K,
    reference_viscosity_Pa_s: float = DEFAULT_REFERENCE_VISCOSITY_PA_S,
    sutherland_constant_K: float = DEFAULT_SUTHERLAND_CONSTANT_K,
) -> float:
    temperature_K = float(air_temperature_C) + 273.15
    reference_temperature_K = float(reference_temperature_K)
    reference_viscosity_Pa_s = float(reference_viscosity_Pa_s)
    sutherland_constant_K = float(sutherland_constant_K)
    if temperature_K <= 0 or reference_temperature_K <= 0:
        raise ValueError("absolute_temperature_must_be_positive")
    if reference_viscosity_Pa_s <= 0:
        raise ValueError("reference_viscosity_must_be_positive")
    eta = (
        reference_viscosity_Pa_s
        * (temperature_K / reference_temperature_K) ** 1.5
        * (reference_temperature_K + sutherland_constant_K)
        / (temperature_K + sutherland_constant_K)
    )
    if not math.isfinite(eta) or eta <= 0:
        raise ValueError("air_viscosity_must_be_positive")
    return float(eta)


def resolve_air_viscosity(config: dict[str, Any]) -> dict[str, Any]:
    viscosity_config = dict(config.get("viscosity") or {})
    physics_config = dict(config.get("physics") or {})
    air_temperature_C = float(viscosity_config.get("air_temperature_C", 20.0))
    reference_temperature_K = float(
        viscosity_config.get("reference_temperature_K", DEFAULT_REFERENCE_TEMPERATURE_K)
    )
    reference_viscosity_Pa_s = float(
        viscosity_config.get("reference_viscosity_Pa_s", DEFAULT_REFERENCE_VISCOSITY_PA_S)
    )
    sutherland_constant_K = float(
        viscosity_config.get("sutherland_constant_K", DEFAULT_SUTHERLAND_CONSTANT_K)
    )
    direct_value = viscosity_config.get("direct_air_viscosity_Pa_s")
    source = str(viscosity_config.get("source", "temperature"))
    if direct_value is None and "air_viscosity_Pa_s" in physics_config:
        direct_value = physics_config["air_viscosity_Pa_s"]
        source = "legacy_physics_direct"
    if direct_value is not None and (source == "direct" or source == "legacy_physics_direct"):
        eta = float(direct_value)
        if not math.isfinite(eta) or eta <= 0:
            raise ValueError("air_viscosity_must_be_positive")
        viscosity_source = "direct" if source == "direct" else "legacy_physics_direct"
    else:
        eta = sutherland_air_viscosity(
            air_temperature_C,
            reference_temperature_K=reference_temperature_K,
            reference_viscosity_Pa_s=reference_viscosity_Pa_s,
            sutherland_constant_K=sutherland_constant_K,
        )
        viscosity_source = "temperature_sutherland"
    return {
        "viscosity_source": viscosity_source,
        "air_temperature_C": air_temperature_C,
        "air_viscosity_Pa_s": eta,
        "sutherland_parameters": {
            "reference_temperature_K": reference_temperature_K,
            "reference_viscosity_Pa_s": reference_viscosity_Pa_s,
            "sutherland_constant_K": sutherland_constant_K,
        },
    }
