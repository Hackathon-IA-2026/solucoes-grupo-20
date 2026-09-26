# Build validation — v0.4

Executado no ambiente de empacotamento em 2026-09-20:

- `python -m compileall -q predicta_climate scripts tests` — OK;
- `python scripts/61_run_climate_automation.py --help` — OK;
- `pytest -q` — **6 passed, 3 skipped**.

Os 3 testes pulados exigem `pyarrow`, que não está instalado neste ambiente e o
container de empacotamento não tem acesso de rede para instalá-lo. `pyarrow` é
dependência obrigatória em `requirements.txt` e `pyproject.toml`.

Os testes executados cobrem, entre outros:

- 2016/2017/2018 com quantidade correta de horas;
- conversões canônicas do cliente ARCO usando dados simulados;
- modo `AUTO` roteando diretamente para ARCO;
- detecção de HTTP 429 com fallback para ARCO;
- erro Open-Meteo não-429 não sendo mascarado.

O teste de retomada real por lote está presente em `tests/test_router_and_resume.py`
e será executado automaticamente quando `pyarrow` estiver disponível.
