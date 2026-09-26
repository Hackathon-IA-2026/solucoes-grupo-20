from __future__ import annotations

import json
import os
import shlex
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

import pandas as pd

from .arco import ArcoClient, CORE_GROUPS
from .points import SUBSYSTEM_FILE_NAMES, load_points_file
from .store import materialize_year


class HistoricalMode(str, Enum):
    AUTO = "auto"
    ARCO_ONLY = "arco_only"
    OPENMETEO_WITH_ARCO_FALLBACK = "openmeteo_with_arco_fallback"


@dataclass(frozen=True)
class RouterConfig:
    mode: HistoricalMode = HistoricalMode.AUTO
    fallback_http_codes: tuple[int, ...] = (429,)
    fallback_on_any_openmeteo_error: bool = False


def _contains_http_code(text: str, code: int) -> bool:
    lowered = text.lower()
    needles = (
        f"http {code}",
        f"http_status={code}",
        f"status {code}",
        f"status_code={code}",
        f"{code} too many requests" if code == 429 else str(code),
    )
    return any(n.lower() in lowered for n in needles) or bool(
        re.search(rf"(?<!\d){code}(?!\d)", lowered)
    )


def run_openmeteo_command(command: Sequence[str]) -> tuple[int, str]:
    """Run the existing project's Open-Meteo historical step, if supplied.

    stdout/stderr are streamed after completion and also returned for 429
    detection. No shell is used.
    """
    proc = subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = proc.stdout or ""
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    return proc.returncode, output


def load_openmeteo_command_from_env() -> list[str] | None:
    raw = os.environ.get("PREDICTA_OPENMETEO_HISTORICAL_COMMAND", "").strip()
    return shlex.split(raw) if raw else None


def load_router_config(path: Path | None = None) -> RouterConfig:
    if path is None or not path.exists():
        return RouterConfig()
    payload = json.loads(path.read_text(encoding="utf-8"))
    mode_value = os.environ.get(
        "PREDICTA_CLIMATE_HISTORICAL_MODE", payload.get("historical_mode", "auto")
    )
    return RouterConfig(
        mode=HistoricalMode(mode_value),
        fallback_http_codes=tuple(int(x) for x in payload.get("fallback_http_codes", [429])),
        fallback_on_any_openmeteo_error=bool(
            payload.get("fallback_on_any_openmeteo_error", False)
        ),
    )


def run_arco_historical(
    *,
    points_dir: Path,
    output_root: Path,
    subsystems: Sequence[str],
    start_year: int,
    end_year: int,
    groups: Sequence[str] = CORE_GROUPS,
    point_batch_size: int = 32,
    max_retries: int = 3,
    force: bool = False,
) -> list[dict]:
    points_by_subsystem = {}
    for subsystem in subsystems:
        path = points_dir / SUBSYSTEM_FILE_NAMES[subsystem]
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo de pontos ausente: {path}. Gere/forneça as listas 0,1° primeiro."
            )
        points_by_subsystem[subsystem] = load_points_file(path, subsystem=subsystem)
        print(f"{subsystem}: {len(points_by_subsystem[subsystem])} células")

    results: list[dict] = []
    with ArcoClient() as client:
        remote_start, remote_end = client.available_time_range("temperature")
        print(f"ARCO disponível: {remote_start} -> {remote_end}")
        for year in range(start_year, end_year + 1):
            # Full annual materialization requires the remote cube to contain Dec 31 23:00.
            required_end = pd.Timestamp(f"{year:04d}-12-31T23:00:00")
            if pd.Timestamp(remote_end) < required_end:
                raise RuntimeError(
                    f"ARCO ainda não contém o ano {year} completo (fim remoto={remote_end}). "
                    "Para baseline use apenas anos fechados; forecast operacional é outro backend."
                )
            for subsystem in subsystems:
                results.append(
                    materialize_year(
                        client=client,
                        points=points_by_subsystem[subsystem],
                        subsystem=subsystem,
                        year=year,
                        groups=groups,
                        output_root=output_root,
                        batch_size=point_batch_size,
                        max_retries=max_retries,
                        force=force,
                    )
                )
    return results


def run_historical_router(
    *,
    config: RouterConfig,
    points_dir: Path,
    output_root: Path,
    subsystems: Sequence[str],
    start_year: int,
    end_year: int,
    groups: Sequence[str] = CORE_GROUPS,
    point_batch_size: int = 32,
    max_retries: int = 3,
    force: bool = False,
    openmeteo_command: Sequence[str] | None = None,
) -> dict:
    """Route the historical climate step and return success only when complete.

    AUTO is intentionally ARCO-first: historical baseline/training should not
    consume Open-Meteo Archive quotas. Open-Meteo remains the forecast backend.
    """
    mode = config.mode
    if mode in (HistoricalMode.AUTO, HistoricalMode.ARCO_ONLY):
        print(f"Climate Router: mode={mode.value}; histórico -> ERA5-Land ARCO")
        results = run_arco_historical(
            points_dir=points_dir,
            output_root=output_root,
            subsystems=subsystems,
            start_year=start_year,
            end_year=end_year,
            groups=groups,
            point_batch_size=point_batch_size,
            max_retries=max_retries,
            force=force,
        )
        return {"backend": "arco", "fallback_used": False, "results": results}

    if mode != HistoricalMode.OPENMETEO_WITH_ARCO_FALLBACK:
        raise ValueError(f"Modo histórico desconhecido: {mode}")

    command = list(openmeteo_command or load_openmeteo_command_from_env() or [])
    if not command:
        print(
            "Climate Router: comando histórico Open-Meteo não configurado; "
            "indo diretamente para ARCO."
        )
        results = run_arco_historical(
            points_dir=points_dir,
            output_root=output_root,
            subsystems=subsystems,
            start_year=start_year,
            end_year=end_year,
            groups=groups,
            point_batch_size=point_batch_size,
            max_retries=max_retries,
            force=force,
        )
        return {"backend": "arco", "fallback_used": True, "reason": "openmeteo_command_missing", "results": results}

    print("Climate Router: tentando etapa histórica Open-Meteo existente...")
    returncode, output = run_openmeteo_command(command)
    if returncode == 0:
        print("Climate Router: Open-Meteo concluiu; devolvendo controle à automação.")
        return {"backend": "openmeteo", "fallback_used": False, "returncode": 0}

    matched = [
        code for code in config.fallback_http_codes if _contains_http_code(output, code)
    ]
    if matched or config.fallback_on_any_openmeteo_error:
        reason = f"HTTP {matched[0]}" if matched else f"openmeteo_exit_{returncode}"
        print(f"Climate Router: {reason}; fallback -> ERA5-Land ARCO")
        results = run_arco_historical(
            points_dir=points_dir,
            output_root=output_root,
            subsystems=subsystems,
            start_year=start_year,
            end_year=end_year,
            groups=groups,
            point_batch_size=point_batch_size,
            max_retries=max_retries,
            force=force,
        )
        print("Climate Router: fallback ARCO concluído; devolvendo controle à automação.")
        return {"backend": "arco", "fallback_used": True, "reason": reason, "results": results}

    raise RuntimeError(
        f"Etapa Open-Meteo falhou (exit={returncode}) sem condição de fallback configurada."
    )
