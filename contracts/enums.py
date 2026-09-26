from __future__ import annotations

from enum import StrEnum


class ZoneType(StrEnum):
    SUBSYSTEM = "SUBSYSTEM"
    SIN = "SIN"
    DISTRIBUTOR = "DISTRIBUTOR"


class IncidentType(StrEnum):
    HEAT = "HEAT"
    COLD = "COLD"
    RAIN = "RAIN"
    WIND = "WIND"
    SOLAR_DEFICIT = "SOLAR_DEFICIT"


class GeometryQuality(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    REAL = "REAL"
    SCHEMATIC = "SCHEMATIC"
    UNKNOWN = "UNKNOWN"
