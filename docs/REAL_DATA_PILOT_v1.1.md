# Predicta v1.1 — Piloto com dados reais

## Objetivo

Validar primeiro uma vertical pequena e reproduzível antes de processar o SIN inteiro. A pergunta técnica é incremental:

1. D-1/D-7 já explicam quanto da carga?
2. histórico + calendário melhora?
3. clima bruto acrescenta sinal?
4. anomalias, percentis e incidentes melhoram especialmente nas horas extremas?

## Fontes congeladas para o piloto

### ONS — Balanço de Energia nos Subsistemas

Dataset: `balanco-energia-subsistema`.

Campos usados segundo o dicionário do ONS:

- `id_subsistema`
- `nom_subsistema`
- `din_instante`
- `val_gerhidraulica`
- `val_gertermica`
- `val_gereolica`
- `val_gersolar`
- `val_carga`
- `val_intercambio`

`val_carga` é o alvo de demanda. Geração e intercâmbio são contexto observado; não são features futuras no backtest operacional.

### Clima

A entrada do ML é construída a partir de três artefatos já existentes no projeto:

```text
Fase 2 climate_hourly (wide, por célula/hora)
 +
Fase 3 target_scores/anomalies_hourly (long, por célula/hora/variável)
 +
Fase 4 incidents_hourly
```

`attach_baseline_scores()` faz o join de anomalia/percentil da Fase 3 ao clima wide antes da agregação regional.

### Calendário

Features:

- hour
- day_of_week
- weekend
- holiday_national
- carnival
- good_friday
- corpus_christi
- month

Eventos móveis são mantidos separados; não são silenciosamente reclassificados como feriados nacionais fixos.

### ANEEL — Tarifas homologadas

Campos atuais suportados pelo parser:

- `SigAgente`
- `DatInicioVigencia`
- `DatFimVigencia`
- `DscBaseTarifaria`
- `DscSubGrupo`
- `DscModalidadeTarifaria`
- `DscClasse`
- `DscSubClasse`
- `DscDetalhe`
- `NomPostoTarifario`
- `DscUnidadeTerciaria`
- `VlrTUSD`
- `VlrTE`

O parser aceita decimal com vírgula e mantém `R$/kW` fora da soma volumétrica.

## Gate antes do ML

`27_real_data_gate.py` deve passar antes do experimento.

Bloqueadores incluem:

- chave duplicada hora/subsistema;
- carga negativa;
- falta de famílias climáticas mínimas;
- overlap insuficiente carga/clima;
- tentativa de `OPERATIONAL_FORECAST` sem clima explicitamente marcado como forecast operacional.

Warnings não impedem execução, mas ficam no relatório.

## Timezone

Internamente o Predicta usa UTC. O adaptador ONS exige `source_timezone` quando `din_instante` vem sem offset. Isso é intencional: timezone de origem deve ser uma decisão de fonte documentada, não uma suposição escondida no parser.

## Experimentos

Todos são avaliados no mesmo holdout cronológico.

| Experimento | Features |
|---|---|
| E0_D1 | carga t-24 h |
| E0_D7 | carga t-168 h |
| E0_BLEND | média D-1/D-7 |
| E1 | lags + calendário |
| E2 | E1 + clima bruto |
| E3 | E2 + anomalias + percentis + incidentes |

E1/E2/E3 usam o mesmo algoritmo Ridge na v1.1. Isso não é o modelo final; serve para medir o valor incremental das features sem confundir o resultado com troca de algoritmo.

## Segmentos de avaliação

Além de `ALL`, quando as colunas estão disponíveis são medidos:

- `EXTREME_ANY`
- `EXTREME_HEAT`
- `EXTREME_COLD`
- `EXTREME_RAIN`
- `EXTREME_WIND`
- `EXTREME_SOLAR_DEFICIT`

A presença de evento vem da Fase 4, não de um limiar inventado dentro do módulo de demanda.

## Critério para avançar

Não existe threshold de ganho pré-imposto no código. O relatório apenas mede e registra.

A equipe deve revisar:

- cobertura e consistência dos dados;
- WAPE/MAE/RMSE E0–E3;
- desempenho em extremos;
- estabilidade em janelas temporais adicionais;
- coerência de features e ausência de leakage.

Só depois disso vale escalar quatro subsistemas/10 anos e introduzir estimadores mais complexos/SHAP.

## Pendência explícita: clima → subsistema

O projeto **não inventa um polígono oficial de subsistema**. Para `28_build_zone_climate.py`, forneça um `cell_zone_map` versionado e documentado. Se o piloto usar proxy geográfico ou cesta de pontos, registre isso como proxy no nome/metadata e não apresente como limite elétrico oficial do ONS.
