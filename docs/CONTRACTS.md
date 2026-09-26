# Contratos v1 — notas operacionais

## Princípios

Os quatro contratos são o limite de acoplamento do projeto. Mudanças incompatíveis exigem uma nova versão (`*_v2`).

Todos usam:

- `schema_version` explícita;
- `run_id` para rastreabilidade;
- `interval_start_utc` em UTC, timezone-aware, alinhado à hora cheia;
- uma linha por chave lógica definida no registry;
- campos `*_json` serializados como JSON canônico em string para manter interoperabilidade tabular/Parquet.

## Chaves

| Contrato | Chave lógica |
|---|---|
| `grid_state_v1` | `run_id + interval_start_utc + cell_id` |
| `asset_exposure_v1` | `run_id + interval_start_utc + asset_id + incident_type` |
| `system_signal_v1` | `run_id + interval_start_utc + zone_type + zone_id` |
| `tariff_v1` | `run_id + interval_start_utc + distributor_id + tariff_profile_id` |

## Nulls deliberados

- `system_signal_v1.supply_pressure`: pode ser `null` quando ainda não houver fonte de oferta futura confiável.
- campos físicos de `grid_state_v1`: podem ser `null` por ausência de dado, mas scores permanecem explícitos e a qualidade deve refletir isso.
- campos específicos de geração/transmissão em `asset_exposure_v1`: podem ser `null` quando não aplicáveis ao tipo de ativo.
- `tariff_v1.supply_pressure` e `economic_signal`: podem ser `null`; o Motor 2 deve aplicar seus guardrails/fallback conforme configuração.

## Regras adicionais verificadas

`system_signal_v1`:

```text
p10 <= p50 <= p90
D, S, C em [0,1] (S pode ser null)
```

`tariff_v1`:

```text
base_total = TE + TUSD
dynamic_tariff = base_total * final_multiplier
```

O validador também detecta colunas ausentes/extras, timestamps duplicados e janelas horárias incompletas quando `--expected-hours` é informado.
