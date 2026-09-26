from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

ANEEL_TARIFF_RESOURCE_ID = 'fcf2906c-7c32-4b9b-a637-054e7a5234f4'
ANEEL_TARIFF_CSV_URL = (
    'https://dadosabertos.aneel.gov.br/dataset/5a583f3e-1646-4f67-bf0f-69db4203e89e/'
    'resource/fcf2906c-7c32-4b9b-a637-054e7a5234f4/download/'
    'tarifas-homologadas-distribuidoras-energia-eletrica.csv'
)
ANEEL_DATASTORE = 'https://dadosabertos.aneel.gov.br/api/3/action/datastore_search'


def fetch_tariff_rows(*, distributor: str | None = None, limit: int = 5000, offset: int = 0) -> pd.DataFrame:
    params: dict[str,str|int] = {'resource_id': ANEEL_TARIFF_RESOURCE_ID, 'limit': int(limit), 'offset': int(offset)}
    if distributor:
        params['q'] = distributor
    url = ANEEL_DATASTORE + '?' + urlencode(params)
    req = Request(url, headers={'User-Agent':'Predicta-Hackathon/1.1'})
    with urlopen(req, timeout=120) as r:
        payload = json.load(r)
    if not payload.get('success'):
        raise RuntimeError(f'ANEEL CKAN request failed: {payload}')
    records = payload.get('result', {}).get('records', [])
    df = pd.DataFrame(records)
    if distributor and 'SigAgente' in df:
        mask = df['SigAgente'].astype(str).str.contains(distributor, case=False, regex=False, na=False)
        df = df.loc[mask].copy()
    return df.reset_index(drop=True)
