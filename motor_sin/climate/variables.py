from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class ClimateVariableSpec:
    canonical_name: str
    aliases: tuple[str, ...]
    canonical_unit: str


VARIABLE_SPECS: tuple[ClimateVariableSpec, ...] = (
    ClimateVariableSpec("temperature_2m", ("temperature_2m",), "degC"),
    ClimateVariableSpec("dewpoint_2m", ("dewpoint_2m", "dew_point_2m"), "degC"),
    ClimateVariableSpec("precipitation", ("precipitation",), "mm"),
    ClimateVariableSpec("wind_speed_10m", ("wind_speed_10m",), "m/s"),
    ClimateVariableSpec("solar_radiation", ("solar_radiation", "shortwave_radiation"), "W/m2"),
)

CANONICAL_VARIABLES = tuple(spec.canonical_name for spec in VARIABLE_SPECS)
CANONICAL_UNITS = {spec.canonical_name: spec.canonical_unit for spec in VARIABLE_SPECS}


def normalize_unit_text(unit: Any) -> str:
    if unit is None:
        return ""
    return (
        str(unit)
        .strip()
        .lower()
        .replace("²", "2")
        .replace("°", "deg")
        .replace(" ", "")
    )


def resolve_source_field(hourly: dict[str, Any], canonical_name: str) -> str | None:
    spec = next((x for x in VARIABLE_SPECS if x.canonical_name == canonical_name), None)
    if spec is None:
        raise KeyError(canonical_name)
    for alias in spec.aliases:
        if alias in hourly:
            return alias
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    if math.isnan(result):
        return None
    return result


def convert_value(canonical_name: str, value: Any, source_unit: Any) -> float | None:
    """Convert supported source units to Predicta canonical units.

    Unknown non-empty units fail fast. Empty units are accepted only for
    hand-built development fixtures and are treated as already canonical.
    """
    value_f = _float_or_none(value)
    if value_f is None:
        return None

    unit = normalize_unit_text(source_unit)
    if canonical_name in {"temperature_2m", "dewpoint_2m"}:
        if unit in {"", "degc", "c", "celsius"}:
            return value_f
        if unit in {"degf", "f", "fahrenheit"}:
            return (value_f - 32.0) * (5.0 / 9.0)
        raise ValueError(f"unsupported temperature unit: {source_unit!r}")

    if canonical_name == "precipitation":
        if unit in {"", "mm", "millimeter", "millimetre"}:
            return value_f
        if unit in {"inch", "inches", "in"}:
            return value_f * 25.4
        raise ValueError(f"unsupported precipitation unit: {source_unit!r}")

    if canonical_name == "wind_speed_10m":
        if unit in {"", "m/s", "ms-1", "mps", "ms"}:
            return value_f
        if unit in {"km/h", "kmh", "kph"}:
            return value_f / 3.6
        if unit == "mph":
            return value_f * 0.44704
        if unit in {"kn", "knot", "knots"}:
            return value_f * 0.514444
        raise ValueError(f"unsupported wind unit: {source_unit!r}")

    if canonical_name == "solar_radiation":
        if unit in {"", "w/m2", "wm-2", "w/m^2"}:
            return value_f
        raise ValueError(f"unsupported radiation unit: {source_unit!r}")

    raise KeyError(canonical_name)
