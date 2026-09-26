# Predicta Web Studio v1.5.1 — hotfix

## Correções

- Corrige `forecast_active.params`, que na v1.5.0 era um `Param` isolado em vez de uma tupla de `Param`. Isso fazia a página **Pipeline** falhar no template Django com `TypeError: 'Param' object is not iterable`.
- Adiciona teste regressivo garantindo que `Stage.params` seja sempre uma tupla.
- Troca construções `pd.Timedelta(...)` de hotspots do pipeline por `datetime.timedelta(...)` para reduzir o grande volume de `DeprecationWarning` observado com combinações recentes de pandas/numpy.
- Versão do pacote atualizada para `1.5.1`.

## Validação local recomendada

```bash
python manage.py check
pytest -q
python manage.py test web.studio
```
