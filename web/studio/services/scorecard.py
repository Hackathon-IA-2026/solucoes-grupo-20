from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
from django.conf import settings

from motor_sin.common.io import read_table

ROOT = Path(settings.PREDICTA_PROJECT_ROOT)
VAL_DIR = ROOT / 'outputs/metrics/model_validation'

REGION_TAGS = {'N': 'n', 'NE': 'ne', 'S': 's', 'SE/CO': 'seco'}
MODEL_FILES = {'N': 'N_E3.json', 'NE': 'NE_E3.json', 'S': 'S_E3.json', 'SE/CO': 'SE_CO_E3.json'}
POINTS_FILES = {'N': 'e2_n_points.csv', 'NE': 'e2_ne_points.csv', 'S': 'e2_s_points.csv', 'SE/CO': 'e2_seco_points.csv'}
GEN_SUBSYSTEM_ALIAS = {'SECO': 'SE/CO'}
# E1 files use the sanitized subsystem slug produced by script 46.
E1_SLUGS = {'N': 'e1_ridge_n_aligned_20260916', 'NE': 'e1_ridge_ne_aligned_20260916',
            'S': 'e1_ridge_s_aligned_20260916', 'SE/CO': 'e1_ridge_se_co_aligned_20260916'}


def _overall_wape(path: Path, experiment: str) -> float | None:
    if not path.exists():
        return None
    df = read_table(path)
    row = df[(df.experiment.astype(str).eq(experiment)) & (df.segment.eq('ALL')) & (df.horizon.eq('ALL'))]
    return float(row.WAPE.iloc[0]) if len(row) else None


def _model_info(region: str) -> dict:
    path = ROOT / 'models/demand' / MODEL_FILES[region]
    if not path.exists():
        return {'name': f'{region} · E3', 'algorithm': 'ridge', 'features': None}
    data = json.loads(path.read_text(encoding='utf-8'))
    return {
        'name': f'{MODEL_FILES[region].removesuffix(".json")} · Ridge quantílico',
        'algorithm': str(data.get('model_type', 'ridge')),
        'features': len(data.get('features', [])) or None,
    }


def _counts(region: str) -> dict:
    distributors = None
    cat_path = ROOT / 'configs/distributor_catalog.csv'
    if cat_path.exists():
        cat = pd.read_csv(cat_path)
        distributors = int((cat.subsystem_id.astype(str) == region).sum())

    plants = tracked = total_gen_mw = None
    coverage_pct = None
    gen_path = ROOT / 'configs/generation_assets_catalog.json'
    if gen_path.exists():
        g = json.loads(gen_path.read_text(encoding='utf-8'))
        def _match(item):
            sub = str(item.get('subsistema', ''))
            return GEN_SUBSYSTEM_ALIAS.get(sub, sub) == region
        usinas = [u for u in g.get('usinas', []) if _match(u)]
        conjuntos = [c for c in g.get('conjuntos_nomeados', []) if _match(c)]
        plants = len(usinas) + len(conjuntos)
        cobertura = (g.get('metadados', {}).get('cobertura_pct_do_total_real_por_subsistema') or {})
        for key, val in cobertura.items():
            if GEN_SUBSYSTEM_ALIAS.get(str(key), str(key)) == region and isinstance(val, dict):
                coverage_pct = val.get('cobertura_camada1_mais_2_pct')

    cells = None
    pts_path = ROOT / 'configs' / POINTS_FILES[region]
    if pts_path.exists():
        cells = int(len(pd.read_csv(pts_path)))

    return {'distributors': distributors, 'plants_tracked': plants, 'plant_coverage_pct': coverage_pct, 'climate_cells': cells}


@lru_cache(maxsize=8)
def subsystem_scorecard(region: str) -> dict | None:
    """Consolidated per-subsystem quality + traceability card (hackathon evidence)."""
    if region not in REGION_TAGS:
        return None
    tag = REGION_TAGS[region]
    e3 = _overall_wape(VAL_DIR / f'auto_e3_ridge_{tag}_2023_2026_metrics.csv', 'E3')
    e1_path = VAL_DIR / f'{E1_SLUGS[region]}_metrics.csv'
    e1 = _overall_wape(e1_path, 'E1')
    e0 = _overall_wape(e1_path if e1_path.exists() else VAL_DIR / f'auto_e3_ridge_{tag}_2023_2026_metrics.csv', 'E0_BLEND')
    gain_vs_baseline = 100.0 * (1 - e3 / e0) if e3 and e0 else None
    gain_vs_e1 = 100.0 * (1 - e3 / e1) if e3 and e1 else None
    return {
        'region': region,
        'model': _model_info(region),
        'wape_active_pct': 100 * e3 if e3 is not None else None,
        'wape_baseline_pct': 100 * e0 if e0 is not None else None,
        'wape_e1_pct': 100 * e1 if e1 is not None else None,
        'gain_vs_baseline_pct': gain_vs_baseline,
        'gain_climate_pct': gain_vs_e1,
        'holdout_hours': 720,
        **_counts(region),
    }


def all_scorecards() -> list[dict]:
    return [s for r in REGION_TAGS if (s := subsystem_scorecard(r))]
