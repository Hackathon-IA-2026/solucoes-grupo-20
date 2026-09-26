from __future__ import annotations
from datetime import timedelta

"""E3 climate context using the rules preserved in the 2026-09-18 OpenMeteo snapshot.

This module deliberately separates:

* the 10-complete-year ERA5-Land monthly temperature baseline;
* target-year daily context/events;
* propagation of daily context to each UTC target hour before subsystem aggregation.

No continuous empirical percentile rank is invented because the supplied snapshot only
specifies monthly threshold percentiles (p05/p10/p90/p95), not a continuous percentile
feature. E3 therefore uses anomalies from the monthly climatological mean and event flags
whose predicates are explicitly supported by ``config/event_rules.json``.
"""

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from motor_sin.climate.e2_pilot import canonical_zone, load_pilot_points
from motor_sin.climate.openmeteo import OPENMETEO_ARCHIVE_URL
from motor_sin.climate.http_client import fetch_json_with_retry
from motor_sin.climate.openmeteo_snapshot_anomaly import (
    SNAPSHOT_BASELINE_VERSION,
    SNAPSHOT_RULES_VERSION,
    baseline_years_for_target,
    build_monthly_temperature_baseline,
    load_snapshot_rules,
    score_daily_temperature_context,
)
from motor_sin.common.provenance import find_cached_raw_record, persist_immutable_raw_record, utc_now_iso
from motor_sin.grid.index import coordinate_to_index


BASELINE_DAILY_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
)
# The supplied OpenMeteo snapshot pins ERA5-Land only for the 10-year
# temperature baseline. Its historical daily collector does NOT pass a
# ``models`` parameter and requests daily temperature, precipitation and
# wind gusts from Open-Meteo's default Historical Weather API selection.
# Keep that distinction: baseline temperatures are ERA5-Land; target-year
# context follows the snapshot historical collector semantics (Best Match).
TARGET_SNAPSHOT_DAILY_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_gusts_10m_max",
)


@dataclass(frozen=True)
class E3DownloadSpec:
    channel: str
    # ``None`` means: omit the models parameter, matching the supplied
    # snapshot's historical.py collector (Open-Meteo Best Match).
    model: str | None
    variables: tuple[str, ...]
    start_date: str
    end_date: str


def infer_target_year_from_load(
    load: pd.DataFrame,
    *,
    subsystem_id: str,
    calendar_timezone: str = "America/Sao_Paulo",
) -> int:
    required = {"interval_start_utc", "subsystem_id", "load_mw"}
    missing = required - set(load.columns)
    if missing:
        raise ValueError(f"load missing columns: {sorted(missing)}")
    zone = canonical_zone(subsystem_id)
    work = load.copy()
    work["subsystem_id"] = work["subsystem_id"].map(canonical_zone)
    work["interval_start_utc"] = pd.to_datetime(work["interval_start_utc"], utc=True, errors="raise")
    work = work[work["subsystem_id"].eq(zone)]
    if work.empty:
        raise ValueError(f"no load rows for subsystem {zone}")
    ZoneInfo(calendar_timezone)
    years = work["interval_start_utc"].dt.tz_convert(calendar_timezone).dt.year
    counts = years.value_counts()
    target_year = int(counts.index[0])
    if int(counts.iloc[0]) < int(0.80 * len(work)):
        raise ValueError(
            "unable to infer a dominant target year from load; pass --target-year explicitly"
        )
    return target_year


def build_daily_archive_parameters(
    *,
    latitude: float,
    longitude: float,
    timezone_name: str,
    start_date: str,
    end_date: str,
    variables: Iterable[str],
    model: str | None,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    ZoneInfo(timezone_name)
    variables = tuple(str(v) for v in variables)
    if not variables:
        raise ValueError("at least one daily variable is required")
    params: dict[str, Any] = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(variables),
        "timezone": str(timezone_name),
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timeformat": "iso8601",
    }
    if model is not None:
        params["models"] = str(model)
    return params


