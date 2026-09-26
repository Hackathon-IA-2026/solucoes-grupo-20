from __future__ import annotations

import pandas as pd


def _lower_map(df: pd.DataFrame) -> dict[str,str]:
    return {str(c).strip().lower():c for c in df.columns}


def _pick(cols:dict[str,str],*names:str)->str|None:
    for n in names:
        if n.lower() in cols:return cols[n.lower()]
    return None


def _numeric(series:pd.Series)->pd.Series:
    if pd.api.types.is_numeric_dtype(series):return pd.to_numeric(series,errors='raise')
    s=series.astype(str).str.strip();comma=s.str.contains(',',regex=False)
    s.loc[comma]=s.loc[comma].str.replace('.','',regex=False).str.replace(',','.',regex=False)
    return pd.to_numeric(s,errors='raise')


def _cnpj_digits(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(r'\D','',regex=True).str.zfill(14)


def _normalize_post(series: pd.Series) -> pd.Series:
    raw = series.astype(str).str.strip()
    norm = raw.str.upper().str.replace('Ã', 'A', regex=False)
    unique_mask = norm.isin({'', 'NAN', 'NA', 'N/A', 'NAO SE APLICA', 'NÃO SE APLICA', 'UNICA', 'ÚNICA', 'UNIQUE'})
    return raw.mask(unique_mask, 'UNIQUE')


def _date_or_default(series: pd.Series | None, index: pd.Index, default: str, *, dayfirst: bool = True) -> pd.Series:
    if series is None:
        return pd.Series(default, index=index)
    raw = series.astype(str).str.strip()
    # ANEEL's current open-data CSV uses ISO YYYY-MM-DD, while some historical
    # exports/fixtures use DD/MM/YYYY. Applying dayfirst=True blindly to ISO
    # values swaps month/day (and can turn dates >12 into NaT). Parse the two
    # contracts explicitly and only then use a conservative fallback.
    iso = raw.str.match(r'^\d{4}-\d{2}-\d{2}(?:$|[ T])', na=False)
    parsed = pd.Series(pd.NaT, index=index, dtype='datetime64[ns]')
    if iso.any():
        parsed.loc[iso] = pd.to_datetime(raw.loc[iso].str.slice(0, 10), format='%Y-%m-%d', errors='coerce')
    other = ~iso
    if other.any():
        parsed.loc[other] = pd.to_datetime(raw.loc[other], errors='coerce', dayfirst=dayfirst)
    out = parsed.dt.strftime('%Y-%m-%d')
    return out.fillna(default)


def prepare_tariffs(df:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame]:
    """Normalize volumetric TE/TUSD tariff rows.

    Supports the current ANEEL open-data field names and a canonical Predicta table.
    R$/MWh is converted to R$/kWh. Demand rows such as R$/kW are returned in `skipped`
    and are never added to volumetric energy tariffs.
    """
    if {'distributor_id','tariff_profile_id','base_te_rs_kwh','base_tusd_rs_kwh'}.issubset(df.columns):
        out=df.copy()
        for c in ['base_te_rs_kwh','base_tusd_rs_kwh']:out[c]=_numeric(out[c])
        if 'base_total_rs_kwh' not in out:out['base_total_rs_kwh']=out.base_te_rs_kwh+out.base_tusd_rs_kwh
        if 'tariff_post' not in out: out['tariff_post']='UNIQUE'
        out['tariff_post'] = _normalize_post(out['tariff_post'])
        if 'valid_from' not in out: out['valid_from']='1900-01-01'
        if 'valid_to' not in out: out['valid_to']='2100-12-31'
        out['valid_from'] = _date_or_default(out['valid_from'], out.index, '1900-01-01')
        out['valid_to'] = _date_or_default(out['valid_to'], out.index, '2100-12-31')
        if 'source' not in out: out['source']='canonical'
        return out.reset_index(drop=True), pd.DataFrame(columns=df.columns)
    cols=_lower_map(df)
    dist=_pick(cols,'distributor_id','sigagente','nomagente','distribuidora','agente')
    te=_pick(cols,'vlrte','te','valor_te')
    tusd=_pick(cols,'vlrtusd','tusd','valor_tusd')
    unit=_pick(cols,'unidade','unid','dsc_unidade','unidademedida','dscunidadeterciaria')
    if not all([dist,te,tusd,unit]):raise ValueError('tariff source must provide distributor, TE, TUSD and unit fields')
    work=df.copy();unit_text=work[unit].astype(str).str.replace(' ','',regex=False).str.upper()
    energy=unit_text.isin({'MWH','R$/MWH','R$MWH'})
    energy_kwh=unit_text.isin({'KWH','R$/KWH','R$KWH'})
    skipped=work.loc[~(energy|energy_kwh)].copy()
    work=work.loc[energy|energy_kwh].copy();factor=pd.Series(1.0,index=work.index);factor.loc[energy.loc[work.index]]=1/1000
    def optional(*names,default=''):
        c=_pick(cols,*names);return work[c].astype(str) if c else pd.Series(default,index=work.index)
    profile_parts=[
        optional('subgrupo','dscsubgrupo'),
        optional('modalidade','modalidadetarifaria','dscmodalidadetarifaria'),
        optional('classe','dscclasse'),
        optional('subclasse','dscsubclasse'),
        optional('detalhe','dscdetalhe'),
        optional('base_tarifaria','dscbasetarifaria'),
    ]
    profile=pd.concat(profile_parts,axis=1).apply(lambda r:'|'.join(x.strip() for x in r if str(x).strip() and str(x).lower() not in {'nan','não se aplica','nao se aplica'}) or 'PROFILE',axis=1)
    post_col=_pick(cols,'postotarifario','posto','dscpostotarifario','nompostotarifario')
    valid_from_col=_pick(cols,'datiniciovigencia','valid_from','inicio_vigencia')
    valid_to_col=_pick(cols,'datfimvigencia','valid_to','fim_vigencia')
    post = _normalize_post(work[post_col]) if post_col else pd.Series('UNIQUE', index=work.index)
    cnpj_col=_pick(cols,'NumCNPJDistribuidora','cnpj','cnpj_distribuidora','distributor_cnpj')
    basis_col=_pick(cols,'DscBaseTarifaria','base_tarifaria','tariff_basis')
    subgrupo_col=_pick(cols,'DscSubGrupo','subgrupo')
    modalidade_col=_pick(cols,'DscModalidadeTarifaria','modalidade','modalidadetarifaria')
    classe_col=_pick(cols,'DscClasse','classe')
    subclasse_col=_pick(cols,'DscSubClasse','subclasse')
    detalhe_col=_pick(cols,'DscDetalhe','detalhe')
    out=pd.DataFrame({
        'distributor_id':work[dist].astype(str).str.strip(),
        'distributor_cnpj':_cnpj_digits(work[cnpj_col]) if cnpj_col else pd.Series('',index=work.index),
        'tariff_profile_id':profile,
        'tariff_post':post,
        'tariff_basis':work[basis_col].astype(str).str.strip() if basis_col else pd.Series('',index=work.index),
        'subgroup':work[subgrupo_col].astype(str).str.strip() if subgrupo_col else pd.Series('',index=work.index),
        'modality':work[modalidade_col].astype(str).str.strip() if modalidade_col else pd.Series('',index=work.index),
        'customer_class':work[classe_col].astype(str).str.strip() if classe_col else pd.Series('',index=work.index),
        'customer_subclass':work[subclasse_col].astype(str).str.strip() if subclasse_col else pd.Series('',index=work.index),
        'detail':work[detalhe_col].astype(str).str.strip() if detalhe_col else pd.Series('',index=work.index),
        'base_te_rs_kwh':_numeric(work[te])*factor,
        'base_tusd_rs_kwh':_numeric(work[tusd])*factor,
        'valid_from':_date_or_default(work[valid_from_col] if valid_from_col else None, work.index, '1900-01-01'),
        'valid_to':_date_or_default(work[valid_to_col] if valid_to_col else None, work.index, '2100-12-31'),
        'source':'ANEEL_TARIFAS_HOMOLOGADAS',
    })
    out['base_total_rs_kwh']=out.base_te_rs_kwh+out.base_tusd_rs_kwh
    def _label(r):
        vals=[r.get('subgroup',''),r.get('modality',''),r.get('customer_class',''),r.get('customer_subclass',''),r.get('detail','')]
        vals=[str(v).strip() for v in vals if str(v).strip() and str(v).strip().lower() not in {'nan','não se aplica','nao se aplica'}]
        return ' · '.join(dict.fromkeys(vals)) if vals else str(r.get('tariff_profile_id','PROFILE'))
    out['profile_label']=out.apply(_label,axis=1)
    return out.reset_index(drop=True),skipped.reset_index(drop=True)
