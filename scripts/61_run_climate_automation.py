#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from predicta_climate.arco import CORE_GROUPS
from predicta_climate.router import HistoricalMode, RouterConfig, load_router_config, run_historical_router


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Entrada da etapa N da automação climática. AUTO usa ARCO para histórico; "
            "o modo Open-Meteo pode cair para ARCO em HTTP 429."
        )
    )
    p.add_argument("--mode", choices=[m.value for m in HistoricalMode], default=None)
    p.add_argument("--config", type=Path, default=ROOT / "configs/climate_router.json")
    p.add_argument("--subsystem", choices=["n", "ne", "seco", "s", "all"], default="all")
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--groups", nargs="+", choices=list(CORE_GROUPS), default=list(CORE_GROUPS))
    p.add_argument("--points-dir", type=Path, default=ROOT / "data/processed/grid")
    p.add_argument("--output-root", type=Path, default=ROOT / "data/climate_store")
    p.add_argument("--point-batch-size", type=int, default=32)
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--openmeteo-command",
        nargs=argparse.REMAINDER,
        help=(
            "Comando da etapa histórica Open-Meteo existente. Use após '--openmeteo-command'. "
            "Alternativa: PREDICTA_OPENMETEO_HISTORICAL_COMMAND."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    base = load_router_config(args.config)
    config = RouterConfig(
        mode=HistoricalMode(args.mode) if args.mode else base.mode,
        fallback_http_codes=base.fallback_http_codes,
        fallback_on_any_openmeteo_error=base.fallback_on_any_openmeteo_error,
    )
    selected = [args.subsystem.upper()] if args.subsystem != "all" else ["N", "NE", "SECO", "S"]
    result = run_historical_router(
        config=config,
        points_dir=args.points_dir,
        output_root=args.output_root,
        subsystems=selected,
        start_year=args.start_year,
        end_year=args.end_year,
        groups=args.groups,
        point_batch_size=args.point_batch_size,
        max_retries=args.max_retries,
        force=args.force,
        openmeteo_command=args.openmeteo_command,
    )
    report = ROOT / "outputs/reports/climate_router_last_run.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Climate Router OK. Relatório: {report}")
    # Exit 0 is intentional: the parent automation should continue to the next stage.


if __name__ == "__main__":
    main()
