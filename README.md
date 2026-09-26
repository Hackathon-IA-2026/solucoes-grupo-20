# Predicta — Climate Router / ERA5-Land ARCO v0.4

Esta versão transforma a antiga etapa de clima histórico em um **Climate Router**
resiliente.

## Executar o Django com uv

Instale as dependências e prepare o banco local:

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py check
```

Inicie o Studio Django e a REST API:

```bash
uv run python manage.py runserver 127.0.0.1:8000
```

Com o servidor ativo, acesse:

- Studio web: <http://127.0.0.1:8000/>
- Swagger UI: <http://127.0.0.1:8000/api/docs/>
- OpenAPI schema: <http://127.0.0.1:8000/api/schema/>

A API versionada está disponível em `/api/v1/`. A simulação do Produto usa
`POST /api/v1/simulations/`; os payloads e endpoints auxiliares estão documentados
em `docs/PREDICTA_API.md` e no Swagger.

```text
HISTÓRICO / BASELINE / TREINO                 FUTURO OPERACIONAL
ERA5-Land ARCO                                Open-Meteo / ECMWF forecast
0,1° · horário · histórico longo              H+1…H+24 no issue-time
          │                                             │
          └──────────────► Motor SIN ◄──────────────────┘
```

## O comportamento da automação agora

O ponto de entrada da etapa histórica é:

```bash
python scripts/61_run_climate_automation.py \
  --subsystem all \
  --start-year 2016 \
  --end-year 2025
```

O padrão em `configs/climate_router.json` é `auto`:

```text
N · clima multi-ano 0,1°
          ↓
     Climate Router
          ↓
     ERA5-Land ARCO
          ↓
  Climate Store validado
          ↓
       exit code 0
          ↓
  automação segue adiante
```

**AUTO não tenta o Open-Meteo Archive**, portanto não consome sua cota histórica e
não fica preso em 429. Open-Meteo/ECMWF continua sendo o caminho para forecast.

## Compatibilidade: Open-Meteo → 429 → ARCO

Para um runner antigo que ainda chama a etapa histórica Open-Meteo:

```bash
python scripts/61_run_climate_automation.py \
  --mode openmeteo_with_arco_fallback \
  --subsystem all \
  --start-year 2016 \
  --end-year 2025 \
  --openmeteo-command python CAMINHO_DO_RUNNER_ANTIGO.py ...
```

Se a saída do comando contém HTTP 429, o router executa o ARCO. Quando o ARCO
termina, o router retorna **exit code 0**, então o runner pai continua para a
próxima etapa.

Outros erros não são mascarados por padrão.

## Retomada real

A v0.4 retoma no nível de lote de células:

```text
data/climate_store/seco/hourly/
├── .2018.partial/
│   ├── part-00000.parquet  ✔
│   ├── part-00001.parquet  ✔
│   ├── part-00002.parquet  ← próximo
│   └── state.json
└── 2018.manifest.json
```

Se a conexão cair, a execução seguinte valida e reutiliza os lotes já escritos.
Ela não recomeça o ano inteiro.

Um `YYYY.parquet` só é pulado quando existem e concordam:

- Parquet anual;
- manifest `status=complete`;
- quality report `status=complete`;
- mesmos grupos climáticos;
- mesma lista de células (fingerprint);
- horas esperadas por célula.

Para 2016 são 8.784 horas; 2017/2018 têm 8.760.

## Autenticação

O código procura a chave nesta ordem:

1. `CDSAPI_KEY`;
2. `~/.cdsapirc`.

Teste:

```bash
python scripts/56_test_arco_access.py
```

## Primeiro teste controlado

```bash
python scripts/61_run_climate_automation.py \
  --subsystem seco \
  --start-year 2025 \
  --end-year 2025 \
  --groups temperature \
  --output-root data/climate_store_trial
```

Depois, baseline completo de 2026:

```bash
python scripts/61_run_climate_automation.py \
  --subsystem all \
  --start-year 2016 \
  --end-year 2025
```

## Variáveis históricas

ARCO:

- temperatura 2 m e ponto de orvalho;
- precipitação;
- U/V do vento 10 m;
- radiação solar descendente.

Derivados:

- °C;
- precipitação em mm;
- `sqrt(u10² + v10²)`;
- radiação média horária W/m²;
- agregações diárias.

**Rajada não é substituída silenciosamente**; permanece uma variável opcional de
fonte secundária.

## Arquivos principais

```text
predicta_climate/
├── arco.py       # acesso Zarr ARCO
├── store.py      # materialização, retomada, validação
├── router.py     # AUTO e fallback 429
├── points.py
├── quality.py
└── daily.py

scripts/
├── 56_test_arco_access.py
├── 57_build_climate_points.py
├── 58_backfill_climate_store_arco.py
├── 59_validate_climate_store.py
├── 60_build_daily_climate_store.py
└── 61_run_climate_automation.py
```

A integração exata com o runner gráfico/CLI original está documentada em
`docs/CLIMATE_ROUTER_INTEGRATION.md`. O runner original não estava entre os
arquivos fornecidos, então este ZIP entrega um ponto de entrada substituível sem
inventar o código ausente.
