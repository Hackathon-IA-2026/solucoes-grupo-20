# Fase 2 — Ingestão climática horária

Status desta entrega: **implementada para smoke test / recorte pequeno**.

## O que entrou

- download pontual do ERA5-Land via endpoint histórico Open-Meteo;
- importação de JSON Open-Meteo já existente;
- RAW imutável e deduplicado por hash;
- parser horário com validação de comprimento das séries;
- conversão explícita para UTC timezone-aware;
- associação determinística à grade Predicta de 0,1°;
- normalização das cinco variáveis mínimas;
- unidades canônicas explícitas;
- Parquet particionado por `run_id/year/month`;
- relatório de qualidade;
- bloqueio de sobreposição `cell_id + hora` por padrão;
- testes sem dependência de internet.

## Contrato tabular desta fase

Campos mínimos produzidos:

```text
interval_start_utc
cell_id
temperature_2m
dewpoint_2m
precipitation
wind_speed_10m
solar_radiation
source
```

Metadados de proveniência também são preservados:

```text
source_service
source_model
source_grid_latitude
source_grid_longitude
source_elevation
raw_record_id
raw_payload_hash
raw_file
```

Unidades canônicas:

- temperatura e ponto de orvalho: `degC`;
- precipitação: `mm`;
- vento 10 m: `m/s`;
- radiação solar: `W/m2`.

## Relação com o snapshot OpenMeteo fornecido

O snapshot fornecido é explicitamente parcial e **não contém dados RAW meteorológicos**. Esta entrega não inventa nem reconstrói dados ausentes. Foram reaproveitadas/adaptadas as regras suportadas pelos arquivos presentes:

- endpoint histórico Open-Meteo;
- modelo explícito `era5_land`;
- persistência RAW imutável;
- hash de conteúdo ignorando `generationtime_ms` volátil;
- validação de séries de mesmo comprimento;
- rastreabilidade de payload;
- UTC como referência interna;
- dez anos completos anteriores permanecem configurados para a próxima fase.

As regras antigas de evento diário não são executadas aqui, pois o Predicta trabalha com célula × hora e o baseline da Fase 3 tem outra resolução.

## Limite deliberado

O downloader desta fase é para **recorte pequeno**. Não executar uma malha Brasil inteira ponto a ponto pelo endpoint Open-Meteo. A escala nacional deverá usar estratégia bulk/CDS apropriada sem mudar o contrato normalizado.

## Próximo DoD

A Fase 3 deverá consumir este dataset e construir, para um ano-alvo e recorte pequeno, o baseline dos dez anos completos anteriores por célula/variável/hora/janela sazonal.
