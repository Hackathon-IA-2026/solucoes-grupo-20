from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from contracts.registry import get_contract_spec


@dataclass
class ValidationReport:
    contract: str
    rows: int
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def raise_for_errors(self) -> None:
        if self.errors:
            joined = "\n".join(f"- {item}" for item in self.errors)
            raise ValueError(f"contract validation failed:\n{joined}")


def _normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            return value
    return value


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        try:
            return pd.read_parquet(path)
        except ImportError as exc:
            raise RuntimeError(
                "Parquet requires pyarrow. Install the project dependencies with "
                "`pip install -e \".[dev]\"`."
            ) from exc
    raise ValueError(f"unsupported table format: {suffix}")


def validate_dataframe(
    df: pd.DataFrame,
    contract: str,
    *,
    expected_hours: int | None = None,
) -> ValidationReport:
    spec = get_contract_spec(contract)
    report = ValidationReport(contract=contract, rows=len(df), valid=False)

    required = set(spec.model.model_fields)
    present = set(df.columns)
    missing = sorted(required - present)
    extras = sorted(present - required)

    if missing:
        report.errors.append(f"missing columns: {missing}")
    if extras:
        report.errors.append(f"unexpected columns for frozen v1 schema: {extras}")
    if report.errors:
        return report

    duplicated = df.duplicated(list(spec.unique_key), keep=False)
    if duplicated.any():
        examples = (
            df.loc[duplicated, list(spec.unique_key)]
            .head(5)
            .astype(str)
            .to_dict(orient="records")
        )
        report.errors.append(
            f"duplicate contract key {spec.unique_key}; examples={examples}"
        )

    row_error_count = 0
    for idx, raw_row in df.iterrows():
        row = {key: _normalize_scalar(value) for key, value in raw_row.to_dict().items()}
        try:
            spec.model.model_validate(row)
        except ValidationError as exc:
            row_error_count += 1
            if row_error_count <= 20:
                compact = "; ".join(
                    f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                    for err in exc.errors()
                )
                report.errors.append(f"row {idx}: {compact}")

    if row_error_count > 20:
        report.errors.append(f"... {row_error_count - 20} additional row errors omitted")

    if expected_hours is not None and contract in {"system_signal_v1", "tariff_v1"}:
        if expected_hours <= 0:
            report.errors.append("expected_hours must be positive")
        else:
            group_cols = (
                ["run_id", "zone_type", "zone_id"]
                if contract == "system_signal_v1"
                else ["run_id", "distributor_id", "tariff_profile_id"]
            )
            parsed = df.copy()
            parsed["_ts"] = pd.to_datetime(parsed["interval_start_utc"], utc=True, errors="coerce")
            for key, group in parsed.groupby(group_cols, dropna=False):
                if len(group) != expected_hours:
                    report.errors.append(
                        f"group {key!r} has {len(group)} rows; expected {expected_hours}"
                    )
                    continue
                ordered = group["_ts"].sort_values()
                expected = pd.date_range(ordered.iloc[0], periods=expected_hours, freq="h", tz="UTC")
                actual = pd.DatetimeIndex(ordered)
                if not actual.equals(expected):
                    report.errors.append(f"group {key!r} does not contain a continuous hourly window")

    report.valid = not report.errors
    return report


def validate_file(
    path: str | Path,
    contract: str,
    *,
    expected_hours: int | None = None,
) -> ValidationReport:
    df = read_table(path)
    return validate_dataframe(df, contract, expected_hours=expected_hours)
