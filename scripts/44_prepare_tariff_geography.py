#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, shutil, sys, unicodedata
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.common.io import write_table, write_json
from motor_tarifa.base_tariff.parser import prepare_tariffs


def norm_text(v:str)->str:
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().casefold().strip()
    return ' '.join(s.split())

def cnpj_digits(v)->str:
    d=re.sub(r'\D','',str(v or ''))
    return d.zfill(14) if d else ''

def main():
    p=argparse.ArgumentParser(description='Prepara mapa real das áreas de concessão e catálogo tarifário ANEEL ligados por CNPJ.')
    p.add_argument('--tariffs',default='references/tarifas_homologadas_distribuidoras_energia_eletrica.csv.gz')
    p.add_argument('--areas',default='configs/distributor_areas_wgs84.geojson',help='GeoJSON já em EPSG:4326. O projeto inclui conversão do SIGEL/ANEEL SIRGAS 2000.')
    p.add_argument('--areas-catalog',default='configs/distributor_catalog.csv')
    p.add_argument('--base-output',default='data/processed/tariff/base_tariffs.parquet')
    p.add_argument('--catalog-output',default='data/processed/tariff/distributor_catalog.csv')
    p.add_argument('--geo-output',default='data/processed/tariff/distributor_areas_wgs84.geojson')
    p.add_argument('--skipped-output',default='outputs/reports/tariff_non_volumetric_rows.csv')
    p.add_argument('--report',default='outputs/reports/tariff_geography_prepare.json')
    a=p.parse_args()

    tariff_path=Path(a.tariffs)
    if not tariff_path.exists(): raise SystemExit(f'Tariff source not found: {tariff_path}')
    raw=pd.read_csv(tariff_path,sep=';',encoding='utf-8',compression='infer',dtype=str,low_memory=False)
    required={'NumCNPJDistribuidora','DscBaseTarifaria','DscUnidadeTerciaria','SigAgente'}
    missing=required-set(raw.columns)
    if missing: raise SystemExit(f'ANEEL tariff CSV missing columns: {sorted(missing)}')

    # Produto usa tarifa regulatória efetivamente aplicada, não "Base Econômica".
    basis=raw['DscBaseTarifaria'].map(norm_text)
    unit=raw['DscUnidadeTerciaria'].fillna('').str.upper().str.replace(' ','',regex=False)
    applicable=basis.eq('tarifa de aplicacao')
    volumetric=unit.str.contains('MWH|KWH',regex=True)
    selected=raw.loc[applicable & volumetric].copy()
    base,skipped=prepare_tariffs(selected)
    # Since selected was volumetric, skipped normally empty; keep report contract anyway.
    Path(a.base_output).parent.mkdir(parents=True,exist_ok=True)
    write_table(base,a.base_output)
    write_table(skipped,a.skipped_output)

    cat=pd.read_csv(a.areas_catalog,dtype={'cnpj_digits':str})
    cat['cnpj_digits']=cat['cnpj_digits'].map(cnpj_digits)
    base['distributor_cnpj']=base['distributor_cnpj'].map(cnpj_digits)
    agg=(base.groupby('distributor_cnpj',dropna=False)
         .agg(tariff_rows=('tariff_profile_id','size'),tariff_agent_names=('distributor_id',lambda s:' | '.join(sorted(set(map(str,s))))),
              tariff_valid_from=('valid_from','min'),tariff_valid_to=('valid_to','max'))
         .reset_index())
    merged=cat.merge(agg,left_on='cnpj_digits',right_on='distributor_cnpj',how='left')
    merged['has_tariff_history']=merged['tariff_rows'].fillna(0).astype(int).gt(0)
    merged['tariff_rows']=merged['tariff_rows'].fillna(0).astype(int)
    merged.drop(columns=['distributor_cnpj'],inplace=True,errors='ignore')
    write_table(merged,a.catalog_output)

    geo_src=Path(a.areas);geo_dst=Path(a.geo_output);geo_dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(geo_src,geo_dst)
    matched=int(merged['has_tariff_history'].sum())
    report={
        'tariff_source':str(tariff_path),'raw_rows':int(len(raw)),'tariff_application_volumetric_rows':int(len(selected)),
        'normalized_base_rows':int(len(base)),'geo_areas':int(len(merged)),'geo_areas_with_tariff_history':matched,
        'geo_match_rate':matched/max(1,len(merged)),'unique_tariff_cnpj':int(base.distributor_cnpj.nunique()),
        'base_output':a.base_output,'catalog_output':a.catalog_output,'geo_output':a.geo_output,
        'join_key':'CNPJ digits: GeoJSON cnpj ↔ ANEEL NumCNPJDistribuidora',
        'product_scope':'TE+TUSD volumétricas, Tarifa de Aplicação. R$/kW e demais componentes da fatura permanecem fora do preço volumétrico mostrado.',
    }
    write_json(report,a.report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
