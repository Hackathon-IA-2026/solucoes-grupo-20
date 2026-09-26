# Predicta v0.3 — Fase 3

## Incluído

- baseline climático regional dos dez anos completos anteriores;
- calendário sazonal canônico de 366 dias para alinhamento de anos bissextos;
- janela móvel sazonal ±15 dias;
- mediana, p01/p05/p10/p25/p75/p90/p95/p99, IQR e contagens;
- `expected_sample_count` e `coverage_ratio`;
- cálculo do ano-alvo: anomalia, robust-z e percentil empírico;
- escrita particionada em Parquet;
- relatório de execução/qualidade;
- guardrail de escopo pequeno;
- gerador de dados sintéticos para smoke test offline;
- testes unitários adicionais da Fase 3.

## Não incluído

- incidentes climáticos (Fase 4);
- download bulk nacional de dez anos;
- otimização distribuída/Dask/Spark;
- definição de baseline climatológico oficial;
- uso de previsão meteorológica operacional futura.
