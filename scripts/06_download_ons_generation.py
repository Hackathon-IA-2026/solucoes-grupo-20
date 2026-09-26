#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    p = argparse.ArgumentParser(description='Baixa um arquivo bruto de geração ONS sem alterá-lo. Informe a URL exata do recurso desejado.')
    p.add_argument('--url', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f'raw immutable: output already exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    req = Request(args.url, headers={'User-Agent':'Predicta-Hackathon/1.0'})
    with urlopen(req, timeout=120) as response, output.open('wb') as fh:
        fh.write(response.read())
    print(f'output={output.resolve()} bytes={output.stat().st_size}')

if __name__ == '__main__':
    main()
