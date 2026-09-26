from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd
from .arco import ArcoClient, CORE_GROUPS, expected_hours_for_year
from .quality import validate_year_file, write_quality_report

GROUP_OUTPUT_COLUMNS = {
    "temperature": ("temperature_2m_c", "dewpoint_2m_c"),
    "precipitation": ("precipitation_mm",),
    "wind": ("wind_u_10m_ms", "wind_v_10m_ms", "wind_speed_10m_ms"),
    "radiation": ("solar_radiation_j_m2", "solar_radiation_w_m2_avg"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def required_columns_for_groups(groups: Sequence[str]) -> list[str]:
    cols: list[str] = []
    for group in groups:
        cols.extend(GROUP_OUTPUT_COLUMNS[group])
    return cols


def points_fingerprint(points: pd.DataFrame) -> str:
    cols = ["cell_id", "subsystem", "latitude", "longitude"]
    stable = points[cols].copy().sort_values("cell_id").reset_index(drop=True)
    payload = stable.to_csv(index=False, float_format="%.6f").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def manifest_path(parquet_path: Path) -> Path:
    return parquet_path.with_suffix(".manifest.json")


def quality_path(parquet_path: Path) -> Path:
    return parquet_path.with_suffix(".quality.json")


def partial_dir(parquet_path: Path) -> Path:
    return parquet_path.parent / f".{parquet_path.stem}.partial"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_year_complete(
    parquet_path: Path,
    *,
    year: int,
    groups: Sequence[str],
    points: pd.DataFrame,
) -> bool:
    """Fast resume check using the validated manifest/quality pair.

    The final Parquet is not trusted by existence alone. We require the same
    point set, same variable groups and a previous complete quality report.
    """
    mp = manifest_path(parquet_path)
    qp = quality_path(parquet_path)
    if not parquet_path.exists() or not mp.exists() or not qp.exists():
        return False
    manifest = _read_json(mp)
    quality = _read_json(qp)
    if not manifest or not quality:
        return False
    return (
        manifest.get("status") == "complete"
        and quality.get("status") == "complete"
        and sorted(manifest.get("groups", [])) == sorted(groups)
        and manifest.get("points_fingerprint") == points_fingerprint(points)
        and int(manifest.get("point_count", -1)) == len(points)
        and int(quality.get("hours_per_cell_expected", -1)) == expected_hours_for_year(year)
    )


def _batch_valid(path: Path, *, year: int, batch: pd.DataFrame, groups: Sequence[str]) -> bool:
    import pyarrow.parquet as pq
    if not path.exists():
        return False
    try:
        pf = pq.ParquetFile(path)
        expected_rows = expected_hours_for_year(year) * len(batch)
        if pf.metadata.num_rows != expected_rows:
            return False
        names = set(pf.schema_arrow.names)
        required = {"time_utc", "cell_id", "subsystem", "latitude", "longitude"}
        required.update(required_columns_for_groups(groups))
        if not required.issubset(names):
            return False
        ids = pd.read_parquet(path, columns=["cell_id"])["cell_id"].astype(str)
        return set(ids.unique()) == set(batch["cell_id"].astype(str))
    except Exception:
        return False


def _fetch_with_retry(
    client: ArcoClient,
    points: pd.DataFrame,
    year: int,
    groups: Sequence[str],
    max_retries: int,
) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return client.fetch_batch(points=points, year=year, groups=groups)
        except Exception as exc:  # network/Zarr errors vary by backend
            last_error = exc
            if attempt == max_retries:
                break
            wait = min(60, 2**attempt)
            print(f"    tentativa {attempt} falhou: {exc}; retry em {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Falha ARCO após {max_retries} tentativas") from last_error


def _write_partial_state(
    state_path: Path,
    *,
    subsystem: str,
    year: int,
    groups: Sequence[str],
    point_count: int,
    batch_size: int,
    fingerprint: str,
    completed_batches: list[int],
    started_at_utc: str | None = None,
) -> None:
    payload = {
        "schema_version": "1.1",
        "backend": "arco_geo_chunked_zarr",
        "subsystem": subsystem,
        "year": year,
        "groups": list(groups),
        "point_count": point_count,
        "point_batch_size": batch_size,
        "points_fingerprint": fingerprint,
        "completed_batches": completed_batches,
        "started_at_utc": started_at_utc,
        "updated_at_utc": utc_now(),
        "status": "partial",
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _partial_state_matches(
    state: dict | None,
    *,
    groups: Sequence[str],
    point_count: int,
    batch_size: int,
    fingerprint: str,
) -> bool:
    if not state:
        return False
    return (
        sorted(state.get("groups", [])) == sorted(groups)
        and int(state.get("point_count", -1)) == point_count
        and int(state.get("point_batch_size", -1)) == batch_size
        and state.get("points_fingerprint") == fingerprint
    )


def materialize_year(
    *,
    client: ArcoClient,
    points: pd.DataFrame,
    subsystem: str,
    year: int,
    groups: Sequence[str] = CORE_GROUPS,
    output_root: Path,
    batch_size: int = 32,
    max_retries: int = 3,
    force: bool = False,
) -> dict:
    """Materialize one subsystem/year with true batch-level resume.

    Completed batch Parquets are kept in a hidden partial directory until the
    final annual Parquet passes validation. A rerun reuses valid batches.
    """
    groups = tuple(groups)
    out_dir = output_root / subsystem.lower() / "hourly"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{year}.parquet"
    mp = manifest_path(out_path)
    qp = quality_path(out_path)
    pdir = partial_dir(out_path)
    state_path = pdir / "state.json"
    fingerprint = points_fingerprint(points)

    if not force and is_year_complete(
        out_path, year=year, groups=groups, points=points
    ):
        print(f"SKIP {subsystem} {year}: já validado como completo")
        return _read_json(mp) or {"status": "complete", "year": year}

    if force:
        for path in (out_path, mp, qp):
            path.unlink(missing_ok=True)
        shutil.rmtree(pdir, ignore_errors=True)

    pdir.mkdir(parents=True, exist_ok=True)
    state = _read_json(state_path)
    if not _partial_state_matches(
        state,
        groups=groups,
        point_count=len(points),
        batch_size=batch_size,
        fingerprint=fingerprint,
    ):
        # Point list/config changed: stale fragments must never be reused.
        shutil.rmtree(pdir, ignore_errors=True)
        pdir.mkdir(parents=True, exist_ok=True)
        state = None

    started = (state or {}).get("started_at_utc") or utc_now()
    completed_batches: list[int] = []
    total_batches = (len(points) + batch_size - 1) // batch_size

    try:
        for batch_idx, start in enumerate(range(0, len(points), batch_size)):
            batch = points.iloc[start : start + batch_size].copy()
            part_path = pdir / f"part-{batch_idx:05d}.parquet"
            if _batch_valid(part_path, year=year, batch=batch, groups=groups):
                print(
                    f"  RESUME {subsystem} {year}: lote {batch_idx + 1}/{total_batches} já completo"
                )
                completed_batches.append(batch_idx)
                continue

            print(
                f"  {subsystem} {year}: lote {batch_idx + 1}/{total_batches} "
                f"(pontos {start + 1}-{start + len(batch)} / {len(points)})"
            )
            frame = _fetch_with_retry(client, batch, year, groups, max_retries)
            temp_part = part_path.with_suffix(".parquet.tmp")
            frame.to_parquet(temp_part, index=False, compression="zstd")
            os.replace(temp_part, part_path)
            if not _batch_valid(part_path, year=year, batch=batch, groups=groups):
                raise RuntimeError(f"Lote {batch_idx} falhou na validação local: {part_path}")
            completed_batches.append(batch_idx)
            _write_partial_state(
                state_path,
                subsystem=subsystem,
                year=year,
                groups=groups,
                point_count=len(points),
                batch_size=batch_size,
                fingerprint=fingerprint,
                completed_batches=completed_batches,
                started_at_utc=started,
            )

        if len(completed_batches) != total_batches:
            raise RuntimeError(
                f"Ano {year}: apenas {len(completed_batches)}/{total_batches} lotes completos."
            )

        final_tmp = out_path.with_suffix(".parquet.partial")
        final_tmp.unlink(missing_ok=True)
        import pyarrow.parquet as pq

        writer = None
        try:
            for batch_idx in range(total_batches):
                part_path = pdir / f"part-{batch_idx:05d}.parquet"
                table = pq.read_table(part_path)
                if writer is None:
                    writer = pq.ParquetWriter(
                        final_tmp,
                        table.schema,
                        compression="zstd",
                        use_dictionary=["cell_id", "subsystem"],
                    )
                writer.write_table(table)
            if writer is None:
                raise RuntimeError("Nenhum lote disponível para consolidação.")
        finally:
            if writer is not None:
                writer.close()

        required = required_columns_for_groups(groups)
        quality = validate_year_file(
            final_tmp,
            year,
            expected_cells=len(points),
            required_columns=required,
        )
        if quality["status"] != "complete":
            raise RuntimeError(
                f"Ano {year} não passou na validação final: {quality.get('reasons', [])}"
            )

        os.replace(final_tmp, out_path)
        quality["path"] = str(out_path)
        write_quality_report(quality, qp)
        manifest = {
            "schema_version": "1.1",
            "source": "Copernicus/ECMWF ERA5-Land ARCO",
            "backend": "arco_geo_chunked_zarr",
            "subsystem": subsystem,
            "year": year,
            "groups": list(groups),
            "point_count": len(points),
            "point_batch_size": batch_size,
            "batches": total_batches,
            "rows_written": int(quality["rows"]),
            "points_fingerprint": fingerprint,
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "quality_report": str(qp),
            "status": "complete",
            "core_complete": set(groups) == set(CORE_GROUPS),
        }
        mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.rmtree(pdir, ignore_errors=True)
        print(f"DONE {subsystem} {year}: complete -> {out_path}")
        return manifest
    except Exception as exc:
        failed = {
            "schema_version": "1.1",
            "backend": "arco_geo_chunked_zarr",
            "subsystem": subsystem,
            "year": year,
            "groups": list(groups),
            "point_count": len(points),
            "point_batch_size": batch_size,
            "points_fingerprint": fingerprint,
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "status": "partial_or_failed",
            "error": str(exc),
            "resume_dir": str(pdir),
        }
        mp.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
