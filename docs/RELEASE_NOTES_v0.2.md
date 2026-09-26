# Predicta v0.2 — Fase 2 climática

Incremento sobre o scaffold v0.1.

## Entregue

- Fase 0 preservada;
- Fase 1 preservada;
- Fase 2 implementada para recorte pequeno;
- aquisição pontual ERA5-Land via Open-Meteo Historical API;
- importação de payload Open-Meteo local;
- RAW imutável e deduplicado;
- parser horário, UTC e unidades canônicas;
- `cell_id` 0,1° determinístico;
- Parquet por execução/ano/mês;
- relatório de qualidade;
- testes de parser, unidades, RAW, parâmetros do downloader e sobreposição.

## Deliberadamente fora desta release

- download nacional/bulk;
- baseline climático de dez anos;
- detecção de incidentes;
- ONS geração/carga;
- previsão de demanda;
- Motor 2 produtivo.

Esses itens permanecem na sequência do Plano Prático v0.2.
