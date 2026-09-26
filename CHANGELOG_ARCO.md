# Changelog — v0.4 Climate Router + ARCO

- adiciona `scripts/61_run_climate_automation.py` como ponto de entrada da etapa N;
- modo padrão `AUTO`: histórico vai diretamente ao ERA5-Land ARCO;
- Open-Meteo continua reservado ao forecast operacional;
- modo de compatibilidade `openmeteo_with_arco_fallback` detecta HTTP 429 e continua via ARCO;
- fallback ARCO concluído retorna exit code 0 para o runner pai continuar;
- retomada agora é **real por lote de células**, não reinício do ano inteiro;
- fragmentos válidos ficam em `.YYYY.partial/part-*.parquet` durante interrupções;
- fingerprint da lista de células impede reutilizar parcial de grade diferente;
- ano completo só é pulado com Parquet + manifest + quality report compatíveis;
- validação pode exigir explicitamente as colunas dos grupos solicitados;
- recusa materialização de ano ainda não fechado no cubo ARCO;
- mantém 2016 = 8.784 h/célula; 2017/2018 = 8.760 h/célula;
- documentação de integração com runner antigo adicionada.

## Herdado da v0.3

- histórico/backfill em ERA5-Land ARCO geo-chunked;
- acesso via CDS token/`~/.cdsapirc`;
- Climate Store anual Parquet/ZSTD;
- K→°C, m→mm, U/V→velocidade do vento e J/m²→W/m² médio;
- rajadas permanecem como fonte secundária opcional, sem substituição silenciosa.
