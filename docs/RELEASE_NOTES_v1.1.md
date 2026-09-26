# Release notes — v1.1

- Adapter real para ONS `Balanço de Energia nos Subsistemas`.
- Separação de carga e oferta observada por subsistema.
- Timezone de `din_instante` obrigatório quando timestamp é naive.
- Parser ANEEL atualizado para os nomes atuais `Dsc*`, decimal com vírgula e unidade `DscUnidadeTerciaria`.
- Downloader ANEEL por DataStore/CSV.
- Calendário Brasil com feriados nacionais fixos e eventos móveis separados.
- Join Fase 3 long-form → clima wide para ML.
- Agregação de incidentes por tipo.
- Gate de dados reais/anti-leakage.
- Experimentos E0_D1, E0_D7, E0_BLEND, E1, E2, E3 na mesma janela temporal.
- Métricas globais e por tipo de extremo.
- Smoke fixtures com formato das fontes reais.
- 47 testes passando no ambiente de build; 2 testes de I/O Parquet pulados pela ausência local de `pyarrow`.
