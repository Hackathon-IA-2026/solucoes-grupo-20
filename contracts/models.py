from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.enums import GeometryQuality, IncidentType, ZoneType


# -----------------------------------------------------------------------------
# common validation helpers
# -----------------------------------------------------------------------------

def _validate_hourly_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    utc_value = value.astimezone(timezone.utc)
    if utc_value.minute != 0 or utc_value.second != 0 or utc_value.microsecond != 0:
        raise ValueError("timestamp must be aligned to the full UTC hour")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must be expressed in UTC (+00:00/Z), not only convertible to UTC")
    return utc_value


def _validate_json_string(value: str, expected: type | tuple[type, ...], field_name: str) -> str:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} must contain valid JSON") from exc
    if not isinstance(parsed, expected):
        names = (
            ", ".join(t.__name__ for t in expected)
            if isinstance(expected, tuple)
            else expected.__name__
        )
        raise ValueError(f"{field_name} JSON must decode to {names}")
    # canonical form makes fixtures/reproducibility deterministic
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ContractBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    run_id: str = Field(min_length=1)
    interval_start_utc: datetime

    @field_validator("interval_start_utc")
    @classmethod
    def validate_interval_start_utc(cls, value: datetime) -> datetime:
        return _validate_hourly_utc(value)


class GridStateV1(ContractBase):
    schema_version: str = Field(default="grid_state_v1", pattern=r"^grid_state_v1$")
    cell_id: str = Field(min_length=1)
    lat_center: float = Field(ge=-90, le=90)
    lon_center: float = Field(ge=-180, le=180)

    temperature_2m: float | None = None
    temperature_anomaly: float | None = None
    temperature_percentile: float | None = Field(default=None, ge=0, le=1)

    precipitation: float | None = Field(default=None, ge=0)
    precipitation_percentile: float | None = Field(default=None, ge=0, le=1)

    wind_speed: float | None = Field(default=None, ge=0)
    wind_percentile: float | None = Field(default=None, ge=0, le=1)

    solar_radiation: float | None = Field(default=None, ge=0)
    solar_percentile: float | None = Field(default=None, ge=0, le=1)

    heat_incident_score: float = Field(ge=0, le=1)
    cold_incident_score: float = Field(ge=0, le=1)
    rain_incident_score: float = Field(ge=0, le=1)
    wind_incident_score: float = Field(ge=0, le=1)
    solar_deficit_score: float = Field(ge=0, le=1)

    capacity_by_type_json: str
    generation_by_type_json: str

    substation_count: int = Field(ge=0)
    hub_max: float | None = Field(default=None, ge=0, le=1)
    transmission_exposure: float | None = Field(default=None, ge=0, le=1)

    data_quality: float = Field(ge=0, le=1)

    @field_validator("capacity_by_type_json", "generation_by_type_json")
    @classmethod
    def validate_dict_json(cls, value: str, info) -> str:
        return _validate_json_string(value, dict, info.field_name)


class AssetExposureV1(ContractBase):
    schema_version: str = Field(default="asset_exposure_v1", pattern=r"^asset_exposure_v1$")
    asset_id: str = Field(min_length=1)
    asset_type: str = Field(min_length=1)

    cell_id: str | None = None
    geometry_quality: GeometryQuality

    incident_type: IncidentType
    incident_score: float = Field(ge=0, le=1)
    exposure_reason: str = Field(min_length=1)

    generation_type: str | None = None
    capacity_mw: float | None = Field(default=None, ge=0)

    hub_score: float | None = Field(default=None, ge=0, le=1)
    voltage_kv: float | None = Field(default=None, ge=0)
    transformer_mva: float | None = Field(default=None, ge=0)

    quality_flags: str

    @field_validator("quality_flags")
    @classmethod
    def validate_quality_flags(cls, value: str) -> str:
        return _validate_json_string(value, list, "quality_flags")


class SystemSignalV1(ContractBase):
    schema_version: str = Field(default="system_signal_v1", pattern=r"^system_signal_v1$")
    zone_type: ZoneType
    zone_id: str = Field(min_length=1)

    demand_p10_mw: float = Field(ge=0)
    demand_p50_mw: float = Field(ge=0)
    demand_p90_mw: float = Field(ge=0)

    demand_percentile: float = Field(ge=0, le=1)
    supply_pressure: float | None = Field(default=None, ge=0, le=1)
    climate_exposure: float = Field(ge=0, le=1)

    generation_by_type_json: str
    main_drivers_json: str

    data_freshness_ok: bool
    quality_flags: str

    @field_validator("generation_by_type_json", "main_drivers_json")
    @classmethod
    def validate_dict_json(cls, value: str, info) -> str:
        return _validate_json_string(value, dict, info.field_name)

    @field_validator("quality_flags")
    @classmethod
    def validate_quality_flags(cls, value: str) -> str:
        return _validate_json_string(value, list, "quality_flags")

    @model_validator(mode="after")
    def validate_quantiles(self) -> "SystemSignalV1":
        if not (self.demand_p10_mw <= self.demand_p50_mw <= self.demand_p90_mw):
            raise ValueError("demand quantiles must satisfy p10 <= p50 <= p90")
        return self


class TariffV1(ContractBase):
    schema_version: str = Field(default="tariff_v1", pattern=r"^tariff_v1$")

    distributor_id: str = Field(min_length=1)
    tariff_profile_id: str = Field(min_length=1)

    zone_type: ZoneType
    zone_id: str = Field(min_length=1)

    base_te_rs_kwh: float = Field(ge=0)
    base_tusd_rs_kwh: float = Field(ge=0)
    base_total_rs_kwh: float = Field(ge=0)

    demand_pressure: float = Field(ge=0, le=1)
    supply_pressure: float | None = Field(default=None, ge=0, le=1)
    economic_signal: float | None = Field(default=None, ge=-1, le=1)

    raw_multiplier: float = Field(gt=0)
    final_multiplier: float = Field(gt=0)
    dynamic_tariff_rs_kwh: float = Field(ge=0)

    floor_applied: bool
    cap_applied: bool
    ramp_applied: bool
    neutrality_adjustment: float
    fallback_applied: bool

    reason_codes: str
    quality_flags: str

    @field_validator("reason_codes", "quality_flags")
    @classmethod
    def validate_list_json(cls, value: str, info) -> str:
        return _validate_json_string(value, list, info.field_name)

    @model_validator(mode="after")
    def validate_tariff_math(self) -> "TariffV1":
        expected_base = self.base_te_rs_kwh + self.base_tusd_rs_kwh
        if abs(expected_base - self.base_total_rs_kwh) > 1e-9:
            raise ValueError("base_total_rs_kwh must equal base_te_rs_kwh + base_tusd_rs_kwh")
        expected_dynamic = self.base_total_rs_kwh * self.final_multiplier
        if abs(expected_dynamic - self.dynamic_tariff_rs_kwh) > 1e-7:
            raise ValueError("dynamic_tariff_rs_kwh must equal base_total_rs_kwh * final_multiplier")
        return self


CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "grid_state_v1": GridStateV1,
    "asset_exposure_v1": AssetExposureV1,
    "system_signal_v1": SystemSignalV1,
    "tariff_v1": TariffV1,
}