def _fetch_json(params: dict[str, Any], *, timeout_seconds: int = 90) -> tuple[int, dict[str, Any], str]:
    url = f"{OPENMETEO_ARCHIVE_URL}?{urlencode(params)}"
    status, payload = fetch_json_with_retry(
        url, timeout_seconds=timeout_seconds, user_agent="predicta-hackathon/1.11",
        max_retries=10, base_backoff_seconds=10.0,
    )
    if not isinstance(payload, dict):
        raise ValueError("Open-Meteo daily archive response must be a JSON object")
    if payload.get("error") is True:
        raise RuntimeError(f"Open-Meteo daily archive request failed: status={status} payload={payload}")
    return status, payload, url


def _validate_daily_payload(payload: dict[str, Any], variables: Iterable[str]) -> None:
    block = payload.get("daily")
    if not isinstance(block, dict):
        raise ValueError("Open-Meteo daily payload does not contain daily object")
    times = block.get("time")
    if not isinstance(times, list) or not times:
        raise ValueError("Open-Meteo daily.time must be a non-empty list")
    n = len(times)
    problems: list[str] = []
    for variable in variables:
        values = block.get(variable)
        if not isinstance(values, list) or len(values) != n:
            problems.append(f"{variable}: missing or length mismatch")
            continue
        non_null = sum(v is not None for v in values)
        if non_null == 0:
            problems.append(f"{variable}: all values are null")
    if problems:
        raise ValueError("daily climate source does not provide required variables: " + "; ".join(problems))


