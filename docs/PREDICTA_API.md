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

DESSEM programming is required for all 24 hours of a product simulation. The
`dessem` block identifies `source`, `hours`, `retrospective`, `captured_at_utc`,
`snapshot_sha256`, and `source_urls`. Each hourly entry includes:

- `demand_p50_mw`: Predicta demand forecast;
- `dessem_programmed_load_mw`: ONS DESSEM programmed demand;
- `dessem_relative_gap_pct`: `100 * (Predicta / DESSEM - 1)`;
- `supply_pressure`: experimental `Predicta / (Predicta + DESSEM)` signal.

Power values are hourly averages in MW. This signal is a comparison with the
programmed demand, not a generation capacity or reserve estimate. Snapshots
without verified availability at forecast issue time are allowed only in replay
mode and reported as retrospective. Missing or incomplete windows return HTTP
400; the product does not silently continue without DESSEM.

## Daily Savings

`optimization_objective` accepts `flatten` or `cost`. Consumer savings and the
portfolio curve now use the same selected objective and shifted profile;
`consumer_optimized_consumption_kwh` mirrors `optimized_consumption_kwh`.
The flatten objective reduces variance subject to energy, peak and cost limits.
It can legitimately produce zero savings: a flatter curve does not guarantee a
lower bill. Tariffs and their guardrails are unchanged by the selected scenario.

- `consumer.savings_24h_rs` is the original hourly consumption cost minus the
  shifted consumption cost, both evaluated at the same dynamic tariff.
- `consumer.savings_month_rs` is the unrounded daily saving multiplied by
  `projection.days` (30.4375, an average month).
- `projection.method` is `REPEAT_SELECTED_24H_AVERAGE_MONTH`; `is_forecast` is false.
  This assumes the selected day's consumption, tariff and participation repeat,
  not that a month of forecasts has been generated.
- `portfolio.customer_savings_24h_rs` and `customer_savings_month_rs` sum the
  savings of participating consumers only. The scope is
  `PARTICIPATING_CONSUMERS_NOT_DISTRIBUTOR_PROFIT`.

The Product preset `?scenario=favorable` selects CEMIG, a synthetic residential
profile of 900 kWh/month, 50% flexible energy, and forecast issue
2026-08-23T23:00:00Z (20h in Sao Paulo). This window was selected for favorable
load smoothing and positive savings among 15 available August windows. It is not
typical-performance evidence. `?scenario=standard` restores 300 kWh/month,
20% flexible energy and the previous issue time. Both presets remain editable.

## Supporting endpoints

- `GET /api/v1/catalog/distribution-areas/` returns the concession areas as GeoJSON.
- `GET /api/v1/catalog/profiles/?cnpj=...&region=SE%2FCO&mode=replay&replay_issue=...` returns the distributor and tariff profiles for the selected window. `effective_date=YYYY-MM-DD` can be supplied explicitly.
- `GET /api/v1/simulations/options/?region=SE%2FCO&mode=replay` returns available replay windows and operational status.