# Runbook — Fase 3 / baseline climático

## 1. Smoke test determinístico sem internet

Gere um dataset horário sintético de uma única célula, cobrindo 2016–2026:

```bash
python scripts/04_generate_baseline_smoke_data.py
```

O script imprime o `cell_id` criado. Os dados são exclusivamente para teste de pipeline.

Construa o baseline 2016–2025 para o ano-alvo 2026, usando apenas temperatura:

```bash
python scripts/04_build_climate_baseline.py \
  --input-run-id baseline-fixture \
  --target-year 2026 \
  --variable temperature_2m \
  --run-id baseline-smoke
```

Saídas esperadas:

```text
data/processed/climate/baseline_10y/run_id=baseline-smoke/target_year=2026/variable=temperature_2m/
data/processed/climate/anomalies_hourly/run_id=baseline-smoke/target_year=2026/variable=temperature_2m/
outputs/reports/climate_baseline_baseline-smoke.json
```

Para uma série completa, `coverage_ratio` deve ficar próxima de `1.0`.

## 2. Usar dados ERA5-Land normalizados reais

A Fase 3 não baixa dados. Ela consome o contrato produzido pela Fase 2.

Depois de possuir 2016–2026 para o mesmo conjunto de células:

```bash
python scripts/04_build_climate_baseline.py \
  --input-run-id <RUN_NORMALIZADO> \
  --target-year 2026 \
  --variable temperature_2m \
  --cell-id <CELL_ID> \
  --run-id era5-baseline-2026
```

Para todas as cinco variáveis, omita `--variable`.

## 3. Verificação rápida

```bash
python - <<'PYCODE'
from pathlib import Path
import pandas as pd

files = list(Path(
    'data/processed/climate/baseline_10y/'
    'run_id=baseline-smoke/target_year=2026/variable=temperature_2m'
).glob('*.parquet'))

df = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
print(df.head())
print(df[['sample_count', 'expected_sample_count', 'coverage_ratio']].describe())
PYCODE
```

## 4. Histórico parcial

Por padrão, ausência de qualquer um dos dez anos anteriores para uma célula interrompe a execução. Para depuração estrutural apenas:

```bash
python scripts/04_build_climate_baseline.py \
  --target-year 2026 \
  --allow-partial-history \
  --run-id partial-debug
```

Não use um baseline parcial como baseline científico final do produto.

## 5. Escopo

A Fase 3 mantém deliberadamente um guardrail de 25 células. Isso segue a ordem do plano: validar primeiro, escalar depois.

Para um teste maior já deliberado:

```bash
python scripts/04_build_climate_baseline.py \
  --target-year 2026 \
  --max-cells 100 \
  --run-id larger-test
```

`--max-cells 0` desabilita o guardrail, mas não é recomendado antes de medir memória, I/O e tamanho dos artefatos.