def download_daily_record(
    *,
    point: pd.Series | Any,
    spec: E3DownloadSpec,
    raw_directory: str | Path,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    params = build_daily_archive_parameters(
        latitude=float(point.latitude),
        longitude=float(point.longitude),
        timezone_name=str(point.timezone),
        start_date=spec.start_date,
        end_date=spec.end_date,
        variables=spec.variables,
        model=spec.model,
    )
    model_label = spec.model or "best_match"
    external_id = (
        f"e3:{spec.channel}:{point.point_id}:{model_label}:"
        f"{spec.start_date}:{spec.end_date}"
    )
    cached = find_cached_raw_record(
        directory=Path(raw_directory), source_service="historical_daily",
        external_id=external_id, request_parameters=params,
    )
    if cached:
        path, record = cached
        payload = record.get("payload") or {}
        _validate_daily_payload(payload, spec.variables)
        return {
            "channel": spec.channel, "point_id": str(point.point_id), "name": str(point.name),
            "state": str(point.state), "subsystem_id": canonical_zone(point.subsystem_id),
            "latitude_requested": float(point.latitude), "longitude_requested": float(point.longitude),
            "timezone": str(point.timezone), "weight": float(point.weight), "model": model_label,
            "variables": list(spec.variables), "start_date": spec.start_date, "end_date": spec.end_date,
            "raw_file": str(path), "created": False, "content_hash": str(record.get("payload_hash") or ""),
            "retrieved_at_utc": record.get("retrieved_at_utc"), "request_url": record.get("source_endpoint"),
        }
    retrieved_at = utc_now_iso()
    status, payload, request_url = _fetch_json(params, timeout_seconds=timeout_seconds)
    _validate_daily_payload(payload, spec.variables)
    path, created, content_hash = persist_immutable_raw_record(
        directory=Path(raw_directory),
        source="open-meteo",
        source_service="historical_daily",
        source_endpoint=OPENMETEO_ARCHIVE_URL,
        external_id=external_id,
        request_parameters=params,
        payload=payload,
        http_status=status,
        retrieved_at_utc=retrieved_at,
    )
    return {
        "channel": spec.channel,
        "point_id": str(point.point_id),
        "name": str(point.name),
        "state": str(point.state),
        "subsystem_id": canonical_zone(point.subsystem_id),
        "latitude_requested": float(point.latitude),
        "longitude_requested": float(point.longitude),
        "timezone": str(point.timezone),
        "weight": float(point.weight),
        "model": spec.model or "best_match",
        "variables": list(spec.variables),
        "start_date": spec.start_date,
        "end_date": spec.end_date,
        "raw_file": str(path),
        "created": bool(created),
        "content_hash": content_hash,
        "retrieved_at_utc": retrieved_at,
        "request_url": request_url,
    }


def download_e3_context(
    points: pd.DataFrame,
    *,
    target_year: int,
    raw_directory: str | Path,
    timeout_seconds: int = 90,
    rules: dict | None = None,
) -> pd.DataFrame:
    rules = rules or load_snapshot_rules()
    baseline_cfg = rules["temperature_baseline"]
    complete_years = int(baseline_cfg["complete_years"])
    years = baseline_years_for_target(target_year, complete_years)
    if str(baseline_cfg["model"]) != "era5_land":
        raise ValueError("snapshot temperature baseline model must be era5_land")
    if str(baseline_cfg["grouping"]) != "calendar_month":
        raise ValueError("this E3 implementation supports the supplied calendar_month baseline only")

    specs = (
        E3DownloadSpec(
            channel="baseline_temperature",
            model="era5_land",
            variables=BASELINE_DAILY_VARIABLES,
            start_date=f"{years[0]}-01-01",
            end_date=f"{years[-1]}-12-31",
        ),
        E3DownloadSpec(
            channel="target_snapshot_daily",
            model=None,
            variables=TARGET_SNAPSHOT_DAILY_VARIABLES,
            start_date=f"{target_year}-01-01",
            end_date=f"{target_year}-12-31",
        ),
    )
    rows: list[dict[str, Any]] = []
    for point in points.itertuples(index=False):
        for spec in specs:
            rows.append(
                download_daily_record(
                    point=point,
                    spec=spec,
                    raw_directory=raw_directory,
                    timeout_seconds=timeout_seconds,
                )
            )
    return pd.DataFrame(rows)


def _load_raw_record(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("payload"), dict):
        raise ValueError(f"invalid immutable RAW record: {path}")
    return document, document["payload"]


def parse_daily_raw_file(
    path: str | Path,
    *,
    point_id: str,
    latitude_requested: float,
    longitude_requested: float,
    timezone_name: str,
    expected_variables: Iterable[str],
) -> pd.DataFrame:
    record, payload = _load_raw_record(path)
    _validate_daily_payload(payload, expected_variables)
    block = payload["daily"]
    units = payload.get("daily_units") or {}
    n = len(block["time"])
    cell_id = coordinate_to_index(float(latitude_requested), float(longitude_requested)).cell_id
    data: dict[str, Any] = {
        "point_id": [str(point_id)] * n,
        "cell_id": [cell_id] * n,
        "date_local": [str(x) for x in block["time"]],
        "timezone": [str(timezone_name)] * n,
        "source_model": [str((record.get("request_parameters") or {}).get("models") or "best_match")] * n,
        "raw_record_id": [record.get("raw_record_id")] * n,
        "raw_payload_hash": [record.get("payload_hash")] * n,
    }
    for variable in expected_variables:
        vals = pd.to_numeric(pd.Series(block[variable]), errors="coerce")
        data[variable] = vals.to_numpy()
        data[f"{variable}__unit"] = [units.get(variable)] * n
    out = pd.DataFrame(data)
    if out.duplicated(["point_id", "date_local"]).any():
        raise ValueError(f"duplicate daily rows in {path}")
    return out


def parse_manifest_baseline_daily(manifest: pd.DataFrame) -> pd.DataFrame:
    """Parse only baseline_temperature records from an E3 manifest.

    This is used by the operational baseline refresher so it can reuse the annual
    historical cache without issuing a dummy target-day request.
    """
    required = {
        "channel", "point_id", "latitude_requested", "longitude_requested", "timezone",
        "raw_file", "variables",
    }
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"E3 manifest missing columns: {sorted(missing)}")
    frames: list[pd.DataFrame] = []
    for row in manifest[manifest["channel"].astype(str).eq("baseline_temperature")].itertuples(index=False):
        variables = row.variables
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except json.JSONDecodeError:
                variables = [v for v in variables.split(",") if v]
        frame = parse_daily_raw_file(
            row.raw_file,
            point_id=row.point_id,
            latitude_requested=float(row.latitude_requested),
            longitude_requested=float(row.longitude_requested),
            timezone_name=row.timezone,
            expected_variables=tuple(variables),
        )
        frame["name"] = str(row.name)
        frame["state"] = str(row.state)
        frame["subsystem_id"] = canonical_zone(row.subsystem_id)
        frame["weight"] = float(row.weight)
        frames.append(frame)
    if not frames:
        raise ValueError("E3 manifest must contain baseline_temperature")
    return pd.concat(frames, ignore_index=True)


