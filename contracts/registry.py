from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from contracts.models import CONTRACT_MODELS


@dataclass(frozen=True)
class ContractSpec:
    name: str
    model: type[BaseModel]
    unique_key: tuple[str, ...]
    expected_schema_version: str


REGISTRY: dict[str, ContractSpec] = {
    "grid_state_v1": ContractSpec(
        name="grid_state_v1",
        model=CONTRACT_MODELS["grid_state_v1"],
        unique_key=("run_id", "interval_start_utc", "cell_id"),
        expected_schema_version="grid_state_v1",
    ),
    "asset_exposure_v1": ContractSpec(
        name="asset_exposure_v1",
        model=CONTRACT_MODELS["asset_exposure_v1"],
        unique_key=("run_id", "interval_start_utc", "asset_id", "incident_type"),
        expected_schema_version="asset_exposure_v1",
    ),
    "system_signal_v1": ContractSpec(
        name="system_signal_v1",
        model=CONTRACT_MODELS["system_signal_v1"],
        unique_key=("run_id", "interval_start_utc", "zone_type", "zone_id"),
        expected_schema_version="system_signal_v1",
    ),
    "tariff_v1": ContractSpec(
        name="tariff_v1",
        model=CONTRACT_MODELS["tariff_v1"],
        unique_key=("run_id", "interval_start_utc", "distributor_id", "tariff_profile_id"),
        expected_schema_version="tariff_v1",
    ),
}


def get_contract_spec(name: str) -> ContractSpec:
    try:
        return REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown contract {name!r}; available: {available}") from exc
