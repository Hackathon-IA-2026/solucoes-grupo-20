#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from predicta_climate.arco import ArcoClient


def main() -> None:
    with ArcoClient() as client:
        start, end = client.available_time_range("temperature")
        print("ARCO ERA5-Land acessível")
        print(f"temperature range: {start} -> {end}")


if __name__ == "__main__":
    main()
