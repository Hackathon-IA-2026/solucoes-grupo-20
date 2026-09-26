#!/usr/bin/env python3
from __future__ import annotations
import argparse
import importlib.util
import py_compile
import shutil
from datetime import datetime
from pathlib import Path

FILES = [
    'scripts/47_run_full_automation.py',
    'scripts/53_download_multiyear_grid_climate.py',
    'scripts/62_arco_openmeteo_proxy.py',
]


def main():
    p=argparse.ArgumentParser(description='Apply Predicta ARCO historical integration patch safely.')
    p.add_argument('--project', default='.', help='Predicta project root')
    a=p.parse_args()
    project=Path(a.project).expanduser().resolve()
    bundle=Path(__file__).resolve().parent
    if not (project/'scripts').is_dir():
        raise SystemExit(f'Projeto inválido: {project} não contém scripts/')
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_root=project/'outputs'/'patch_backups'/f'arco_{stamp}'
    backup_root.mkdir(parents=True, exist_ok=True)
    for rel in FILES:
        src=bundle/rel
        dst=project/rel
        if not src.exists():
            raise SystemExit(f'Arquivo do patch ausente: {src}')
        if dst.exists():
            bkp=backup_root/rel
            bkp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst,bkp)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src,dst)
        print(f'APPLIED {rel}')
    for rel in FILES:
        py_compile.compile(str(project/rel), doraise=True)
    print(f'BACKUP {backup_root}')
    missing=[]
    for mod in ('xarray','zarr','fsspec'):
        if importlib.util.find_spec(mod) is None:
            missing.append(mod)
    if missing:
        print('MISSING_PYTHON_PACKAGES ' + ' '.join(missing))
        print('Instale no .venv: pip install xarray zarr fsspec aiohttp')
    else:
        print('ARCO_PYTHON_DEPENDENCIES OK')
    print('PATCH_OK')

if __name__=='__main__':
    main()
