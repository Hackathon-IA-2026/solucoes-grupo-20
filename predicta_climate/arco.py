from __future__ import annotations

import calendar
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import xarray as xr


ARCO_URLS = {
    "temperature": (
        "https://arco.datastores.ecmwf.int/"
        "cadl-arco-geo-007/arco/reanalysis_era5_land/"
        "sfc-2m-temperature/geoChunked.zarr"
    ),
    "precipitation": (
        "https://arco.datastores.ecmwf.int/"
        "cadl-arco-geo-009/arco/reanalysis_era5_land/"
        "sfc-pressure-precipitation/geoChunked.zarr"
    ),
    "wind": (
        "https://arco.datastores.ecmwf.int/"
        "cadl-arco-geo-008/arco/reanalysis_era5_land/"
        "sfc-wind/geoChunked.zarr"
    ),
    "radiation": (
        "https://arco.datastores.ecmwf.int/"
        "cadl-arco-geo-010/arco/reanalysis_era5_land/"
        "sfc-radiation-heat/geoChunked.zarr"
    ),
}

# ARCO commonly exposes GRIB short names. The long names are kept as aliases
# so the pipeline does not break if catalogue naming changes.
VARIABLE_ALIASES = {
    "temperature_2m": ("t2m", "2m_temperature", "temperature_2m"),
    "dewpoint_2m": ("d2m", "2m_dewpoint_temperature", "dewpoint_2m"),
    "precipitation": ("tp", "total_precipitation", "precipitation"),
    "surface_pressure": ("sp", "surface_pressure"),
    "wind_u_10m": ("u10", "10m_u_component_of_wind", "wind_u_10m"),
    "wind_v_10m": ("v10", "10m_v_component_of_wind", "wind_v_10m"),
    "solar_radiation": (
        "ssrd",
        "surface_solar_radiation_downwards",
        "solar_radiation",
    ),
}

GROUP_VARIABLES = {
    "temperature": ("temperature_2m", "dewpoint_2m"),
    "precipitation": ("precipitation",),
    "wind": ("wind_u_10m", "wind_v_10m"),
    "radiation": ("solar_radiation",),
}

CORE_GROUPS = tuple(GROUP_VARIABLES)


@dataclass(frozen=True)
class ArcoConfig:
    urls: dict[str, str] = field(default_factory=lambda: dict(ARCO_URLS))
    consolidated: bool = True


def expected_hours_for_year(year: int) -> int:
    return (366 if calendar.isleap(year) else 365) * 24


def load_cds_api_key() -> str:
    """Load the CDS API token without printing it.

    Priority:
    1) CDSAPI_KEY environment variable
    2) ~/.cdsapirc line `key: ...`
    """
    key = os.environ.get("CDSAPI_KEY", "").strip().strip('"').strip("'")
    if key:
        return key

    cdsapirc = Path.home() / ".cdsapirc"
    if cdsapirc.exists():
        for line in cdsapirc.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*key\s*:\s*(.+?)\s*$", line)
            if match:
                key = match.group(1).strip().strip('"').strip("'")
                if key:
                    return key

    raise RuntimeError(
        "CDS API key ausente. Defina CDSAPI_KEY ou configure ~/.cdsapirc."
    )


def _resolve_var(ds: xr.Dataset, logical_name: str) -> str:
    aliases = VARIABLE_ALIASES[logical_name]
    for name in aliases:
        if name in ds.data_vars:
            return name
    raise KeyError(
        f"Variável lógica '{logical_name}' não encontrada. "
        f"Aliases tentados={aliases}; disponíveis={list(ds.data_vars)}"
    )


def _to_float32(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=np.float32)


