# Fixtures

As fixtures desta pasta são **sintéticas** e existem apenas para congelar e testar contratos.

Arquivos fonte versionados:

- `grid_state_v1_example.csv`
- `asset_exposure_v1_example.csv`
- `system_signal_v1_example.csv`
- `tariff_v1_example.csv`
- `tariff_base_example.csv`

Os dois `.parquet` principais são gerados localmente por:

```bash
python scripts/00_bootstrap_phase0.py --require-parquet
```

Isso evita versionar binários reprodutíveis e mantém a fixture legível em code review.
