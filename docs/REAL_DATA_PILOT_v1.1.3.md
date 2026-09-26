# Predicta v1.1.3 — piloto real direct multi-horizon

## Objetivo

Medir E0/E1/E2/E3 em uma previsão fixa das próximas 24 horas sem propagar erro recursivo entre horizontes.

Para cada origem `t`, a versão 1.1.3 treina modelos independentes:

```text
H01: features conhecidas em t + calendário/clima de t+1  -> carga t+1
H02: features conhecidas em t + calendário/clima de t+2  -> carga t+2
...
H24: features conhecidas em t + calendário/clima de t+24 -> carga t+24
```

Nenhum modelo H02...H24 recebe a previsão de outro horizonte.

## Features históricas

As features de carga são relativas à origem e, portanto, observáveis no instante de emissão:

```text
issue_lag_0h
issue_lag_1h
issue_lag_2h
issue_lag_24h
issue_lag_48h
issue_lag_168h
```

Calendário descreve a hora-alvo em `calendar_timezone`. E2/E3 acrescentam clima da hora-alvo conforme o modo meteorológico declarado.

## Intervalos p10/p90

Cada par `(experimento, horizonte)` tem seu próprio intervalo. O modelo pontual é ajustado em dados mais antigos. Em seguida, um bloco cronológico imediatamente anterior ao holdout calcula os quantis 10% e 90% dos resíduos.

```text
passado antigo        pré-teste                    holdout
[ fit do ponto ] [ calibração p10/p90 ] [ avaliação final ]
```

Default:

```text
calibration_hours = 720
```

Em smoke tests curtos o bloco pode ser reduzido automaticamente, preservando pelo menos 48 observações e amostra mínima de fit. Em ONS 2025 com holdout de 720 h, o esperado é usar 720 h de calibração.

## Comando E0/E1

```bash
python scripts/29_run_real_pilot.py \
  --load data/processed/demand/load_hourly.parquet \
  --subsystem SE/CO \
  --weather-mode PERFECT_WEATHER_BACKTEST \
  --test-hours 720 \
  --forecast-horizon 24 \
  --origin-step-hours 24 \
  --calendar-timezone America/Sao_Paulo \
  --calibration-hours 720
```

## Comando E0/E1/E2/E3

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

## Saídas adicionais de auditoria

`real_pilot_predictions.parquet` contém, para E1/E2/E3:

```text
model_strategy = direct_multi_horizon
interval_calibration_method
interval_calibration_rows
interval_calibration_coverage
```

As métricas continuam contendo `ALL` e `H01`...`H24`.

## Interpretação

O resultado recursivo da v1.1.2 não deve ser comparado diretamente como se fosse a mesma estratégia de forecast. A v1.1.3 passa a ser o baseline válido para a próxima etapa E2/E3.
