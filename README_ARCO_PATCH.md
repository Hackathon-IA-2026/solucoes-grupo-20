# Predicta — integração ARCO no runner real (patch v2)

Este patch foi construído sobre os arquivos reais `scripts/47_run_full_automation.py` e `scripts/53_download_multiyear_grid_climate.py` fornecidos em 20/09/2026.

## O que muda

- `47_run_full_automation.py` ganha `--climate-historical-backend`.
- O padrão é `auto`, que usa **ARCO para qualquer lacuna histórica**.
- O Climate Store existente continua `LOCAL FIRST`: arquivos já completos não são baixados de novo.
- `53_download_multiyear_grid_climate.py` continua chamando as funções atuais de `batch_openmeteo`, portanto **o layout de cache, manifests, checkpoints e os consumidores E2/E3 não mudam**.
- Para preservar esse contrato, `62_arco_openmeteo_proxy.py` expõe localmente uma resposta compatível com a Archive API, mas lê os dados diretamente dos datacubes ARCO.
- Open-Meteo continua sendo usado pela etapa operacional de forecast (`48_build_operational_weather.py`); a troca é somente do histórico.

## Fontes no modo ARCO

- Temperatura/dewpoint: ERA5-Land ARCO, 0,1°.
- Precipitação: ERA5-Land ARCO, 0,1°.
- U/V e velocidade do vento: ERA5-Land ARCO, 0,1°.
- Radiação: ERA5-Land ARCO, 0,1°.
- Rajada: ERA5 single-level ARCO, 0,25°, vizinho mais próximo de cada célula Predicta. Não há substituição silenciosa por vento sustentado.

## Aplicação

Com a automação antiga interrompida (`Ctrl+C`), descompacte este bundle e execute:

```bash
cd ~/Área\ de\ Trabalho/predicta
source .venv/bin/activate
python /CAMINHO/DO/BUNDLE/apply_patch.py --project .
pip install -r /CAMINHO/DO/BUNDLE/requirements_arco.txt
```

O instalador salva backup dos scripts atuais em:

```text
outputs/patch_backups/arco_YYYYMMDD_HHMMSS/
```

## Execução recomendada

O padrão já é ARCO-first para histórico:

```bash
python scripts/47_run_full_automation.py
```

ou explicitamente:

```bash
python scripts/47_run_full_automation.py \
  --climate-historical-backend auto
```

### Modos

```text
auto                     cache local -> ARCO para lacunas (RECOMENDADO)
arco                     equivalente a ARCO-first explícito
openmeteo                comportamento legado; 429 pode deferir
openmeteo-fallback-arco  tenta legado; ao deferir por rate-limit, reinicia o passe com ARCO
```

## O que esperar no log

No começo de cada região, em `auto`:

```text
=== N · clima multi-ano 0,1° · ARCO AUTO ===
PREDICTA_ARCO_START: ... 62_arco_openmeteo_proxy.py ...
PREDICTA_ARCO_READY: http://127.0.0.1:XXXXX/v1/archive
PREDICTA_CLIMATE_BACKEND: histórico faltante -> ERA5-Land/ERA5 ARCO
```

Anos/pontos já presentes continuam como `cache_hits`. Quando faltar algo, aparecem mensagens:

```text
ARCO_PROXY_OK points=... dates=... hourly=... daily=...
```

**Observação:** as funções legadas podem continuar imprimindo frases como `Open-Meteo E3 baseline_temperature ...`. Esse texto é apenas o nome/log interno da camada existente. Se o log tiver `PREDICTA_ARCO_READY` e `ARCO_PROXY_OK`, a requisição histórica foi atendida localmente pelo adaptador ARCO, não pela API pública do Open-Meteo.

## Ano corrente

O script 53 continua calculando o limite histórico com `archive_lag_days=5`. Portanto 2026 é solicitado apenas até a data disponível de reanálise, em vez de exigir 31/12/2026.

## Depois do clima

Nada muda na sequência do runner: ele executa `32_prepare_e2_zone_climate.py`, `54_prepare_multiyear_e3.py`, combina regiões, valida Ridge e XGBoost, treina/congela os dois candidatos por subsistema, seleciona por WAPE e grava `models/demand/operational_registry.json`. Em seguida, se não houver `--skip-operational`, roda o forecast H01–H24 e o `system_signal_v1`.


## Validação

Veja `VALIDATION.md`. Este patch foi compilado e o contrato de conversão do proxy foi testado offline antes do empacotamento.
