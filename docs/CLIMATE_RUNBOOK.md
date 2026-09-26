# Runbook — primeiro smoke test climático

## Opção A — validar sem internet

```bash
python scripts/02_ingest_climate_snapshot.py tests/fixtures/openmeteo_hourly_example.json
python scripts/03_prepare_climate.py --run-id fixture-smoke
```

O resultado ficará em:

```text
data/processed/climate/climate_hourly/run_id=fixture-smoke/year=2026/month=09/
```

## Opção B — baixar um pequeno período ERA5-Land

```bash
python scripts/02_download_era5_land.py \
  --lat -22.90 \
  --lon -43.20 \
  --start-date 2025-09-01 \
  --end-date 2025-09-07

python scripts/03_prepare_climate.py --run-id era5-smoke
```

O downloader fixa `model=era5_land`, `timezone=GMT` e resolução temporal horária. As coordenadas retornadas pela fonte são usadas para calcular `cell_id`, pois a fonte pode ajustar o ponto solicitado para sua grade.

## Verificação rápida

```bash
python - <<'PYCODE'
from pathlib import Path
import pandas as pd
files = list(Path('data/processed/climate/climate_hourly/run_id=era5-smoke').rglob('*.parquet'))
print(files)
df = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
print(df.head())
print(df.dtypes)
PYCODE
```

## Não fazer ainda

- não baixar dez anos do Brasil inteiro;
- não calcular incidentes antes do baseline;
- não misturar forecast futuro com ERA5-Land observado em backtest operacional;
- não distribuir carga ONS artificialmente nas células de 0,1°.
