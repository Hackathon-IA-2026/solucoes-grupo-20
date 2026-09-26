from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

GENERATION_ALIASES: dict[str, tuple[str, ...]] = {
    'interval_start_utc': ('interval_start_utc','din_instante','din_referenciautc','data_hora','timestamp'),
    'plant_id': ('plant_id','id_ons','id_usina','id_empreendimento','ceg','cod_empreendimento'),
    'plant_name': ('plant_name','nom_usina','nome_usina','nom_empreendimento','empreendimento'),
    'generation_type': ('generation_type','nom_tipousina','tipo_usina','fonte','tipogeracao'),
    'subsystem_id': ('subsystem_id','id_subsistema','nom_subsistema','subsistema'),
    'state': ('state','id_estado','uf','estado'),
    'generation_mw': ('generation_mw','val_geracao','geracao_mw','valor_geracao'),
}

KNOWN_TYPES = {'EOLIELÉTRICA','EOLICA','FOTOVOLTAICA','HIDROELÉTRICA','HIDRELETRICA','NUCLEAR','TÉRMICA','TERMICA'}


def _first(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def normalize_generation(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    mapping: dict[str, str] = {}
    for canonical, aliases in GENERATION_ALIASES.items():
        found = _first(df, aliases)
        if found is None:
            raise ValueError(f'generation source missing field for {canonical}; accepted={aliases}')
        mapping[found] = canonical
    out = df.rename(columns=mapping)[list(GENERATION_ALIASES)].copy()
    out['interval_start_utc'] = pd.to_datetime(out['interval_start_utc'], utc=True, errors='raise').dt.floor('h')
    out['plant_id'] = out['plant_id'].astype(str).str.strip()
    out['plant_name'] = out['plant_name'].astype(str).str.strip()
    out['generation_type'] = out['generation_type'].astype(str).str.strip().str.upper()
    out['subsystem_id'] = out['subsystem_id'].astype(str).str.strip().str.upper().replace({'SE':'SE/CO','SECO':'SE/CO','SUDESTE/CENTRO-OESTE':'SE/CO'})
    out['state'] = out['state'].astype(str).str.strip().str.upper()
    out['generation_mw'] = pd.to_numeric(out['generation_mw'], errors='coerce')
    negative = out['generation_mw'].lt(0)
    if negative.any():
        # Preserve source values; quality layer flags them rather than silently clipping.
        out['quality_flag_negative_generation'] = negative
    else:
        out['quality_flag_negative_generation'] = False
    out['source'] = 'ONS_GENERATION'
    unknown = sorted(set(out['generation_type'].dropna()) - KNOWN_TYPES)
    return out, unknown
