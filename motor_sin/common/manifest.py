from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_commit(root: str | Path = '.') -> str | None:
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_manifest(*, run_id: str, issue_time: str, forecast_horizon: int, baseline_period: str | None,
                   data_sources: list[str], contract_versions: dict[str, str], config_versions: dict[str, str] | None = None,
                   root: str | Path = '.') -> dict:
    return {
        'run_id': run_id,
        'issue_time': issue_time,
        'forecast_horizon': int(forecast_horizon),
        'model_version': 'predicta_mvp_v1',
        'contract_versions': contract_versions,
        'config_versions': config_versions or {},
        'data_sources': data_sources,
        'source_freshness': {},
        'baseline_period': baseline_period,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'git_commit': git_commit(root),
    }
