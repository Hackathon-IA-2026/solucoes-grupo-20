from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from motor_sin.climate.baseline import (
    baseline_years_for_target,
    build_climate_baseline,
    discover_climate_parquets,
    read_climate_parquets,
    write_phase3_artifacts,
)
from motor_sin.climate.variables import CANONICAL_VARIABLES


def _load_baseline_config(path: str | Path) -> dict:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return (document.get("climate") or {}).get("baseline") or {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Predicta 10-year regional hourly climate baseline and score target-year observations."
    )
    parser.add_argument("--input-root", default="data/processed/climate/climate_hourly")
    parser.add_argument("--input-run-id", action="append", default=None, help="Repeat to select normalized climate run(s).")
    parser.add_argument("--target-year", required=True, type=int)
    parser.add_argument("--variable", action="append", choices=list(CANONICAL_VARIABLES), default=None)
    parser.add_argument("--cell-id", action="append", default=None)
    parser.add_argument("--config", default="configs/climate.yaml")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--baseline-output-root", default="data/processed/climate/baseline_10y")
    parser.add_argument("--score-output-root", default="data/processed/climate/anomalies_hourly")
    parser.add_argument("--report", default=None)
    parser.add_argument("--allow-partial-history", action="store_true")
    parser.add_argument(
        "--max-cells",
        type=int,
        default=None,
        help="Small-scope guard. 0 disables. Default comes from configs/climate.yaml.",
    )
    args = parser.parse_args()

    cfg = _load_baseline_config(args.config)
    years_count = int(cfg.get("complete_previous_years", 10))
    window_days = int(cfg.get("seasonal_window_days", 15))
    baseline_version = str(cfg.get("version", "1.0"))
    robust_epsilon = float(((cfg.get("target_scoring") or {}).get("robust_z_epsilon", 1e-6)))
    warning_threshold = float(cfg.get("coverage_warning_threshold", 0.80))
    max_cells = int(cfg.get("small_scope_max_cells", 25)) if args.max_cells is None else int(args.max_cells)
    scientific_status = str(cfg.get("scientific_status", "operational_baseline_not_official_climatological_normal"))

    baseline_years = baseline_years_for_target(args.target_year, years_count)
    years_to_read = [*baseline_years, args.target_year]
    paths = discover_climate_parquets(args.input_root, years=years_to_read, run_ids=args.input_run_id)
    variables = tuple(args.variable or CANONICAL_VARIABLES)
    columns = ["interval_start_utc", "cell_id", *variables]
    df = read_climate_parquets(paths, columns=columns)

    result = build_climate_baseline(
        df,
        target_year=args.target_year,
        variables=variables,
        complete_previous_years=years_count,
        seasonal_window_days=window_days,
        baseline_version=baseline_version,
        require_all_baseline_years=not args.allow_partial_history,
        cell_ids=args.cell_id,
        max_cells=None if max_cells == 0 else max_cells,
        robust_epsilon=robust_epsilon,
    )

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = args.report or f"outputs/reports/climate_baseline_{run_id}.json"
    report = write_phase3_artifacts(
        result,
        baseline_output_root=args.baseline_output_root,
        score_output_root=args.score_output_root,
        report_path=report_path,
        run_id=run_id,
        source_files=paths,
        scientific_status=scientific_status,
        coverage_warning_threshold=warning_threshold,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
