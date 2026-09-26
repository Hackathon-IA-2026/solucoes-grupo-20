#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import pandas as pd


def _norm_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    cols = {str(c).lower(): str(c) for c in df.columns}
    for c in candidates:
        if c.lower() in cols:
            return cols[c.lower()]
    return None


def _centers_from_grid(grid: pd.DataFrame) -> pd.DataFrame:
    if 'cell_id' not in grid.columns:
        return pd.DataFrame(columns=['cell_id', '_grid_lat', '_grid_lon'])
    latc = _norm_col(grid, ('lat_center','latitude','lat','center_lat'))
    lonc = _norm_col(grid, ('lon_center','longitude','lon','center_lon'))
    out = grid[['cell_id']].copy()
    if latc and lonc:
        out['_grid_lat'] = pd.to_numeric(grid[latc], errors='coerce')
        out['_grid_lon'] = pd.to_numeric(grid[lonc], errors='coerce')
        return out
    lat_min = _norm_col(grid, ('lat_min','min_lat','latitude_min'))
    lat_max = _norm_col(grid, ('lat_max','max_lat','latitude_max'))
    lon_min = _norm_col(grid, ('lon_min','min_lon','longitude_min'))
    lon_max = _norm_col(grid, ('lon_max','max_lon','longitude_max'))
    if all([lat_min, lat_max, lon_min, lon_max]):
        out['_grid_lat'] = (pd.to_numeric(grid[lat_min], errors='coerce') + pd.to_numeric(grid[lat_max], errors='coerce')) / 2.0
        out['_grid_lon'] = (pd.to_numeric(grid[lon_min], errors='coerce') + pd.to_numeric(grid[lon_max], errors='coerce')) / 2.0
        return out
    return pd.DataFrame(columns=['cell_id', '_grid_lat', '_grid_lon'])


def _payload_lat_lon(path: Path) -> tuple[float, float] | None:
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if isinstance(obj, list):
        if len(obj) != 1 or not isinstance(obj[0], dict):
            return None
        obj = obj[0]
    if not isinstance(obj, dict):
        return None
    try:
        return float(obj['latitude']), float(obj['longitude'])
    except Exception:
        return None


def _same_point(a: tuple[float,float], b: tuple[float,float], tol: float = 5e-5) -> bool:
    return abs(a[0]-b[0]) <= tol and abs(a[1]-b[1]) <= tol


def _quarantine_files(root: Path, discarded: list[tuple[float,float]], quarantine: Path) -> int:
    if not root.exists() or not discarded:
        return 0
    moved = 0
    for p in root.rglob('*.json'):
        ll = _payload_lat_lon(p)
        if ll is None or not any(_same_point(ll, d) for d in discarded):
            continue
        rel = p.relative_to(root)
        dest = quarantine / root.name / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite an earlier quarantine copy.
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            n = 1
            while dest.exists():
                dest = dest.with_name(f'{stem}__{n}{suffix}')
                n += 1
        shutil.move(str(p), str(dest))
        moved += 1
    return moved


def main() -> None:
    ap = argparse.ArgumentParser(description='Repair duplicate Predicta climate cells without weakening duplicate-observation validation.')
    ap.add_argument('--points', required=True)
    ap.add_argument('--grid', default='data/processed/grid/brazil_grid_01deg.parquet')
    ap.add_argument('--hourly-dir', required=True)
    ap.add_argument('--daily-dir', required=True)
    ap.add_argument('--quarantine-root', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()

    points_path = Path(a.points)
    if not points_path.exists():
        raise SystemExit(f'points file not found: {points_path}')
    pts = pd.read_csv(points_path)
    required = {'cell_id','latitude','longitude'}
    missing = sorted(required - set(pts.columns))
    if missing:
        raise SystemExit(f'points file missing columns {missing}: {points_path}')

    pts['cell_id'] = pts['cell_id'].astype(str)
    pts['latitude'] = pd.to_numeric(pts['latitude'], errors='raise')
    pts['longitude'] = pd.to_numeric(pts['longitude'], errors='raise')
    dup_mask = pts.duplicated('cell_id', keep=False)

    payload = {
        'points_file': str(points_path),
        'rows_before': int(len(pts)),
        'duplicate_cell_ids': int(pts.loc[dup_mask, 'cell_id'].nunique()),
        'duplicate_rows': int(dup_mask.sum()),
        'discarded_points': [],
        'quarantined_hourly_files': 0,
        'quarantined_daily_files': 0,
        'status': 'NO_DUPLICATES',
    }

    if not dup_mask.any():
        print('CLIMATE_CELL_REPAIR_OK no duplicate cell_id rows; nothing to change')
        if a.report:
            rp = Path(a.report); rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        return

    work = pts.copy()
    work['_row_order'] = range(len(work))
    grid_path = Path(a.grid)
    centers = pd.DataFrame(columns=['cell_id','_grid_lat','_grid_lon'])
    if grid_path.exists():
        try:
            centers = _centers_from_grid(pd.read_parquet(grid_path))
        except Exception as exc:
            print(f'CLIMATE_CELL_REPAIR_WARN could not read grid centers: {type(exc).__name__}: {exc}', flush=True)
    if not centers.empty:
        work = work.merge(centers.drop_duplicates('cell_id'), on='cell_id', how='left')
        work['_distance2'] = (work['latitude']-work['_grid_lat'])**2 + (work['longitude']-work['_grid_lon'])**2
    else:
        work['_distance2'] = math.inf

    # Deterministic choice: nearest point to the canonical cell center; if center
    # metadata is unavailable/tied, preserve the earliest point produced by the grid builder.
    work['_distance2'] = pd.to_numeric(work['_distance2'], errors='coerce').fillna(math.inf)
    order = work.sort_values(['cell_id','_distance2','_row_order'], kind='stable')
    keep_idx = set(order.drop_duplicates('cell_id', keep='first')['_row_order'].astype(int).tolist())
    discarded_df = work[~work['_row_order'].isin(keep_idx)].copy()
    kept = pts.iloc[sorted(keep_idx)].copy().reset_index(drop=True)

    # Back up the exact point definition before mutating it.
    backup = points_path.with_suffix(points_path.suffix + '.pre_collision_repair.bak')
    if not backup.exists():
        shutil.copy2(points_path, backup)
    kept.to_csv(points_path, index=False)

    discarded = [(float(r.latitude), float(r.longitude)) for r in discarded_df.itertuples()]
    payload['discarded_points'] = [
        {'cell_id': str(r.cell_id), 'latitude': float(r.latitude), 'longitude': float(r.longitude)}
        for r in discarded_df.itertuples()
    ]
    quarantine = Path(a.quarantine_root)
    payload['quarantined_hourly_files'] = _quarantine_files(Path(a.hourly_dir), discarded, quarantine)
    payload['quarantined_daily_files'] = _quarantine_files(Path(a.daily_dir), discarded, quarantine)
    payload['rows_after'] = int(len(kept))
    payload['backup'] = str(backup)
    payload['quarantine_root'] = str(quarantine)
    payload['status'] = 'REPAIRED'

    # Hard invariant: the active point definition must now be one row per cell.
    verify = pd.read_csv(points_path)
    if verify['cell_id'].astype(str).duplicated().any():
        raise RuntimeError('repair failed: duplicate cell_id remains in active points file')

    if a.report:
        rp = Path(a.report); rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print('CLIMATE_CELL_REPAIR_OK ' + json.dumps(payload, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