def parse_manifest_daily_frames(manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "channel", "point_id", "latitude_requested", "longitude_requested", "timezone",
        "raw_file", "variables",
    }
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"E3 manifest missing columns: {sorted(missing)}")

    baseline_frames: list[pd.DataFrame] = []
    target_frames: list[pd.DataFrame] = []
    # Backward-compatible containers for an interrupted/older v1.3.0 manifest.
    legacy_target_land: list[pd.DataFrame] = []
    legacy_target_precip: list[pd.DataFrame] = []

    for row in manifest.itertuples(index=False):
        variables = row.variables
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except json.JSONDecodeError:
                variables = [v for v in variables.split(",") if v]
        frame = parse_daily_raw_file(
            row.raw_file,
            point_id=row.point_id,
            latitude_requested=float(row.latitude_requested),
            longitude_requested=float(row.longitude_requested),
            timezone_name=row.timezone,
            expected_variables=tuple(variables),
        )
        frame["name"] = str(row.name)
        frame["state"] = str(row.state)
        frame["subsystem_id"] = canonical_zone(row.subsystem_id)
        frame["weight"] = float(row.weight)
        if row.channel == "baseline_temperature":
            baseline_frames.append(frame)
        elif row.channel == "target_snapshot_daily":
            target_frames.append(frame)
        elif row.channel == "target_temperature_wind":
            legacy_target_land.append(frame)
        elif row.channel == "target_precipitation":
            legacy_target_precip.append(frame)
        else:
            raise ValueError(f"unknown E3 manifest channel: {row.channel}")

    if not baseline_frames:
        raise ValueError("E3 manifest must contain baseline_temperature")
    baseline = pd.concat(baseline_frames, ignore_index=True)

    if target_frames:
        target = pd.concat(target_frames, ignore_index=True)
        required_target = {
            "temperature_2m_max", "temperature_2m_min",
            "precipitation_sum", "wind_gusts_10m_max",
        }
        missing_target = required_target - set(target.columns)
        if missing_target:
            raise ValueError(f"target_snapshot_daily missing columns: {sorted(missing_target)}")
        return baseline, target

    # Legacy v1.3.0 compatibility only. A complete old manifest can still be read,
    # but the corrected downloader no longer creates this split because forcing
    # wind gusts through ERA5-Land returned all-null values in real execution.
    if not legacy_target_land or not legacy_target_precip:
        raise ValueError(
            "E3 manifest must contain target_snapshot_daily (v1.3.1) or both "
            "legacy target_temperature_wind and target_precipitation channels"
        )
    land = pd.concat(legacy_target_land, ignore_index=True)
    precip = pd.concat(legacy_target_precip, ignore_index=True)
    merge_cols = ["point_id", "cell_id", "date_local", "timezone", "name", "state", "subsystem_id", "weight"]
    cols = [c for c in ["precipitation_sum", "wind_gusts_10m_max"] if c in precip.columns]
    target = land.merge(
        precip[merge_cols + cols],
        on=merge_cols,
        how="inner",
        validate="one_to_one",
        suffixes=("", "_precip"),
    )
    return baseline, target


