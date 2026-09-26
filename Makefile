.PHONY: install web-install web-migrate web-run web-check bootstrap test grid climate-fixture baseline-smoke demo motor-sin motor-tarifa clean-generated real-pilot-smoke e2-download e2-prepare e2-run e3-download e3-prepare e3-run freeze-e3 system-signal-real

install:
	python -m pip install -e ".[dev]"

web-install:
	python -m pip install -e ".[dev,web,ml]"

web-migrate:
	python manage.py migrate

web-check:
	python manage.py check

web-run:
	python manage.py runserver 127.0.0.1:8000

bootstrap:
	python scripts/00_bootstrap_phase0.py --require-parquet

test:
	pytest -q

grid:
	python scripts/01_build_grid.py --brazil-only --output data/processed/grid/brazil_grid_01deg.parquet

climate-fixture:
	python scripts/02_ingest_climate_snapshot.py tests/fixtures/openmeteo_hourly_example.json
	python scripts/03_prepare_climate.py --run-id fixture-smoke

baseline-smoke:
	python scripts/04_generate_baseline_smoke_data.py
	python scripts/04_build_climate_baseline.py --input-run-id baseline-fixture --target-year 2026 --variable temperature_2m --run-id baseline-smoke

motor-sin:
	python scripts/run_motor_sin.py --demo --issue-time 2026-09-19T00:00:00Z

motor-tarifa:
	python scripts/run_motor_tarifa.py

demo:
	python scripts/run_pipeline.py --demo --issue-time 2026-09-19T00:00:00Z

clean-generated:
	rm -rf data/demo data/processed/generation data/processed/assets data/processed/demand data/processed/tariff models/demand
	rm -f outputs/contracts/*.parquet outputs/metrics/*.csv outputs/reports/*.json

real-pilot-smoke:
	python scripts/30_generate_real_pilot_smoke.py
	python scripts/24_prepare_ons_balance.py --input tests/fixtures/ons_balance_source_shaped.csv --source-timezone UTC --load-output /tmp/predicta_load.csv --supply-output /tmp/predicta_supply.csv --report /tmp/predicta_ons_quality.json
	python scripts/27_real_data_gate.py --load /tmp/predicta_load.csv --climate tests/fixtures/zone_climate_source_shaped.csv --subsystem SE/CO --weather-mode PERFECT_WEATHER_BACKTEST --output /tmp/predicta_gate.json
	python scripts/29_run_real_pilot.py --load /tmp/predicta_load.csv --climate tests/fixtures/zone_climate_source_shaped.csv --subsystem SE/CO --weather-mode PERFECT_WEATHER_BACKTEST --test-hours 336 --metrics-output /tmp/predicta_metrics.csv --predictions-output /tmp/predicta_predictions.csv --report-output /tmp/predicta_summary.json

# E2 MVP: climate raw at target hour (PERFECT_WEATHER_BACKTEST)
e2-download:
	python scripts/31_download_e2_climate.py --load data/processed/demand/load_hourly.parquet --subsystem SE/CO

e2-prepare:
	python scripts/32_prepare_e2_zone_climate.py --subsystem SE/CO --run-id e2-2025

e2-run:
	python scripts/33_run_e2.py --subsystem SE/CO

# E3 MVP: 10-year OpenMeteo snapshot baseline + daily anomaly/event context
e3-download:
	python scripts/34_download_e3_context.py --load data/processed/demand/load_hourly.parquet --subsystem SE/CO

e3-prepare:
	python scripts/35_prepare_e3_context.py --subsystem SE/CO --target-year 2025

e3-run:
	python scripts/36_run_e3.py --subsystem SE/CO

# v1.4 operational bridge
freeze-e3:
	python scripts/37_freeze_e3_models.py --subsystem SE/CO

system-signal-real:
	python scripts/39_build_real_system_signal.py


# v1.6 Web Studio helpers
ons-history:
	python scripts/45_sync_ons_history.py --start-year 2021 --end-year 2025

tariff-geo:
	python scripts/44_prepare_tariff_geography.py

validate-xgb-e3:
	python scripts/46_validate_model.py --experiment E3 --algorithm xgboost --subsystem SE/CO
