# Predicta Web Studio v1.12.0

## Climate Store local-first

- histórico climático persistente em `data/climate_store/`;
- `local-first`: consulta local antes da rede e baixa apenas gaps;
- `local-only`: proíbe acesso à API histórica;
- atualização incremental do ano corrente: somente datas faltantes;
- migração automática dos caches v1.11;
- import/export do Climate Store;
- verificação de cobertura para saber quando é seguro operar em `local-only`;
- operacional H01–H24 usa baseline local e mantém rede apenas para forecast futuro.

Comandos principais:

```bash
python scripts/55_manage_climate_store.py seed-existing
python scripts/55_manage_climate_store.py status
python scripts/56_update_climate_store.py --start-year 2026 --end-year 2026
python scripts/57_verify_climate_store.py --start-year 2023 --end-year 2026
```
