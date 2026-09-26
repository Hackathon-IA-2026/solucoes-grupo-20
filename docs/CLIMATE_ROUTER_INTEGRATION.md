# Integração da etapa N — Climate Router v0.4

## Objetivo

A etapa histórica da automação não deve mais depender do Open-Meteo Archive.
O novo ponto de entrada é:

```bash
python scripts/61_run_climate_automation.py \
  --subsystem all \
  --start-year 2016 \
  --end-year 2025
```

Em `configs/climate_router.json`, o padrão é:

```json
"historical_mode": "auto"
```

Nesse modo:

```text
etapa N
  ↓
Climate Router
  ↓
histórico? ──► ERA5-Land ARCO
  ↓
valida Climate Store
  ↓
exit code 0
  ↓
automação continua
```

O forecast H+1…H+24 continua fora desse backfill e deve permanecer no caminho
Open-Meteo/ECMWF operacional.

## O que ocorre ao clicar/rodar novamente

Para cada `subsistema × ano`:

1. se `YYYY.parquet` + manifest + quality report são compatíveis e `complete`, o ano é pulado;
2. se existe uma pasta `.YYYY.partial`, lotes já válidos são reutilizados;
3. somente lotes ausentes/corrompidos são buscados novamente;
4. o arquivo anual só é publicado depois da validação final;
5. sucesso retorna `0`, permitindo ao runner pai continuar.

Logo, **existência do arquivo não é suficiente para pular**.

## Compatibilidade com o runner antigo e HTTP 429

Se for necessário manter temporariamente a antiga etapa Open-Meteo histórica:

```bash
python scripts/61_run_climate_automation.py \
  --mode openmeteo_with_arco_fallback \
  --subsystem all \
  --start-year 2016 \
  --end-year 2025 \
  --openmeteo-command python CAMINHO_DO_RUNNER_ANTIGO.py ARG1 ARG2
```

Ou defina o comando:

```bash
export PREDICTA_OPENMETEO_HISTORICAL_COMMAND='python CAMINHO_DO_RUNNER_ANTIGO.py ...'
```

Comportamento:

```text
Open-Meteo histórico
   ├─ exit 0 ───────────────► continua automação
   └─ saída contém HTTP 429
             ↓
        ERA5-Land ARCO
             ↓
        backfill/retomada
             ↓
          exit 0
             ↓
        continua automação
```

Outros erros do Open-Meteo **não** são ocultados por padrão. Isso evita transformar
problemas de dados/código em fallback silencioso. Se deliberadamente necessário,
`fallback_on_any_openmeteo_error` pode ser alterado no JSON de configuração.

## Patch no runner real

Se o runner possui uma lista de etapas, substitua somente o comando da etapa
`N · clima multi-ano 0,1° + download resiliente` pelo comando do Climate Router.
Não altere a etapa de forecast.

Exemplo conceitual:

```python
STEPS = [
    # ...
    (
        "N · clima multi-ano 0,1° + download resiliente",
        [
            sys.executable,
            "scripts/61_run_climate_automation.py",
            "--subsystem", "all",
            "--start-year", "2016",
            "--end-year", "2025",
        ],
    ),
    # etapa seguinte permanece igual
]
```

Este ZIP não contém o runner gráfico/original da máquina local, portanto não é
possível editar fielmente um arquivo que não foi fornecido. O script acima é o
ponto de entrada pronto para substituir a etapa N no runner real.
