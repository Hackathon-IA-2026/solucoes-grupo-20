# Predicta Web Studio v1.6

A v1.6 reorganiza o Django para refletir o ciclo real do MVP, separando claramente **dados**, **features**, **modelagem**, **validação**, **deployment** e **produto**.

## Fluxo da interface

```text
Dados
  ├─ histórico multi-ano ONS
  └─ mapa de concessões + tarifas ANEEL por CNPJ
        ↓
Features
  ├─ E1: histórico + calendário
  ├─ E2: + clima bruto
  └─ E3: + anomalias/eventos
        ↓
Modelagem
  ├─ Ridge
  └─ XGBoost
        ↓
Validação
  ├─ MAE
  ├─ RMSE
  ├─ WAPE
  ├─ cobertura p10-p90
  ├─ H01-H24
  └─ realizado × previsto
        ↓
Modelos
  ├─ congelar H01-H24
  └─ promover modelo ativo
        ↓
Produto
  localização no mapa real
        ↓
  CNPJ da concessão
        ↓
  tarifa ANEEL vigente na data do sinal
        ↓
  system_signal_v1
        ↓
  tarifa dinâmica Predicta
```

## XGBoost

XGBoost foi implementado como segundo algoritmo do Motor de Demanda. Ridge e XGBoost usam:

- a mesma matriz de features;
- o mesmo backtest temporal fixed-origin;
- os mesmos horizontes H01-H24;
- a mesma janela de calibração dos intervalos p10-p90;
- o mesmo holdout.

Isso permite comparar algoritmos sem mudar simultaneamente a metodologia.

Instalação:

```bash
pip install -e ".[dev,web,ml]"
```

Na tela **Modelagem**, escolha `Ridge` ou `XGBoost`. Para XGBoost, a interface expõe os principais hiperparâmetros do MVP: `n_estimators`, `max_depth`, `learning_rate`, `subsample` e `colsample_bytree`.

## Histórico multi-ano ONS

A tela **Dados** permite escolher um intervalo de anos. O script `45_sync_ons_history.py`:

1. reutiliza RAW já baixado;
2. baixa somente anos ausentes;
3. normaliza cada ano;
4. concatena a série;
5. rejeita conflitos de timestamps;
6. materializa novamente `load_hourly.parquet` e `supply_by_subsystem_hourly.parquet`.

Exemplo:

```bash
python scripts/45_sync_ons_history.py \
  --start-year 2021 \
  --end-year 2025 \
  --source-timezone America/Sao_Paulo
```

**Importante:** E1 pode usar todo o histórico ONS. E2/E3 exigem também cobertura climática para os mesmos timestamps. Se o clima existir apenas em 2025, adicionar ONS 2021-2024 não cria features climáticas para esses anos; a interface mostra a cobertura efetiva.

## Mapa real e tarifa por localização

A v1.6 usa os dois datasets fornecidos ao projeto:

- `areas_distribuicao_brasil.geojson` — 103 áreas de concessão com Polygon/MultiPolygon;
- `tarifas-homologadas-distribuidoras-energia-eletrica.csv` — histórico de tarifas homologadas.

A chave de relacionamento é:

```text
GeoJSON.properties.cnpj
         ↕
CSV.NumCNPJDistribuidora
```

O projeto inclui:

```text
references/areas_distribuicao_brasil_sirgas2000.geojson
references/tarifas_homologadas_distribuidoras_energia_eletrica.csv.gz
configs/distributor_areas_wgs84.geojson
configs/distributor_catalog.csv
```

O GeoJSON original foi fornecido em SIRGAS 2000 (EPSG:4674) e a cópia usada no navegador foi convertida para WGS84/EPSG:4326.

Preparação:

```bash
python scripts/44_prepare_tariff_geography.py
```

A etapa:

- lê o CSV tarifário completo;
- mantém `Tarifa de Aplicação`;
- separa componentes volumétricos de componentes em R$/kW;
- normaliza TE/TUSD para R$/kWh;
- relaciona as áreas por CNPJ;
- gera catálogo e mapa processados.

No dataset fornecido, o smoke test encontrou histórico tarifário para **103/103** áreas geográficas.

### Uso do Produto

1. Clique em uma área real no mapa ou busque a distribuidora.
2. O sistema obtém o CNPJ da concessão.
3. O CNPJ filtra os perfis tarifários ANEEL vigentes na data do `system_signal_v1`.
4. Selecione um perfil volumétrico compatível.
5. Informe consumo mensal e forma da curva.
6. O Motor 2 compara tarifa-base ANEEL e tarifa dinâmica experimental nas mesmas 24 horas.

A interface mostra TE, TUSD, TE+TUSD e a data de referência da tarifa.

### Escopo tarifário do MVP

A comparação **não é a fatura completa**. O MVP usa TE+TUSD volumétricas. Impostos, CIP, bandeiras e componentes de demanda em R$/kW podem ficar fora.

Tarifas duplicadas só são colapsadas quando são economicamente idênticas. Se houver TE/TUSD conflitantes para a mesma seleção, o Motor 2 falha explicitamente em vez de fazer média silenciosa.

## Associação distribuidora → subsistema

A área geográfica é real, mas o campo `subsystem_id` usado para colorir o mapa e selecionar o sinal sistêmico ainda é uma **proxy do MVP derivada da macrorregião geográfica**. Isso está marcado como:

```text
GEOGRAPHIC_REGION_PROXY_MVP
```

Não deve ser apresentado como fronteira elétrica oficial do ONS. Quando houver uma tabela autoritativa distribuidora → subsistema, ela deverá substituir apenas essa associação; os polígonos de concessão e a relação por CNPJ permanecem válidos.

## Modelagem e validação

A nova tela **Modelagem** executa uma configuração por vez e não sobrescreve automaticamente outras validações. Cada execução recebe um identificador derivado da configuração, permitindo comparar, por exemplo:

```text
E1 + Ridge + 2024-2025
E1 + XGBoost + 2024-2025
E3 + Ridge + 2025
E3 + XGBoost + 2025
```

A tela **Validação** apresenta:

- ranking por WAPE agregado;
- MAE;
- RMSE;
- cobertura p10-p90;
- WAPE H01-H24;
- curva realizado × p50, p10 e p90;
- período de carga e clima efetivamente utilizado.

Depois de escolher uma configuração, use **Modelos** para congelar os 24 artefatos H01-H24 e então promovê-los como modelo ativo.

## Subir a aplicação

```bash
pip install -e ".[dev,web,ml]"
python manage.py migrate
python manage.py check
pytest -q
python manage.py test web.studio
python manage.py runserver 127.0.0.1:8000
```

Acesse:

```text
http://127.0.0.1:8000/
```