def _mark_consecutive_sequences(
    frame: pd.DataFrame,
    *,
    predicate_col: str,
    minimum_days: int,
    output_col: str,
) -> pd.DataFrame:
    out = frame.copy()
    out[output_col] = False
    for point_id, g in out.groupby("point_id", sort=False):
        idxs = list(g.sort_values("date_local").index)
        current: list[int] = []
        prev_date: pd.Timestamp | None = None
        sequences: list[list[int]] = []
        for idx in idxs:
            current_date = pd.Timestamp(out.at[idx, "date_local"])
            passed = bool(out.at[idx, predicate_col])
            consecutive = prev_date is not None and current_date - prev_date == timedelta(days=1)
            if passed:
                if current and not consecutive:
                    sequences.append(current)
                    current = []
                current.append(idx)
            else:
                if current:
                    sequences.append(current)
                    current = []
            prev_date = current_date
        if current:
            sequences.append(current)
        for seq in sequences:
            if len(seq) >= int(minimum_days):
                out.loc[seq, output_col] = True
    return out


def build_e3_daily_context(
    baseline_daily: pd.DataFrame,
    target_daily: pd.DataFrame,
    *,
    target_year: int,
    rules: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the exact snapshot-supported daily anomaly/event context.

    Temperature baseline semantics come directly from the supplied snapshot:
    10 complete prior years, calendar-month grouping, ERA5-Land, mean/p05/p10/p90/p95,
    NumPy linear quantiles, and the configured minimum monthly sample count.
    """
    rules = rules or load_snapshot_rules()
    baseline_cfg = rules["temperature_baseline"]
    if int(baseline_cfg["complete_years"]) != 10:
        raise ValueError("supplied snapshot expected complete_years=10")
    if list(baseline_cfg["variables"]) != ["temperature_2m_max", "temperature_2m_min"]:
        raise ValueError("unexpected snapshot temperature baseline variables")
    if list(baseline_cfg["statistics"]) != ["mean", "p05", "p10", "p90", "p95"]:
        raise ValueError("unexpected snapshot temperature baseline statistics")
    if str(baseline_cfg["percentile_method"]) != "linear_interpolation_n_minus_1":
        raise ValueError("unexpected snapshot percentile method")

    baseline_input = baseline_daily[[
        "cell_id", "date_local", "temperature_2m_max", "temperature_2m_min"
    ]].copy()
    baseline = build_monthly_temperature_baseline(
        baseline_input,
        target_year=target_year,
        minimum_samples_per_month=int(baseline_cfg["minimum_samples_per_month"]),
    )

    scored_long = score_daily_temperature_context(
        target_daily[["cell_id", "date_local", "temperature_2m_max", "temperature_2m_min"]],
        baseline,
        rules=rules,
    )
    max_scored = scored_long[scored_long["metric"].eq("temperature_2m_max")].copy()
    min_scored = scored_long[scored_long["metric"].eq("temperature_2m_min")].copy()
    max_scored = max_scored.rename(columns={
        "value": "temperature_2m_max",
        "mean": "temperature_2m_max_climatological_mean",
        "p90": "temperature_2m_max_p90",
        "p95": "temperature_2m_max_p95",
        "anomaly_from_mean_c": "temperature_max_anomaly_c",
    })
    min_scored = min_scored.rename(columns={
        "value": "temperature_2m_min",
        "mean": "temperature_2m_min_climatological_mean",
        "p05": "temperature_2m_min_p05",
        "p10": "temperature_2m_min_p10",
        "p90": "temperature_2m_min_p90",
        "anomaly_from_mean_c": "temperature_min_anomaly_c",
    })
    hot_cols = [
        "cell_id", "date_local", "temperature_2m_max", "temperature_2m_max_climatological_mean",
        "temperature_2m_max_p90", "temperature_2m_max_p95", "temperature_max_anomaly_c",
        "unusually_hot_day", "extreme_heat_day", "heat_wave_day_predicate",
    ]
    cold_cols = [
        "cell_id", "date_local", "temperature_2m_min", "temperature_2m_min_climatological_mean",
        "temperature_2m_min_p05", "temperature_2m_min_p10", "temperature_2m_min_p90",
        "temperature_min_anomaly_c", "unusually_cold_day", "extreme_cold_day", "cold_wave_day_predicate",
    ]
    context = target_daily.merge(max_scored[hot_cols], on=["cell_id", "date_local"], how="left", validate="one_to_one", suffixes=("", "_score"))
    context = context.merge(min_scored[cold_cols], on=["cell_id", "date_local"], how="left", validate="one_to_one", suffixes=("", "_score"))
    for c in ["temperature_2m_max_score", "temperature_2m_min_score"]:
        if c in context.columns:
            context = context.drop(columns=[c])

    # Snapshot detector only emits the highest daily heat/cold severity satisfied.
    context["unusually_hot_day"] = context["unusually_hot_day"].astype(bool) & ~context["extreme_heat_day"].astype(bool)
    context["unusually_cold_day"] = context["unusually_cold_day"].astype(bool) & ~context["extreme_cold_day"].astype(bool)

    # Warm-night evidence is explicitly described as complementary, not a condition.
    context["warm_night_evidence"] = pd.to_numeric(context["temperature_2m_min"], errors="coerce").ge(
        pd.to_numeric(context["temperature_2m_min_p90"], errors="coerce")
    )

    te = rules["temperature_events"]
    context = _mark_consecutive_sequences(
        context,
        predicate_col="heat_wave_day_predicate",
        minimum_days=int(te["heat_wave_candidate"]["minimum_consecutive_days"]),
        output_col="heat_wave_candidate",
    )
    context = _mark_consecutive_sequences(
        context,
        predicate_col="cold_wave_day_predicate",
        minimum_days=int(te["cold_wave_candidate"]["minimum_consecutive_days"]),
        output_col="cold_wave_candidate",
    )

    precip = pd.to_numeric(context["precipitation_sum"], errors="coerce")
    pr = rules["precipitation_events"]
    extreme_rain_threshold = float(pr["extreme_rain_day"]["threshold"])
    heavy_rain_threshold = float(pr["heavy_rain_day"]["threshold"])
    context["extreme_rain_day"] = precip.ge(extreme_rain_threshold)
    context["heavy_rain_day"] = precip.ge(heavy_rain_threshold) & ~context["extreme_rain_day"]

    gust = pd.to_numeric(context["wind_gusts_10m_max"], errors="coerce")
    wr = rules["wind_events"]
    t_extreme = float(wr["extreme_wind_day"]["threshold"])
    t_severe = float(wr["severe_wind_day"]["threshold"])
    t_strong = float(wr["strong_wind_day"]["threshold"])
    context["extreme_wind_day"] = gust.ge(t_extreme)
    context["severe_wind_day"] = gust.ge(t_severe) & ~context["extreme_wind_day"]
    context["strong_wind_day"] = gust.ge(t_strong) & ~context["severe_wind_day"] & ~context["extreme_wind_day"]

    sr = rules["storm_events"]["storm_candidate"]
    # Historical/reanalysis mode: weather_code is not used because the supplied snapshot
    # explicitly restricts it to forecast. The historical predicate is daily rain AND gust.
    context["storm_candidate"] = precip.ge(float(sr["minimum_precipitation_mm"])) & gust.ge(
        float(sr["minimum_wind_gust_kmh"])
    )

    context["heat_event"] = context[["unusually_hot_day", "extreme_heat_day", "heat_wave_candidate"]].any(axis=1)
    context["cold_event"] = context[["unusually_cold_day", "extreme_cold_day", "cold_wave_candidate"]].any(axis=1)
    context["rain_event"] = context[["heavy_rain_day", "extreme_rain_day"]].any(axis=1)
    context["wind_event"] = context[["strong_wind_day", "severe_wind_day", "extreme_wind_day"]].any(axis=1)
    context["event_any"] = context[["heat_event", "cold_event", "rain_event", "wind_event", "storm_candidate"]].any(axis=1)

    context["rules_version"] = str(rules["rules_version"])
    context["baseline_version"] = str(baseline_cfg["baseline_version"])
    context["baseline_year_start"] = int(target_year) - int(baseline_cfg["complete_years"])
    context["baseline_year_end"] = int(target_year) - 1
    context["baseline_grouping"] = str(baseline_cfg["grouping"])
    context["baseline_scientific_status"] = str(rules["methodology"]["scientific_status"])
    context["storm_simultaneity_confirmed"] = bool(sr.get("simultaneity_confirmed", False))

    return baseline.sort_values(["cell_id", "month", "metric"]).reset_index(drop=True), context.sort_values(["point_id", "date_local"]).reset_index(drop=True)


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    mask = v.notna() & w.notna() & w.gt(0)
    if not mask.any():
        return float("nan")
    return float(np.average(v[mask].to_numpy(dtype=float), weights=w[mask].to_numpy(dtype=float)))


def build_e3_hourly_zone_context(
    daily_context: pd.DataFrame,
    points: pd.DataFrame,
    hourly_index: pd.DataFrame,
    *,
    subsystem_id: str,
) -> pd.DataFrame:
    """Propagate point-local daily context to UTC target hours, then aggregate to one zone."""
    zone = canonical_zone(subsystem_id)
    p = points.copy()
    p["subsystem_id"] = p["subsystem_id"].map(canonical_zone)
    p = p[p["subsystem_id"].eq(zone)].copy()
    if p.empty:
        raise ValueError(f"no E3 points for subsystem {zone}")
    h = hourly_index[["interval_start_utc"]].drop_duplicates().copy()
    h["interval_start_utc"] = pd.to_datetime(h["interval_start_utc"], utc=True, errors="raise")
    h["_join"] = 1
    pp = p[["point_id", "timezone", "weight"]].copy()
    pp["_join"] = 1
    expanded = h.merge(pp, on="_join", how="inner").drop(columns="_join")

    # Different representative points can have different civil time zones.
    local_dates = pd.Series(index=expanded.index, dtype=object)
    for tz_name, idx in expanded.groupby("timezone").groups.items():
        ZoneInfo(str(tz_name))
        local_dates.loc[idx] = expanded.loc[idx, "interval_start_utc"].dt.tz_convert(str(tz_name)).dt.date.astype(str)
    expanded["date_local"] = local_dates

    ctx = daily_context.copy()
    context_cols = [c for c in ctx.columns if c not in {"cell_id", "timezone", "name", "state", "subsystem_id", "weight"}]
    expanded = expanded.merge(
        ctx[context_cols],
        on=["point_id", "date_local"],
        how="left",
        validate="many_to_one",
    )

    numeric_context = [
        "temperature_max_anomaly_c",
        "temperature_min_anomaly_c",
    ]
    event_cols = [
        "unusually_hot_day", "extreme_heat_day", "heat_wave_candidate",
        "unusually_cold_day", "extreme_cold_day", "cold_wave_candidate",
        "heavy_rain_day", "extreme_rain_day",
        "strong_wind_day", "severe_wind_day", "extreme_wind_day",
        "storm_candidate", "warm_night_evidence",
        "heat_event", "cold_event", "rain_event", "wind_event", "event_any",
    ]
    rows: list[dict[str, Any]] = []
    for ts, g in expanded.groupby("interval_start_utc", sort=True):
        row: dict[str, Any] = {
            "interval_start_utc": ts,
            "subsystem_id": zone,
        }
        for c in numeric_context:
            vals = pd.to_numeric(g[c], errors="coerce") if c in g else pd.Series(dtype=float)
            if len(vals) and vals.notna().any():
                row[f"{c}_mean"] = _weighted_mean(vals, g["weight"])
                row[f"{c}_p90"] = float(vals.dropna().quantile(0.90))
                row[f"{c}_max"] = float(vals.dropna().max())
                row[f"{c}_min"] = float(vals.dropna().min())
        for c in event_cols:
            if c in g:
                vals = pd.to_numeric(g[c], errors="coerce")
                row[f"incident_{c}_fraction"] = _weighted_mean(vals, g["weight"])
        row["incident_heat_fraction"] = row.get("incident_heat_event_fraction", 0.0)
        row["incident_cold_fraction"] = row.get("incident_cold_event_fraction", 0.0)
        row["incident_rain_fraction"] = row.get("incident_rain_event_fraction", 0.0)
        row["incident_wind_fraction"] = row.get("incident_wind_event_fraction", 0.0)
        row["incident_storm_fraction"] = row.get("incident_storm_candidate_fraction", 0.0)
        row["incident_cell_fraction"] = row.get("incident_event_any_fraction", 0.0)
        row["e3_point_count"] = int(g["point_id"].nunique())
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("E3 hourly aggregation produced no rows")
    meta = daily_context.iloc[0]
    out["e3_rules_version"] = str(meta["rules_version"])
    out["e3_baseline_version"] = str(meta["baseline_version"])
    out["e3_baseline_year_start"] = int(meta["baseline_year_start"])
    out["e3_baseline_year_end"] = int(meta["baseline_year_end"])
    out["e3_context_resolution"] = "daily_local_propagated_to_target_hour"
    out["e3_spatial_method"] = "MVP_REPRESENTATIVE_POINTS_UNIFORM"
    return out.sort_values("interval_start_utc").reset_index(drop=True)


def merge_e2_with_e3_context(e2_zone: pd.DataFrame, e3_hourly: pd.DataFrame) -> pd.DataFrame:
    e2 = e2_zone.copy()
    e3 = e3_hourly.copy()
    for frame in (e2, e3):
        frame["interval_start_utc"] = pd.to_datetime(frame["interval_start_utc"], utc=True, errors="raise")
        frame["subsystem_id"] = frame["subsystem_id"].map(canonical_zone)
    if e2.duplicated(["interval_start_utc", "subsystem_id"]).any():
        raise ValueError("E2 zone climate has duplicate subsystem-hour rows")
    if e3.duplicated(["interval_start_utc", "subsystem_id"]).any():
        raise ValueError("E3 context has duplicate subsystem-hour rows")
    out = e2.merge(e3, on=["interval_start_utc", "subsystem_id"], how="left", validate="one_to_one")
    # E3 readiness requires real enhanced data on the load-overlap year. Do not replace
    # missing enhanced values with zero, because missing context is not evidence of no event.
    enhanced = [c for c in out.columns if "anomaly_" in c or c.startswith("incident_")]
    if not enhanced:
        raise ValueError("E3 merge produced no enhanced anomaly/incident features")
    if not any(pd.to_numeric(out[c], errors="coerce").notna().any() for c in enhanced):
        raise ValueError("all E3 enhanced features are null after merge")
    return out.sort_values(["subsystem_id", "interval_start_utc"]).reset_index(drop=True)


def e3_quality_summary(
    baseline: pd.DataFrame,
    daily_context: pd.DataFrame,
    hourly_context: pd.DataFrame,
    merged_zone: pd.DataFrame,
) -> dict[str, Any]:
    incident_cols = [c for c in hourly_context.columns if c.startswith("incident_")]
    event_hours = {
        c: int(pd.to_numeric(hourly_context[c], errors="coerce").fillna(0).gt(0).sum())
        for c in incident_cols
    }
    return {
        "rules_version": SNAPSHOT_RULES_VERSION,
        "baseline_version": SNAPSHOT_BASELINE_VERSION,
        "baseline_rows": int(len(baseline)),
        "baseline_cells": int(baseline["cell_id"].nunique()),
        "baseline_months": sorted(int(x) for x in baseline["month"].unique()),
        "daily_context_rows": int(len(daily_context)),
        "daily_context_points": int(daily_context["point_id"].nunique()),
        "hourly_context_rows": int(len(hourly_context)),
        "merged_zone_rows": int(len(merged_zone)),
        "event_hours_nonzero": event_hours,
        "methodology": {
            "temperature_anomaly": "observed daily Tmax/Tmin minus local calendar-month climatological mean",
            "temperature_baseline": "10 complete prior years, ERA5-Land, mean/p05/p10/p90/p95",
            "precipitation_events": "absolute daily thresholds from supplied snapshot",
            "wind_events": "absolute daily gust thresholds from supplied snapshot",
            "storm_historical_logic": "daily precipitation AND daily maximum gust; simultaneity_confirmed=false",
            "scientific_status": "operational_baseline_not_official_climatological_normal",
        },
    }
