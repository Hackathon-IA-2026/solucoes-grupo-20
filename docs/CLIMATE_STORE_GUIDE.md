# Climate Store local — operação recomendada

O objetivo é que o Predicta **não consulte a API histórica durante treino, backtest ou cálculo de baseline** depois do backfill inicial.

## 1. Reaproveitar tudo que já foi baixado

```bash
python scripts/55_manage_climate_store.py seed-existing
```

Isso migra os caches de `data/raw/climate/annual_archive/` para `data/climate_store/` usando hardlink quando possível.

## 2. Completar o backfill uma única vez

Para o histórico 2023–2026:

```bash
python scripts/56_update_climate_store.py \
  --start-year 2023 \
  --end-year 2026
```

A rotina é LOCAL-FIRST. Ela lê o store, detecta gaps por célula/data e somente os gaps são solicitados. Se o ano corrente já estiver salvo até determinada data, a próxima execução solicita somente os dias posteriores disponíveis.

Se você tiver uma instância Open-Meteo local/self-hosted, passe seu endpoint em `--archive-url` para fazer o backfill sem quota da API pública.

## 3. Verificar se o histórico está completo

```bash
python scripts/57_verify_climate_store.py \
  --start-year 2023 \
  --end-year 2026
```

Só mude para `local-only` quando aparecer:

```text
READY_LOCAL_ONLY
```

## 4. Treinar sem API histórica

```bash
python scripts/47_run_full_automation.py \
  --start-year 2023 \
  --end-year 2026 \
  --climate-history-mode local-only
```

Nesse modo uma lacuna histórica gera erro explícito `MISSING_LOCAL_HISTORY`; o pipeline nunca faz fallback silencioso para internet.

## 5. Atualização periódica

Quando novos dias históricos estiverem disponíveis:

```bash
python scripts/56_update_climate_store.py \
  --start-year 2026 \
  --end-year 2026
```

O downloader compara a cobertura local e solicita apenas datas faltantes.

## 6. Operacional H01–H24

```bash
python scripts/50_refresh_operational.py
```

O baseline é lido do Climate Store em `local-only`. A rede fica reservada para o forecast meteorológico futuro e para a atualização do ONS.

## 7. Backup / compartilhamento

Exportar:

```bash
python scripts/55_manage_climate_store.py export \
  --output Predicta_Climate_Store.zip
```

Importar em outra máquina:

```bash
python scripts/55_manage_climate_store.py import \
  --source Predicta_Climate_Store.zip
```

Assim apenas uma máquina/equipe precisa fazer o backfill histórico completo.

## Diretório que deve ser preservado em upgrades

Nunca sobrescreva:

```text
data/climate_store/
```

Ele passa a ser um ativo persistente do projeto, assim como `models/` e os dados processados.
