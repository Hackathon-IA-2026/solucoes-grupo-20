# Predicta v1.2.1 — E2 com clima real

## Objetivo

Comparar o E1 congelado (`histórico + calendário`) contra o E2 (`E1 + clima bruto no horário-alvo`), usando o mesmo backtest fixed-origin direct multi-horizon H01–H24.

## Regra experimental

O E2 recebe apenas clima bruto agregado no horário que está sendo previsto:

- `temperature_2m_*`
- `dewpoint_2m_*`
- `precipitation_*`
- `wind_speed_10m_*`
- `solar_radiation_*`

Anomalias, percentis e flags de extremo **não entram no E2**. Isso é deliberado para que E1 → E2 meça o valor incremental do clima bruto e E2 → E3 meça depois o valor incremental do contexto anômalo/extremo.

## OpenMeteo snapshot usado como fonte metodológica

O arquivo `configs/openmeteo_event_rules_snapshot_2026-08-08.2.json` foi copiado literalmente do snapshot `OpenMeteo_snapshot_disponivel_2026-09-18.zip`.

Para E3, a semântica térmica preservada é:

- ERA5-Land;
- 10 anos completos imediatamente anteriores ao ano-alvo;
- agregação diária local de `temperature_2m_max` e `temperature_2m_min`;
- baseline agrupado por mês do calendário;
- estatísticas `mean`, `p05`, `p10`, `p90`, `p95`;
- anomalia = valor diário − média climatológica mensal;
- `extreme_heat_day`: Tmax >= p95 **e** anomalia >= +3 °C;
- `extreme_cold_day`: Tmin <= p05 **e** anomalia <= -3 °C;
- `heat_wave_candidate`: Tmax >= p90 **e** anomalia >= +5 °C por pelo menos 5 dias, com noite quente >= p90;
- `cold_wave_candidate`: Tmin <= p10 **e** anomalia <= -3 °C por pelo menos 3 dias.

O snapshot se autodefine como `operational_baseline_not_official_climatological_normal`; essa qualificação foi preservada.

O módulo `motor_sin/climate/openmeteo_snapshot_anomaly.py` materializa somente regras explicitamente suportadas pelo snapshot disponível. Como o ZIP informa que `baseline.py` original não está disponível, não foram inventados detalhes ausentes.

## Recorte espacial do E2 MVP

Para evitar baixar dezenas de milhares de células antes de validar a hipótese, `configs/e2_seco_points.csv` contém oito pontos representativos (capitais de SP, RJ, MG, ES, DF, GO, MT e MS).

**Hotfix v1.2.1:** o E2 usa `era5_seamless` na Historical Weather API do Open-Meteo. O motivo é técnico: o endpoint não entrega precipitação, vento e radiação solar diretamente quando `models=era5_land`; esses campos podem retornar nulos. `era5_seamless` combina temperatura/umidade de ERA5-Land com campos atmosféricos de ERA5 para disponibilizar todas as famílias necessárias ao E2. A grade Predicta permanece 0,1° como índice espacial canônico; isso não implica que todas as variáveis-fonte possuam resolução nativa de 0,1°.

Para o E3, a semântica de anomalia térmica do snapshot continua baseada em temperatura ERA5-Land e nos 10 anos completos anteriores ao ano-alvo.

A agregação recebe:

`climate_spatial_method = MVP_REPRESENTATIVE_POINTS_UNIFORM`

Portanto este piloto **não deve ser descrito como média climática integral do subsistema SE/CO**. É um proxy espacial para o MVP. A expansão posterior substitui os pontos por células amostradas/ponderadas ou por toda a grade, sem alterar o experimento E1/E2.

## Execução

### 1. Baixar clima para o mesmo intervalo do ONS

```bash
python scripts/31_download_e2_climate.py \
  --load data/processed/demand/load_hourly.parquet \
  --subsystem SE/CO \
  --model era5_seamless
```

O intervalo é inferido da carga. No arquivo ONS 2025 atualmente usado isso inclui a borda UTC que alcança 2026-01-01.

### 2. Normalizar e agregar

```bash
python scripts/32_prepare_e2_zone_climate.py \
  --subsystem SE/CO \
  --run-id e2-2025-seamless
```

Saída principal:

```text
data/processed/climate/zone_climate_hourly.parquet
```

### 3. Rodar E1 x E2

```bash
python scripts/33_run_e2.py --subsystem SE/CO
```

Ou diretamente:

```bash
python scripts/29_run_real_pilot.py \
  --load data/processed/demand/load_hourly.parquet \
  --climate data/processed/climate/zone_climate_hourly.parquet \
  --subsystem SE/CO \
  --weather-mode PERFECT_WEATHER_BACKTEST \
  --test-hours 720 \
  --forecast-horizon 24 \
  --origin-step-hours 24 \
  --calendar-timezone America/Sao_Paulo \
  --calibration-hours 720
```

## Interpretação

O `PERFECT_WEATHER_BACKTEST` usa clima que de fato ocorreu no horário-alvo. Ele mede o teto de valor potencial do clima; não representa ainda uma previsão meteorológica operacional disponível no instante de emissão.

O critério principal é `E2_wape_change_vs_E1_pct` no relatório. Valor negativo significa redução de erro.


## Migração v1.2.0 → v1.2.1

Não reutilize `data/raw/climate/e2_openmeteo` da v1.2.0 para o E2, pois aquele download foi feito com `models=era5_land` e pode conter precipitação/vento/radiação integralmente nulos. O hotfix usa por padrão:

```text
data/raw/climate/e2_openmeteo_seamless/
```

O preparador agora também falha imediatamente se qualquer uma das cinco famílias E2 estiver ausente ou totalmente nula, em vez de omitir silenciosamente as colunas agregadas.
