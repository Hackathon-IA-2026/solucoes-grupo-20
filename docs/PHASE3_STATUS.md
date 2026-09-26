# Fase 3 — Baseline climático regional de 10 anos

Status desta entrega: **implementada para o caso controlado / recorte pequeno** previsto no plano v0.2.

## Regra implementada

Para um ano-alvo `Y`, o histórico elegível é sempre:

```text
Y-10 ... Y-1
```

O ano-alvo é excluído da amostra histórica mesmo quando está presente no mesmo dataset de entrada.

O baseline é calculado por:

```text
cell_id
+ variável
+ hora UTC
+ época do ano (dia sazonal ±15 dias)
```

A janela sazonal usa um calendário canônico de 366 dias, ancorado por mês/dia, para manter março–dezembro alinhados entre anos bissextos e não bissextos. Dezembro e janeiro são tratados circularmente.

## Estatísticas produzidas

Para cada grupo:

```text
median
p01
p05
p10
p25
p75
p90
p95
p99
IQR
sample_count
expected_sample_count
coverage_ratio
```

Os quantis usam interpolação linear. O método fica registrado no relatório de execução.

## Avaliação do ano-alvo

Quando há observações do ano-alvo no dataset de entrada, a mesma execução também produz, por observação:

```text
anomaly = value - baseline_median

robust_z =
(value - baseline_median)
/
max(IQR / 1.349, epsilon)

percentile =
fração empírica das observações históricas <= value
```

O percentil é portanto uma ECDF empírica do tipo `<=`, sempre limitada a `[0,1]` quando existe amostra histórica.

## Artefatos

Baseline:

```text
data/processed/climate/baseline_10y/
└── run_id=<RUN_ID>/
    └── target_year=<YYYY>/
        └── variable=<VAR>/
            └── part-*.parquet
```

Anomalias / percentis do ano-alvo:

```text
data/processed/climate/anomalies_hourly/
└── run_id=<RUN_ID>/
    └── target_year=<YYYY>/
        └── variable=<VAR>/
            └── part-*.parquet
```

Relatório:

```text
outputs/reports/climate_baseline_<RUN_ID>.json
```

## Proteções

- valida duplicidade `cell_id + interval_start_utc` antes de calcular o baseline;
- exige os dez anos anteriores por célula por padrão;
- `--allow-partial-history` existe somente para depuração e gera aviso no relatório;
- há um guardrail de escopo pequeno (`small_scope_max_cells: 25`) para impedir expansão nacional acidental nesta fase;
- cobertura amostral é explicitamente registrada, nunca corrigida silenciosamente;
- dados sintéticos de smoke test são identificados como sintéticos e não devem ser usados como evidência científica.

## Relação com o snapshot OpenMeteo

O snapshot fornecido declara a metodologia como `operational_baseline_not_official_climatological_normal` e explicita dez anos completos no baseline de temperatura. O arquivo `baseline.py` original do snapshot **não estava disponível**, portanto esta implementação não tenta reconstruí-lo. A lógica desta fase vem do Plano Prático Predicta v0.2 e reutiliza apenas os princípios efetivamente suportados pelo snapshot: histórico ERA5-Land explícito, rastreabilidade, anos completos anteriores e status científico operacional.

## Definition of Done atendida

- [x] ano-alvo excluído do baseline;
- [x] dez anos anteriores configuráveis;
- [x] agrupamento por célula/variável/hora/época do ano;
- [x] janela sazonal ±15 dias;
- [x] mediana, percentis, IQR e `sample_count`;
- [x] anomalia, `robust_z` e percentil empírico;
- [x] cobertura amostral auditável;
- [x] Parquet particionado;
- [x] relatório de qualidade;
- [x] testes de ano-alvo, leap year, virada do ano, ECDF, robust-z e guardrail de escopo.

A próxima fase é a **Fase 4 — detecção de incidentes climáticos** a partir dos percentis e scores produzidos aqui.
