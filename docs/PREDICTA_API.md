# Predicta REST API

The API mirrors the Product page simulation and is available under `/api/v1/`.

## Swagger

- Interactive documentation: `/api/docs/`
- OpenAPI document: `/api/schema/`

## Simulation

`POST /api/v1/simulations/`

Example request:

```json
{
  "cnpj": "00000000000191",
  "region": "SE/CO",
  "distributor": "DISTRIBUTOR_ID",
  "profile": "PROFILE_ID",
  "monthly_kwh": 300,
  "customer_type": "residential",
  "mode": "replay",
  "replay_key": "2026-08-10T00:00:00+00:00",
  "flexible_pct": 20
}
```

`customer_type` accepts `residential`, `commercial`, or `industrial_flat`.
`mode` accepts `replay` or `operational`; `replay_key` is optional in operational mode.

The response contains the summary used by the web page, the `optimization` block,
the selected `window`, and `hourly` with 24 local and UTC time points.

## Supporting endpoints

- `GET /api/v1/catalog/distribution-areas/` returns the concession areas as GeoJSON.
- `GET /api/v1/catalog/profiles/?cnpj=...&region=SE%2FCO&mode=replay&replay_issue=...` returns the distributor and tariff profiles for the selected window. `effective_date=YYYY-MM-DD` can be supplied explicitly.
- `GET /api/v1/simulations/options/?region=SE%2FCO&mode=replay` returns available replay windows and operational status.