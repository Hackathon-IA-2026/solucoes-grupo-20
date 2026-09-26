# Predicta Web Studio v1.11.1

Hotfix de resiliência climática para backfills multi-ano em grade 0,1°.

## Correções

- HTTP 429 persistente não encerra mais o downloader como erro científico genérico.
- Após o orçamento de retries, o downloader grava `WAITING_RATE_LIMIT`, preserva checkpoint e encerra com código 75 (defer/retry seguro).
- A automação completa reconhece código 75, espera e retoma automaticamente o mesmo comando, reutilizando cache por ponto/ano.
- Ao esgotar os ciclos configurados, a automação finaliza como `WAITING_RATE_LIMIT`, e não `FAILED`.
- Baseline/E3 diário passa a aceitar batch separado (`--daily-batch-size`, default 24).
- Pontos de fusos diferentes agora podem compartilhar a mesma chamada diária usando lista de timezones por localização, reduzindo requests.
- Endpoint histórico é configurável por `--archive-url` ou `PREDICTA_OPENMETEO_ARCHIVE_URL`.
- API key opcional fica fora da linha de comando via `PREDICTA_OPENMETEO_API_KEY`.

## Uso de alto volume

O endpoint público continua sujeito às cotas do provedor. Backfills nacionais de vários anos podem exigir múltiplas janelas de quota mesmo com batching/cache. Para cargas intensivas, a aplicação aceita um endpoint Open-Meteo local/self-hosted compatível com `/v1/archive`.
