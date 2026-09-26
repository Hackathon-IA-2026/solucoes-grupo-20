# E3 — anomalias e eventos do snapshot OpenMeteo (v1.3.0)

## Objetivo

E3 mantém o E1 e o E2 congelados e acrescenta apenas o contexto climático histórico/extremo definido no snapshot `OpenMeteo_snapshot_disponivel_2026-09-18.zip`.

A comparação permanece:

```text
E1 = histórico de carga + calendário
E2 = E1 + clima bruto no horário-alvo
E3 = E2 + anomalias diárias + candidatos a eventos extremos
```

O mesmo estimador Ridge, mesmas origens, mesmos horizontes H01–H24 e mesmo holdout são usados para preservar a interpretação incremental.

## O que foi implementado diretamente do snapshot

Arquivo de regras preservado sem alterações:

```text
configs/openmeteo_event_rules_snapshot_2026-08-08.2.json
```

SHA-256 do arquivo coincide com `config/event_rules.json` do snapshot fornecido.

### Baseline térmico

- fonte: Open-Meteo historical;
- modelo: `era5_land`;
- 10 anos completos anteriores ao ano-alvo;
- agrupamento: mês do calendário;
- métricas: `temperature_2m_max` e `temperature_2m_min` diárias;
- estatísticas: `mean`, `p05`, `p10`, `p90`, `p95`;
- método de quantil: interpolação linear `n-1` via NumPy `method="linear"`;
- mínimo: 250 amostras por célula/mês/métrica;
- anomalia: valor diário observado menos média climatológica mensal.

Para alvo 2025:

```text
baseline = 2015–2024
```

### Calor

- `unusually_hot_day`: Tmax >= p90;
- `extreme_heat_day`: Tmax >= p95 e anomalia >= +3 °C;
- `heat_wave_candidate`: Tmax >= p90 e anomalia >= +5 °C por pelo menos 5 dias consecutivos;
- noite quente (Tmin >= p90) é mantida apenas como evidência complementar, conforme o snapshot, e não como condição obrigatória da onda.

O detector diário preserva a regra de maior severidade: um `extreme_heat_day` não é simultaneamente marcado como `unusually_hot_day`.

### Frio

- `unusually_cold_day`: Tmin <= p10;
- `extreme_cold_day`: Tmin <= p05 e anomalia <= -3 °C;
- `cold_wave_candidate`: Tmin <= p10 e anomalia <= -3 °C por pelo menos 3 dias consecutivos.

Também aqui a maior severidade diária prevalece.

### Precipitação

- `heavy_rain_day`: precipitação diária >= 50 mm;
- `extreme_rain_day`: precipitação diária >= 100 mm;
- a faixa extrema prevalece sobre a faixa de chuva intensa.

### Vento

- `strong_wind_day`: rajada máxima diária >= 60 km/h;
- `severe_wind_day`: >= 80 km/h;
- `extreme_wind_day`: >= 100 km/h;
- somente a maior faixa atingida no dia é marcada.

### Tempestade

No backtest histórico, o código meteorológico não é usado, porque a regra do snapshot limita esse caminho ao serviço de forecast. Assim, `storm_candidate` usa:

```text
precipitação diária >= 30 mm
AND
rajada máxima diária >= 60 km/h
```

A própria regra do snapshot declara `simultaneity_confirmed=false`; portanto o E3 trata o resultado como candidato diário, não como confirmação de simultaneidade horária.

## O que NÃO foi inventado

O snapshot fornecido é parcial e informa que `openmeteo_pipeline/baseline.py` não está disponível. Por isso esta implementação não cria um percentil empírico contínuo diário que não esteja especificado no material. O E3 usa somente:

- médias e limiares p05/p10/p90/p95 explicitamente definidos;
- anomalias em relação à média mensal;
- predicados/candidatos a evento que aparecem em `event_rules.json` e no detector disponível.

## Fontes usadas no MVP

O baseline térmico usa `ERA5-Land`, exatamente como a regra fornecida.

Para o ano-alvo:

- temperatura máxima/mínima e rajada máxima diária: `ERA5-Land`;
- precipitação diária: `ERA5`.

A separação é explícita porque as famílias de variáveis disponíveis diferem entre reanálises. Os dados permanecem associados aos oito pontos representativos já usados no E2; isso continua sendo um proxy espacial de MVP, não uma fronteira oficial do subsistema ONS.

## Execução

### 1. Baixar contexto E3

```bash
python scripts/34_download_e3_context.py \
  --load data/processed/demand/load_hourly.parquet \
  --subsystem SE/CO
```

O ano-alvo é inferido da carga. Para o piloto atual, 2025 produz baseline 2015–2024.

### 2. Construir baseline, anomalias e eventos

```bash
python scripts/35_prepare_e3_context.py \
  --subsystem SE/CO \
  --target-year 2025
```

Artefatos:

```text
data/processed/climate/e3_temperature_baseline_monthly.parquet
data/processed/climate/e3_daily_context.parquet
data/processed/climate/e3_zone_context_hourly.parquet
data/processed/climate/zone_climate_hourly_e3.parquet
outputs/reports/e3_climate_prepare.json
```

O arquivo `zone_climate_hourly_e3.parquet` preserva todas as features E2 e acrescenta anomalias e frações de pontos em eventos E3.

### 3. Rodar E1 × E2 × E3

```bash
python scripts/36_run_e3.py --subsystem SE/CO
```

Saídas:

```text
outputs/metrics/e3_real_pilot_metrics.csv
outputs/metrics/e3_real_pilot_predictions.parquet
outputs/reports/e3_real_pilot_summary.json
```

Além de `ALL` e H01–H24, as métricas incluem segmentos como `EXTREME_ANY`, `EXTREME_HEAT`, `EXTREME_COLD`, `EXTREME_RAIN` e `EXTREME_WIND` quando houver ocorrências no holdout.

## Interpretação

Uma variação negativa de WAPE significa redução de erro. O relatório compara:

- E2 vs E1;
- E3 vs E1;
- E3 vs E2;
- E3 vs E1/E2 no subconjunto `EXTREME_ANY` quando disponível.

`PERFECT_WEATHER_BACKTEST` continua sendo limite superior do valor do clima observado, não avaliação de forecast meteorológico operacional.
