from __future__ import annotations

from dataclasses import dataclass

import math


@dataclass(frozen=True)
class PhysicalConfig:
    plate_distance_m: float
    oil_density_kg_m3: float
    gravity_m_s2: float
    air_viscosity_Pa_s: float
    pressure_Pa: float
    cunningham_b_Pa_m: float


@dataclass(frozen=True)
class ChargeResult:
    valid: bool
    radius_m: float | None
    charge_C: float | None
    effective_viscosity_Pa_s: float | None
    flags: list[str]


def compute_balance_fall_charge(*, v_g_m_s: float, balance_voltage_V: float, config: PhysicalConfig) -> ChargeResult:
    if v_g_m_s <= 0 or not math.isfinite(v_g_m_s):
        return ChargeResult(False, None, None, None, ["invalid_fall_velocity"])
    if balance_voltage_V == 0 or not math.isfinite(balance_voltage_V):
        return ChargeResult(False, None, None, None, ["invalid_balance_voltage"])
    b_over_p = float(config.cunningham_b_Pa_m) / float(config.pressure_Pa)
    k = 9.0 * float(config.air_viscosity_Pa_s) * float(v_g_m_s) / (
        2.0 * float(config.oil_density_kg_m3) * float(config.gravity_m_s2)
    )
    radius = (-b_over_p + math.sqrt(b_over_p * b_over_p + 4.0 * k)) / 2.0
    if radius <= 0 or not math.isfinite(radius):
        return ChargeResult(False, None, None, None, ["invalid_radius"])
    effective_eta = float(config.air_viscosity_Pa_s) / (1.0 + b_over_p / radius)
    mass = (4.0 / 3.0) * math.pi * radius**3 * float(config.oil_density_kg_m3)
    charge = mass * float(config.gravity_m_s2) * float(config.plate_distance_m) / abs(float(balance_voltage_V))
    if charge <= 0 or not math.isfinite(charge):
        return ChargeResult(False, radius, None, effective_eta, ["invalid_charge"])
    return ChargeResult(True, radius, charge, effective_eta, [])