class ArcoClient:
    """Lazy client for the ERA5-Land ARCO geo-chunked stores."""

    def __init__(self, config: ArcoConfig | None = None, api_key: str | None = None):
        self.config = config or ArcoConfig()
        self.api_key = api_key or load_cds_api_key()
        self._datasets: dict[str, xr.Dataset] = {}

    def open_group(self, group: str) -> xr.Dataset:
        if group not in self.config.urls:
            raise KeyError(f"Grupo ARCO desconhecido: {group}")
        if group not in self._datasets:
            self._datasets[group] = xr.open_zarr(
                self.config.urls[group],
                consolidated=self.config.consolidated,
                storage_options={
                    "headers": {"Authorization": f"Bearer {self.api_key}"}
                },
            )
        return self._datasets[group]

    def close(self) -> None:
        for ds in self._datasets.values():
            close = getattr(ds, "close", None)
            if callable(close):
                close()
        self._datasets.clear()

    def __enter__(self) -> "ArcoClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def available_time_range(self, group: str = "temperature") -> tuple[pd.Timestamp, pd.Timestamp]:
        ds = self.open_group(group)
        times = ds["time"]
        return pd.Timestamp(times.min().values), pd.Timestamp(times.max().values)

    def _select(
        self,
        *,
        group: str,
        logical_name: str,
        points: pd.DataFrame,
        start: str,
        end: str,
    ) -> xr.DataArray:
        ds = self.open_group(group)
        source_var = _resolve_var(ds, logical_name)

        lat_indexer = xr.DataArray(
            points["latitude"].to_numpy(dtype=float),
            dims="point",
            coords={"point": np.arange(len(points))},
        )
        lon_indexer = xr.DataArray(
            points["longitude"].to_numpy(dtype=float),
            dims="point",
            coords={"point": np.arange(len(points))},
        )

        arr = (
            ds[source_var]
            .sel(latitude=lat_indexer, longitude=lon_indexer, method="nearest")
            .sel(time=slice(start, end))
            .transpose("time", "point")
        )
        return arr

    def fetch_batch(
        self,
        *,
        points: pd.DataFrame,
        year: int,
        groups: Sequence[str] = CORE_GROUPS,
    ) -> pd.DataFrame:
        """Fetch one year for a point batch and return canonical hourly columns."""
        if points.empty:
            raise ValueError("Lote de pontos vazio.")
        required = {"cell_id", "latitude", "longitude", "subsystem"}
        missing = required.difference(points.columns)
        if missing:
            raise ValueError(f"Pontos sem colunas obrigatórias: {sorted(missing)}")

        start = f"{year:04d}-01-01T00:00:00"
        end = f"{year:04d}-12-31T23:00:00"

        arrays: dict[str, xr.DataArray] = {}
        for group in groups:
            if group not in GROUP_VARIABLES:
                raise ValueError(f"Grupo inválido: {group}")
            for logical_name in GROUP_VARIABLES[group]:
                arrays[logical_name] = self._select(
                    group=group,
                    logical_name=logical_name,
                    points=points,
                    start=start,
                    end=end,
                )

        if not arrays:
            raise ValueError("Nenhum grupo ARCO selecionado.")

        # Trigger remote I/O. xarray/dask will deduplicate shared Zarr chunks
        # inside each graph where possible.
        loaded = {name: arr.load() for name, arr in arrays.items()}

        first = next(iter(loaded.values()))
        times = pd.DatetimeIndex(first["time"].values)
        expected = expected_hours_for_year(year)
        if len(times) != expected:
            raise RuntimeError(
                f"Ano {year}: ARCO retornou {len(times)} horas; esperado={expected}."
            )
        if times.has_duplicates:
            raise RuntimeError(f"Ano {year}: timestamps duplicados no ARCO.")

        n_time = len(times)
        n_points = len(points)
        out = pd.DataFrame(
            {
                "time_utc": np.repeat(times.values, n_points),
                "cell_id": np.tile(points["cell_id"].astype(str).to_numpy(), n_time),
                "subsystem": np.tile(points["subsystem"].astype(str).to_numpy(), n_time),
                "latitude": np.tile(points["latitude"].to_numpy(dtype=np.float32), n_time),
                "longitude": np.tile(points["longitude"].to_numpy(dtype=np.float32), n_time),
            }
        )

        def flat(name: str) -> np.ndarray:
            return _to_float32(loaded[name].values).reshape(-1)

        if "temperature_2m" in loaded:
            out["temperature_2m_c"] = flat("temperature_2m") - np.float32(273.15)
        if "dewpoint_2m" in loaded:
            out["dewpoint_2m_c"] = flat("dewpoint_2m") - np.float32(273.15)
        if "precipitation" in loaded:
            # ARCO exposes hourly de-accumulated ERA5-Land precipitation in metres.
            out["precipitation_mm"] = flat("precipitation") * np.float32(1000.0)
        if "wind_u_10m" in loaded:
            out["wind_u_10m_ms"] = flat("wind_u_10m")
        if "wind_v_10m" in loaded:
            out["wind_v_10m_ms"] = flat("wind_v_10m")
        if "wind_u_10m" in loaded and "wind_v_10m" in loaded:
            u = out["wind_u_10m_ms"].to_numpy(dtype=np.float32)
            v = out["wind_v_10m_ms"].to_numpy(dtype=np.float32)
            out["wind_speed_10m_ms"] = np.sqrt(u * u + v * v).astype(np.float32)
        if "solar_radiation" in loaded:
            ssrd = flat("solar_radiation")
            out["solar_radiation_j_m2"] = ssrd
            out["solar_radiation_w_m2_avg"] = ssrd / np.float32(3600.0)

        return out


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
