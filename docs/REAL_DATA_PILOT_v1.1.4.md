# Predicta v1.1.4 — E1 com histórico do horário-alvo

A v1.1.4 é o último ajuste pequeno de feature engineering previsto antes de avançar para E2/E3 no MVP.

## Por que mudou

O E1 da v1.1.3 era muito forte em H01, mas degradava em horizontes longos porque descrevia principalmente o estado da carga no `issue_time`. Agora ele também descreve como o **horário que será previsto** se comportou recentemente.

Exemplo: emissão às 08h para prever 20h (`H12`). O modelo recebe, além do estado das 08h:

```text
ontem às 20h
dois dias atrás às 20h
sete dias atrás às 20h
média das 20h nos últimos 3 dias
média das 20h nos últimos 7 dias
calendário das 20h
```

Tudo isso já existe às 08h; nenhuma carga futura é utilizada.

## Comando do piloto

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

Use o novo resultado de E1 como referência para E2/E3. Não altere o holdout ao comparar o ganho climático.
