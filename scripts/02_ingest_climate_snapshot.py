from __future__ import annotations

import argparse
import json
from pathlib import Path

from motor_sin.climate.raw import ingest_local_openmeteo_json
from motor_sin.common.provenance import utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import local Open-Meteo hourly JSON into immutable Predicta RAW storage."
    )
    parser.add_argument("inputs", nargs="+", help="Direct API JSON or OpenMeteo/Predicta RAW wrapper JSON")
    parser.add_argument("--raw-dir", default="data/raw/climate/openmeteo")
    parser.add_argument("--source-service", default="historical")
    parser.add_argument("--manifest", default="data/interim/climate/ingest_manifest.json")
    args = parser.parse_args()

    results = []
    for item in args.inputs:
        results.extend(
            ingest_local_openmeteo_json(
                item,
                raw_directory=args.raw_dir,
                source_service=args.source_service,
            )
        )
    manifest = {
        "schema_version": "climate_ingest_manifest_v1",
        "created_at_utc": utc_now_iso(),
        "source": "open-meteo",
        "results": results,
    }
    path = Path(args.manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
