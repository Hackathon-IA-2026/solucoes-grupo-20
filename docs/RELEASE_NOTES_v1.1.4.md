# Release notes — v1.1.4

## Objetivo

Melhorar a engenharia de features do E1 do MVP sem trocar algoritmo, contratos ou metodologia de backtest.

## Alterações

- mantém **direct multi-horizon**, com um Ridge independente por H01...H24;
- mantém o gate anti-leakage e calendário em hora civil local;
- preserva as features de estado no instante de emissão: `issue_lag_0h`, `1h`, `2h`, `24h`, `48h`, `168h`;
- adiciona histórico relativo ao horário-alvo:
  - `target_lag_24h`;
  - `target_lag_48h`;
  - `target_lag_168h`;
  - `mean_same_target_hour_3d`;
  - `mean_same_target_hour_7d`;
- adiciona aliases explícitos de calendário do alvo e codificação cíclica:
  - `target_hour`, `target_day_of_week`, `target_weekend`, `target_holiday_national`, `target_month`;
  - `target_hour_sin/cos`;
  - `target_day_of_week_sin/cos`;
- E2/E3 herdam exatamente as mesmas features históricas e acrescentam clima/anáomalias conforme o experimento;
- disponibilidade de clima agora é checada apenas para colunas realmente provenientes do dataset climático; features históricas locais não são confundidas com exógenas;
- saída de backtest registra `feature_set_version=v1.1.4_target_history`.

## Regra anti-leakage

Para horizonte `h <= 24`:

```text
target_lag_24h = load(issue + h - 24h)
```

Como `h <= 24`, esse timestamp nunca é posterior ao `issue_time`. A mesma lógica vale para 48h, 168h e para as médias do mesmo horário nos 3/7 dias anteriores.

## Validação do build

```text
54 passed
2 skipped (somente I/O Parquet no ambiente sem pyarrow)
```
