from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from motor_sin.climate.parser import OUTPUT_COLUMNS, parse_openmeteo_file
from motor_sin.climate.quality import build_climate_quality_report


def _safe_run_id(run_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in run_id)
    if not cleaned:
        raise ValueError("run_id must contain at least one safe character")
    return cleaned



# PREDICTA_CANONICAL_POINT_CELL_PATCH_V1
def _predicta_apply_canonical_point_cell_ids(frame):
    """
    Re-attach the canonical Predicta cell_id from the active points CSV.

    Historical providers may snap coordinates internally. The RAW filename
    retains the coordinate requested by Predicta. That requested coordinate
    is matched back to climate_points_*_01deg.csv, making the points file
    authoritative for spatial identity.
    """
    import os as _os
    import re as _re
    import pandas as _pd
    from pathlib import Path as _Path

    _points_path = _os.environ.get("PREDICTA_CLIMATE_POINTS_FILE", "").strip()
    if not _points_path or frame is None or getattr(frame, "empty", True):
        return frame
    if "raw_file" not in frame.columns or "cell_id" not in frame.columns:
        return frame

    _p = _Path(_points_path)
    if not _p.exists():
        return frame

    _pts = _pd.read_csv(_p)
    _rename = {}
    for _target, _candidates in {
        "latitude": ("latitude", "lat", "lat_center", "grid_lat"),
        "longitude": ("longitude", "lon", "lng", "lon_center", "grid_lon"),
        "cell_id": ("cell_id", "grid_cell_id", "point_id"),
    }.items():
        for _candidate in _candidates:
            if _candidate in _pts.columns:
                _rename[_candidate] = _target
                break
    _pts = _pts.rename(columns=_rename)

    if not {"latitude", "longitude", "cell_id"}.issubset(_pts.columns):
        return frame

    def _key(_lat, _lon):
        return (round(float(_lat), 4), round(float(_lon), 4))

    _coord_to_cell = {}
    for _row in _pts[["latitude", "longitude", "cell_id"]].itertuples(index=False):
        _coord_to_cell[_key(_row.latitude, _row.longitude)] = str(_row.cell_id)

    _rx = _re.compile(
        r"(?P<lat>-?\d+_\d{4})_(?P<lon>-?\d+_\d{4})_"
        r"\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}"
    )

    _raw_to_cell = {}
    for _raw in frame["raw_file"].dropna().astype(str).unique():
        _name = _Path(_raw).name
        _m = _rx.search(_name)
        if not _m:
            continue
        try:
            _lat = float(_m.group("lat").replace("_", "."))
            _lon = float(_m.group("lon").replace("_", "."))
        except ValueError:
            continue
        _cell = _coord_to_cell.get(_key(_lat, _lon))
        if _cell is not None:
            _raw_to_cell[_raw] = _cell

    if not _raw_to_cell:
        return frame

    _mapped = frame["raw_file"].astype(str).map(_raw_to_cell)
    _mask = _mapped.notna()
    if _mask.any():
        frame = frame.copy()
        frame.loc[_mask, "cell_id"] = _mapped.loc[_mask].astype(str).values

    return frame

def prepare_climate_dataset(
    raw_files: Iterable[str | Path],
    *,
    output_root: str | Path,
    report_path: str | Path,
    run_id: str,
    strict_duplicates: bool = True,
) -> dict:
    files = sorted(Path(p) for p in raw_files)
    if not files:
        raise ValueError("no RAW climate files supplied")

    frames = [parse_openmeteo_file(path) for path in files]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = df.sort_values(["interval_start_utc", "cell_id", "raw_file"], kind="stable").reset_index(drop=True)

    # Canonical spatial identity comes from the active Predicta points file.
    df = _predicta_apply_canonical_point_cell_ids(df)
    duplicate_mask = df.duplicated(["interval_start_utc", "cell_id"], keep=False)
    if strict_duplicates and duplicate_mask.any():
        sample = df.loc[duplicate_mask, ["interval_start_utc", "cell_id", "raw_file"]].head(10)
        raise ValueError(
            "duplicate cell/hour observations across RAW files; resolve source overlap before preparing dataset. "
            f"sample={sample.to_dict(orient='records')}"
        )

    run_id_safe = _safe_run_id(run_id)
    run_root = Path(output_root) / f"run_id={run_id_safe}"
    artifacts: list[str] = []
    grouped = df.groupby(
        [df["interval_start_utc"].dt.year, df["interval_start_utc"].dt.month],
        sort=True,
    )
    for (year, month), group in grouped:
        partition = run_root / f"year={int(year):04d}" / f"month={int(month):02d}"
        partition.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(
            pd.util.hash_pandas_object(group[OUTPUT_COLUMNS], index=False).values.tobytes()
        ).hexdigest()[:16]
        path = partition / f"part-{digest}.parquet"
        if not path.exists():
            group[OUTPUT_COLUMNS].to_parquet(path, index=False)
        artifacts.append(str(path))

    report = build_climate_quality_report(
        df,
        run_id=run_id_safe,
        source_files=[str(p) for p in files],
        rows_read=sum(len(frame) for frame in frames),
    )
    report["artifacts"] = artifacts
    report["dataset_root"] = str(run_root)
    report["partitioning"] = ["run_id", "year", "month"]
    report["canonical_units"] = {
        "temperature_2m": "degC",
        "dewpoint_2m": "degC",
        "precipitation": "mm",
        "wind_speed_10m": "m/s",
        "solar_radiation": "W/m2",
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
