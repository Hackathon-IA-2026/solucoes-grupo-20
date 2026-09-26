# Predicta v1.1.2 — Piloto real com backtest 24 h corrigido

## O que foi corrigido

A v1.1.1 já ingeria o Balanço ONS e executava E0/E1. A v1.1.2 corrige duas questões metodológicas antes de incorporar clima:

1. **Leakage de carga no holdout:** o backtest antigo avaliava cada linha usando `lag_1h`/`lag_2h` observados. Isso mede um forecast rolante de curto prazo, não uma emissão fixa das próximas 24 horas.
2. **Calendário em UTC:** os joins e o armazenamento devem permanecer UTC, mas hora civil, dia da semana e feriados precisam ser derivados no fuso local relevante.

## Novo contrato do backtest

O piloto usa origens fixas. Em cada `issue_time_utc` são emitidas previsões para:

```text
t+1, t+2, ..., t+24
```

Para cada origem:

- carga observada com timestamp `<= issue_time_utc` pode ser usada;
- carga observada `> issue_time_utc` é proibida como feature;
- quando `lag_1h` ou `lag_2h` aponta para uma hora já dentro do horizonte, usa-se a própria previsão p50 produzida nessa origem;
- D-1 e D-7 só são usados quando os valores correspondentes já eram observáveis no instante de emissão;
- o modelo é treinado apenas em registros disponíveis até a primeira origem do holdout.

O padrão é:

```text
forecast_horizon = 24 h
origin_step       = 24 h
```

Assim, uma janela de `720 h` gera 30 origens diárias e 720 alvos sem sobreposição.

## Tempo local sem perder UTC

O campo canônico continua sendo:

```text
interval_start_utc
```

Calendário é derivado por conversão explícita:

```text
UTC -> calendar_timezone -> hour/day_of_week/holiday
```

Para o piloto SE/CO atual, o comando usa explicitamente:

```text
America/Sao_Paulo
```

Isso é um parâmetro do experimento, não uma regra universal para todos os subsistemas. Se o recorte mudar, a decisão de fuso deve ser revisada e documentada.

## Comando E0/E1 sem clima

```bash
python scripts/29_run_real_pilot.py \
  --load data/processed/demand/load_hourly.parquet \
  --subsystem SE/CO \
  --weather-mode PERFECT_WEATHER_BACKTEST \
  --test-hours 720 \
  --forecast-horizon 24 \
  --origin-step-hours 24 \
  --calendar-timezone America/Sao_Paulo
```

## Comando E0/E1/E2/E3 com clima

```bash
python scripts/29_run_real_pilot.py \
  --load data/processed/demand/load_hourly.parquet \
  --climate data/processed/climate/zone_climate_hourly.parquet \
  --subsystem SE/CO \
  --weather-mode PERFECT_WEATHER_BACKTEST \
  --test-hours 720 \
  --forecast-horizon 24 \
  --origin-step-hours 24 \
  --calendar-timezone America/Sao_Paulo
```

## Saídas

`outputs/metrics/real_pilot_predictions.parquet` passa a registrar:

```text
issue_time_utc
interval_start_utc
horizon_hour
experiment
actual_mw
p10_mw
p50_mw
p90_mw
calendar_timezone
```

`outputs/metrics/real_pilot_metrics.csv` contém:

- `horizon = ALL` para as 24 horas agregadas;
- `H01` ... `H24` para erro por horizonte;
- segmentos `EXTREME_*` quando clima/incidentes estiverem disponíveis.

O console mostra `ALL`, `H01`, `H06`, `H12` e `H24`; o CSV mantém todos os horizontes.

## Experimentos

| Experimento | Informação permitida |
|---|---|
| E0_D1 | carga do mesmo horário no dia anterior, desde que observável na origem |
| E0_D7 | carga do mesmo horário 7 dias antes |
| E0_BLEND | média D-1/D-7 |
| E1 | lags recursivos + calendário local |
| E2 | E1 + clima bruto do horizonte |
| E3 | E2 + anomalias, percentis e incidentes |

E1/E2/E3 continuam usando Ridge nesta etapa para isolar o efeito das features. Isso ainda não é o estimador final do produto.

## Testes regressivos adicionados

A suíte agora verifica explicitamente que:

- `03:00 UTC` em 2025 vira `00:00` em `America/Sao_Paulo` para as features comportamentais;
- alterar a carga observada nas 24 horas futuras não altera a previsão E1 de uma origem já emitida;
- todas as experiências usam as mesmas origens/alvos;
- `horizon_hour` cobre 1..24.

## Próximo passo

Reexecute E0/E1 com o ONS 2025 real. O WAPE anterior de E1 (1,55%) não deve ser reutilizado como evidência, pois foi obtido com o backtest rolante antigo. O novo valor, obtido por origem fixa, passa a ser o baseline válido para comparar E2 e E3.
