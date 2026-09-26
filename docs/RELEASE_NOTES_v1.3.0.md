# Release notes — v1.3.0

- implementa E3 a partir das regras efetivamente presentes no snapshot OpenMeteo fornecido;
- baixa baseline térmico diário 2015–2024 para alvo 2025 usando ERA5-Land;
- calcula baseline mensal `mean/p05/p10/p90/p95` e anomalia diária contra a média climatológica;
- implementa calor/frio incomum e extremo, candidatos a onda, chuva intensa/extrema, vento forte/severo/extremo e candidato diário a tempestade;
- preserva prioridade de severidade e regras de consecutividade do snapshot;
- propaga contexto diário local para cada hora UTC e agrega por pontos representativos do SE/CO;
- produz `zone_climate_hourly_e3.parquet` sem sobrescrever o artefato E2;
- E3 entra automaticamente no backtest direct H01–H24 sem alterar E1/E2;
- resumo incremental passa a reportar E3 vs E2 além de E3 vs E1;
- adiciona testes de baseline, anomalia, ondas, chuva, vento, tempestade e integração das features E3.

Validação do pacote: 64 testes passaram; 2 testes de I/O Parquet foram pulados no ambiente de build por ausência de `pyarrow`.
