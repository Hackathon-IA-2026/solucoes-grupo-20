# v1.2.1 — hotfix E2 ERA5-Seamless

- corrige a fonte meteorológica do E2: `era5_land` isolado não fornece no Open-Meteo as famílias de precipitação, vento e radiação exigidas pelo experimento;
- E2 passa a usar `era5_seamless` por padrão, combinando temperatura/umidade de ERA5-Land com campos atmosféricos de ERA5;
- preserva a grade Predicta 0,1° como índice espacial comum, sem afirmar que todas as variáveis têm resolução nativa 0,1°;
- adiciona validação de cobertura: temperatura, dewpoint, precipitação, vento e radiação não podem estar integralmente nulos;
- usa novo diretório RAW `data/raw/climate/e2_openmeteo_seamless` para não misturar downloads inválidos da v1.2.0;
- remove placeholders `incident_* = 0` do E2 para que o sistema não sinalize E3 como disponível antes do baseline/anomalias reais;
- torna a detecção de E3 mais estrita: exige anomalia/percentil real ou incidente efetivamente não-zero;
- mantém as regras de anomalia/extremos do snapshot OpenMeteo para o E3;
- validação local: 60 testes passaram e 2 foram pulados apenas por ausência de `pyarrow` no ambiente de build.
