import math

import pytest

from millikan_ai.physics.viscosity import resolve_air_viscosity, sutherland_air_viscosity


def test_sutherland_air_viscosity_matches_reference_temperatures():
    assert sutherland_air_viscosity(20.0) == pytest.approx(1.81e-5, rel=1e-12)
    assert sutherland_air_viscosity(0.0) == pytest.approx(1.71286e-5, rel=3e-6)
    assert sutherland_air_viscosity(40.0) == pytest.approx(1.90399e-5, rel=3e-6)


def test_sutherland_air_viscosity_is_monotonic_in_lab_range():
    values = [sutherland_air_viscosity(temp_c) for temp_c in (0.0, 10.0, 20.0, 30.0, 40.0)]
    assert values == sorted(values)


def test_sutherland_air_viscosity_converts_celsius_to_kelvin():
    eta = sutherland_air_viscosity(
        -273.14,
        reference_temperature_K=293.15,
        reference_viscosity_Pa_s=1.81e-5,
        sutherland_constant_K=110.4,
    )
    assert math.isfinite(eta)
    assert eta > 0
    with pytest.raises(ValueError, match="absolute_temperature_must_be_positive"):
        sutherland_air_viscosity(-273.15)


def test_resolve_air_viscosity_prefers_direct_value_and_records_source():
    result = resolve_air_viscosity(
        {
            "viscosity": {
                "source": "direct",
                "air_temperature_C": 40.0,
                "direct_air_viscosity_Pa_s": 2.0e-5,
            }
        }
    )

    assert result["air_viscosity_Pa_s"] == pytest.approx(2.0e-5)
    assert result["viscosity_source"] == "direct"
    assert result["air_temperature_C"] == 40.0
    assert result["sutherland_parameters"]["reference_temperature_K"] == 293.15


def test_resolve_air_viscosity_uses_temperature_source():
    result = resolve_air_viscosity({"viscosity": {"source": "temperature", "air_temperature_C": 0.0}})

    assert result["air_viscosity_Pa_s"] == pytest.approx(1.71286e-5, rel=3e-6)
    assert result["viscosity_source"] == "temperature_sutherland"
