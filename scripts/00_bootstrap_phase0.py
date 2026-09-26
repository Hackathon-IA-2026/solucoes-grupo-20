from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from contracts.models import CONTRACT_MODELS
from contracts.validators.core import validate_file


SCHEMA_DIR = ROOT / "contracts" / "schemas"
FIXTURE_DIR = ROOT / "contracts" / "fixtures"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase0_bootstrap_report.json"


def write_schemas() -> list[str]:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in CONTRACT_MODELS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(str(path.relative_to(ROOT)))
    return written


def materialize_parquet(csv_name: str, parquet_name: str, require: bool) -> tuple[bool, str | None]:
    src = FIXTURE_DIR / csv_name
    dst = FIXTURE_DIR / parquet_name
    df = pd.read_csv(src)
    try:
        df.to_parquet(dst, index=False)
    except (ImportError, ModuleNotFoundError) as exc:
        if require:
            raise RuntimeError(
                "Could not write Parquet. Install dependencies with `pip install -e \".[dev]\"`."
            ) from exc
        return False, str(exc)
    return True, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-parquet", action="store_true")
    args = parser.parse_args()

    schemas = write_schemas()
    validations = {}
    for contract, filename, expected in [
        ("system_signal_v1", "system_signal_v1_example.csv", 24),
        ("tariff_v1", "tariff_v1_example.csv", 24),
        ("grid_state_v1", "grid_state_v1_example.csv", None),
        ("asset_exposure_v1", "asset_exposure_v1_example.csv", None),
    ]:
        report = validate_file(FIXTURE_DIR / filename, contract, expected_hours=expected)
        validations[contract] = {
            "valid": report.valid,
            "rows": report.rows,
            "errors": report.errors,
        }
        if not report.valid:
            report.raise_for_errors()

    parquet = {}
    for csv_name, pq_name in [
        ("system_signal_v1_example.csv", "system_signal_v1_example.parquet"),
        ("tariff_v1_example.csv", "tariff_v1_example.parquet"),
    ]:
        ok, error = materialize_parquet(csv_name, pq_name, args.require_parquet)
        parquet[pq_name] = {"created": ok, "error": error}

    report_payload = {
        "phase": "phase0_contracts",
        "status": "ok",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "schemas": schemas,
        "validations": validations,
        "parquet": parquet,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
