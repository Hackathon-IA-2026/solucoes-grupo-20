# Predicta — Plano Prático de Implementação v0.2

**Escopo:** Brasil, com foco operacional no Sistema Interligado Nacional (SIN)  
**Base técnica:** Especificação Técnica Predicta v0.2  
**Objetivo desta etapa:** organizar a implementação em Python antes da integração com Django  
**Arquitetura:** dois motores independentes, integrados exclusivamente por contratos de dados versionados

---

## 1. Objetivo do plano

Este documento transforma a especificação técnica v0.2 em uma sequência prática de implementação.

A solução será construída em duas frentes independentes:

1. **Motor 1 — Inteligência Físico-Climática do SIN**
   - clima;
   - baseline climático regional;
   - incidentes climáticos;
   - carga/demanda;
   - geração por usina e tecnologia;
   - ativos de transmissão;
   - exposição de ativos;
   - sinais agregados por subsistema e SIN.

2. **Motor 2 — Sinal Tarifário Dinâmico**
   - identificação da tarifa-base;
   - associação entre perfil, posto e vigência;
   - consumo do sinal agregado produzido pelo Motor 1;
   - cálculo do fator tarifário experimental;
   - aplicação de limites e proteções;
   - produção da tarifa simulada.

O **Motor 2 não acessará dados ERA5, modelos de ML, geometrias, usinas ou infraestrutura do Motor 1**.

O merge entre os dois motores será garantido pelo contrato:

```text
system_signal_v1
```

A aplicação Django será iniciada somente quando os dois motores estiverem funcionando de forma independente em scripts Python.

---

# 2. Regra principal de desenvolvimento

A ordem será:

```text
CONTRATOS
    ↓
DADOS BRUTOS
    ↓
NORMALIZAÇÃO
    ↓
CLIMA + REDE + GERAÇÃO + DEMANDA
    ↓
MOTOR 1
    ↓
system_signal_v1
    ↓
MOTOR 2
    ↓
tariff_v1
    ↓
DJANGO
```

Não começar pelo frontend.

Não começar treinando vários modelos.

Não processar dez anos de ERA5-Land para todo o Brasil antes de validar o pipeline em um recorte pequeno.

---

# 3. Escopo espacial e temporal

## 3.1 Escopo geográfico

Cobertura de produto:

```text
Brasil
└── foco no SIN
    ├── Norte
    ├── Nordeste
    ├── Sul
    └── Sudeste/Centro-Oeste
```

A classificação por subsistema deve usar o identificador fornecido pelo ONS.

A geometria desenhada no mapa serve para visualização e **não substitui a classificação elétrica oficial do ONS**.

Ativos encontrados fora do SIN devem ser preservados com flag:

```text
outside_sin_scope = true
```

---

## 3.2 Grade espacial canônica

A grade espacial de análise será a mesma resolução do ERA5-Land:

```text
0,1° latitude × 0,1° longitude
EPSG:4326
```

Essa grade é um **índice espacial comum**.

Ela não significa que todos os dados elétricos possuem resolução de 0,1°.

### Pode ser colocado diretamente na grade

- temperatura;
- precipitação;
- vento;
- radiação;
- incidentes climáticos;
- usinas georreferenciadas;
- subestações;
- linhas de transmissão quando houver geometria.

### Não deve ser artificialmente distribuído na grade

- carga ONS por subsistema;
- geração que só possua localização regional;
- grandezas agregadas sem localização confiável.

---

## 3.3 Resolução temporal

Padrão interno:

```text
UTC timezone-aware
```

Contrato principal:

```text
1 hora
```

Resoluções nativas podem ser mantidas em `raw`.

Exemplos:

| Fonte | Resolução nativa | Resolução do contrato |
|---|---:|---:|
| ERA5-Land | 1 h | 1 h |
| Geração por Usina ONS | 1 h | 1 h |
| Carga ONS | 30 min / conforme fonte | 1 h |
| DESSEM | 30 min | 1 h no contrato |
| Tarifa | vigência/posto | 1 h após regra de posto |

Hora local será calculada somente quando necessária para:

- calendário;
- posto tarifário;
- interface;
- explicações ao usuário.

---

# 4. Estrutura inicial do repositório

Criar o repositório nesta estrutura antes de desenvolver lógica de negócio:

```text
predicta/
│
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── configs/
│   ├── project.yaml
│   ├── climate.yaml
│   ├── incidents.yaml
│   ├── demand.yaml
│   ├── assets.yaml
│   └── tariff.yaml
│
├── contracts/
│   ├── schemas/
│   ├── fixtures/
│   ├── validators/
│   └── enums.py
│
├── motor_sin/
│   ├── climate/
│   ├── demand/
│   ├── generation/
│   ├── grid/
│   ├── assets/
│   └── signals/
│
├── motor_tarifa/
│   ├── profiles/
│   ├── base_tariff/
│   ├── signal/
│   ├── guardrails/
│   └── billing/
│
├── scripts/
│
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
│
├── models/
│
├── outputs/
│   ├── contracts/
│   ├── reports/
│   ├── maps/
│   └── metrics/
│
├── tests/
│   ├── unit/
│   ├── contracts/
│   └── integration/
│
└── web/
    └── README.md
```

Regra:

```text
data/raw/ nunca é alterado depois da ingestão.
```

Transformações sempre produzem um novo artefato.

---

# 5. Fase 0 — Congelar contratos antes de implementar os motores

## Objetivo

Garantir que as duas frentes possam evoluir separadamente.

## Criar quatro contratos

### 5.1 `grid_state_v1`

Representa o estado físico-climático por célula e hora.

Campos mínimos:

```text
schema_version
run_id
interval_start_utc
cell_id
lat_center
lon_center

temperature_2m
temperature_anomaly
temperature_percentile

precipitation
precipitation_percentile

wind_speed
wind_percentile

solar_radiation
solar_percentile

heat_incident_score
cold_incident_score
rain_incident_score
wind_incident_score
solar_deficit_score

capacity_by_type_json
generation_by_type_json

substation_count
hub_max

transmission_exposure

data_quality
```

---

### 5.2 `asset_exposure_v1`

Representa ativos expostos a incidentes.

Campos mínimos:

```text
schema_version
run_id
interval_start_utc

asset_id
asset_type

cell_id
geometry_quality

incident_type
incident_score
exposure_reason

generation_type
capacity_mw

hub_score
voltage_kv
transformer_mva

quality_flags
```

---

### 5.3 `system_signal_v1`

É a **única entrada permitida no Motor 2**.

Campos mínimos:

```text
schema_version
run_id
interval_start_utc

zone_type
zone_id

demand_p10_mw
demand_p50_mw
demand_p90_mw

demand_percentile
supply_pressure
climate_exposure

generation_by_type_json
main_drivers_json

data_freshness_ok
quality_flags
```

Valores iniciais de `zone_type`:

```text
SUBSYSTEM
SIN
```

Futuro:

```text
DISTRIBUTOR
```

---

### 5.4 `tariff_v1`

Saída do Motor 2.

Campos recomendados:

```text
schema_version
run_id
interval_start_utc

distributor_id
tariff_profile_id

zone_type
zone_id

base_te_rs_kwh
base_tusd_rs_kwh
base_total_rs_kwh

demand_pressure
supply_pressure
economic_signal

raw_multiplier
final_multiplier

dynamic_tariff_rs_kwh

floor_applied
cap_applied
ramp_applied
neutrality_adjustment
fallback_applied

reason_codes
quality_flags
```

---

## 5.5 Criar fixtures imediatamente

Antes dos motores reais, criar:

```text
contracts/fixtures/system_signal_v1_example.parquet
contracts/fixtures/tariff_base_example.csv
```

O Motor 2 deve funcionar utilizando apenas essa fixture.

---

## Definition of Done da Fase 0

- [ ] schemas definidos;
- [ ] fixtures criadas;
- [ ] validadores funcionando;
- [ ] testes detectam coluna ausente;
- [ ] testes detectam timestamp duplicado;
- [ ] testes detectam valores fora de `[0,1]`;
- [ ] mudança incompatível exige nova versão do contrato.

---

# 6. Fase 1 — Criar a grade espacial nacional

## Objetivo

Criar o sistema de referência comum do produto.

Script:

```text
scripts/01_build_grid.py
```

Entrada:

```text
bounding box do Brasil
máscara territorial
```

Saída:

```text
data/processed/grid/brazil_grid_01deg.parquet
```

Campos:

```text
cell_id
lat_min
lat_max
lon_min
lon_max
lat_center
lon_center
inside_brazil
```

Implementar `cell_id` de forma determinística.

Exemplo conceitual:

```text
lat_index = floor((lat + 90) / 0.1)
lon_index = floor((lon + 180) / 0.1)
```

Nunca usar o texto da coordenada como identificador primário.

---

## Testes

- [ ] mesma coordenada sempre retorna a mesma célula;
- [ ] coordenadas limítrofes funcionam;
- [ ] nenhuma célula possui `cell_id` duplicado;
- [ ] CRS documentado como EPSG:4326.

---

# 7. Fase 2 — Ingestão climática

## Objetivo

Construir o pipeline climático de forma independente do restante do sistema.

Inicialmente trabalhar com:

```text
1 ano
+
um recorte espacial pequeno
```

Depois escalar.

Variáveis mínimas:

```text
temperatura 2 m
ponto de orvalho
precipitação
vento 10 m
radiação solar
```

Script de ingestão:

```text
scripts/02_download_era5_land.py
```

Script de normalização:

```text
scripts/03_prepare_climate.py
```

Saída normalizada:

```text
data/processed/climate/climate_hourly/
```

Particionar preferencialmente por:

```text
year
month
```

Campos:

```text
interval_start_utc
cell_id

temperature_2m
dewpoint_2m
precipitation
wind_speed_10m
solar_radiation

source
```

---

# 8. Fase 3 — Baseline climático regional de 10 anos

Esta é uma das partes mais importantes do projeto.

## Regra

Para analisar um instante no ano `Y`:

```text
baseline = Y-10 até Y-1
```

Exemplo:

```text
evento em 2026
baseline = 2016–2025
```

Não incluir 2026 no baseline.

---

## Baseline por

```text
célula
+
variável
+
hora do dia
+
época do ano
```

Para sazonalidade, usar janela:

```text
dia do ano ±15 dias
```

---

## Estatísticas mínimas

Para cada grupo calcular:

```text
median
p01
p05
p10
p25
p75
p90
p95
p99
IQR
sample_count
```

Saída:

```text
data/processed/climate/baseline_10y/
```

---

## Equações

### Anomalia

```text
anomaly = valor_atual - mediana_baseline
```

### z-score robusto

```text
robust_z =
(valor_atual - mediana_baseline)
/
max(IQR / 1.349, epsilon)
```

### Percentil

```text
percentile =
posição_empírica(valor_atual dentro do baseline)
```

---

## Script

```text
scripts/04_build_climate_baseline.py
```

---

## Primeiro teste

Antes do Brasil inteiro:

```text
1 ano alvo
1 região
1 variável
```

Somente depois validar todos os casos e escalar para:

```text
10 anos
Brasil/SIN
todas as variáveis
```

---

# 9. Fase 4 — Detectar incidentes climáticos

Script:

```text
scripts/05_detect_climate_incidents.py
```

Inicialmente implementar apenas regras transparentes.

## Calor extremo

```text
temperature_percentile >= 0.95
```

Se:

```text
>= 0.99
```

marcar severidade maior.

---

## Frio extremo

```text
temperature_percentile <= 0.05
```

---

## Chuva intensa

Regra:

```text
precipitation_percentile >= 0.95
AND
precipitation > absolute_minimum
```

O limiar absoluto deve estar em `configs/incidents.yaml`.

---

## Vento forte

```text
wind_percentile >= 0.95
```

---

## Déficit solar

Somente em horas solares:

```text
solar_percentile <= 0.05
```

---

## Score normalizado

Para cauda superior:

```text
score = clip(
    (percentile - threshold) / (1 - threshold),
    0,
    1
)
```

---

## Saída

```text
data/processed/climate/incidents_hourly.parquet
```

Campos:

```text
interval_start_utc
cell_id
incident_type
incident_score
severity
baseline_year_start
baseline_year_end
```

---

# 10. Fase 5 — Ingestão da geração ONS

## Fontes centrais

1. Geração por Usina em Base Horária;
2. Capacidade Instalada de Geração.

Scripts:

```text
scripts/06_download_ons_generation.py
scripts/07_prepare_generation.py
```

---

## Preservar tipos originais

Não limitar o código a uma lista fixa.

Hoje o projeto considera pelo menos:

```text
EOLIELÉTRICA
FOTOVOLTAICA
HIDROELÉTRICA
NUCLEAR
TÉRMICA
```

Mas qualquer novo `nom_tipousina` deve:

```text
ser preservado
+
ser sinalizado no relatório de qualidade
```

---

## Saída principal

```text
data/processed/generation/generation_hourly.parquet
```

Campos mínimos:

```text
interval_start_utc
plant_id
plant_name
generation_type
subsystem_id
state
generation_mw
source
```

---

# 11. Fase 6 — Cadastro e geocodificação das usinas

Objetivo:

```text
plant_id
    ↓
latitude
longitude
    ↓
cell_id
```

Prioridade de chave:

```text
1. CEG
2. identificador ONS
3. nome tratado
```

Nome deve ser último recurso.

Fonte complementar:

```text
ANEEL SIGA
```

---

## Qualidade da localização

Criar:

```text
location_quality
```

Valores:

```text
A = coordenada oficial/cadastral
B = centroide aproximado obtido via SIGA
C = grupo/conjunto sem ponto individual confiável
D = somente UF/subsistema
```

Registros `C` e `D` não devem receber uma coordenada falsa.

---

## Script

```text
scripts/08_geocode_generation_assets.py
```

Saída:

```text
data/processed/assets/generation_assets.parquet
```

---

# 12. Fase 7 — Centros de geração

Para cada célula e tecnologia:

```text
capacity_cell_type =
soma(capacidade das usinas na célula)
```

Depois:

```text
generation_center_score =
percentile_rank(capacity_cell_type)
```

Regra inicial de destaque:

```text
score >= p90
```

O limiar deve ser configurável.

Saída:

```text
data/processed/assets/generation_centers.parquet
```

Isso permite responder:

> O incidente climático ocorre em uma região com concentração relevante de geração solar, eólica, térmica, hidráulica etc.?

---

# 13. Fase 8 — Subestações, transformação e linhas de transmissão

## 13.1 Subestações

Ingerir cadastro ONS.

Script:

```text
scripts/09_prepare_substations.py
```

Saída:

```text
data/processed/assets/substations.parquet
```

Campos:

```text
substation_id
name
lat
lon
cell_id
voltage_kv
subsystem_id
```

---

## 13.2 Capacidade de transformação

Integrar quando houver chave confiável.

Calcular por subestação:

```text
transformer_mva
```

---

## 13.3 Linhas de transmissão

Script:

```text
scripts/10_prepare_transmission_lines.py
```

Campos:

```text
line_id
from_substation
to_substation
voltage_kv
length_km
geometry
geometry_quality
```

Valores possíveis de `geometry_quality`:

```text
REAL
SCHEMATIC
UNKNOWN
```

Linha reta entre subestações só pode ser usada quando marcada:

```text
SCHEMATIC
```

Nunca apresentar km de exposição como rota real quando a geometria for esquemática.

---

# 14. Fase 9 — Calcular hubs de transmissão

Criar um score analítico.

Equação:

```text
hub_score =
w1 * norm(log(1 + MVA))
+
w2 * norm(degree)
+
w3 * norm(max_kV)
+
w4 * norm(betweenness)
```

Pesos ficam em:

```text
configs/assets.yaml
```

`betweenness` pode ficar de fora no primeiro MVP.

Se algum componente estiver ausente:

```text
renormalizar os pesos restantes
```

e registrar:

```text
hub_components_used
```

Importante:

> `hub_score` é prioridade analítica/cartográfica, não classificação oficial de criticidade do ONS.

---

# 15. Fase 10 — Cruzar clima com ativos elétricos

Esta fase cria o primeiro produto visual relevante.

## 15.1 Usinas

Para cada usina:

```text
asset cell
+
incident cell
+
mesma hora
```

Resultado:

```text
asset_exposure
```

---

## 15.2 Subestações

Mesma lógica:

```text
substation cell
+
incidente
```

---

## 15.3 Linhas

Quando houver geometria real:

```text
LineExposure =
comprimento da linha dentro de células severas
/
comprimento total da linha
```

Quando a geometria for esquemática, produzir apenas indicador qualitativo.

---

## 15.4 Linguagem

Permitido:

```text
"incidente climático coincide com usina"
"ativo exposto"
"centro gerador em área de calor extremo"
"linha cruza área de vento forte"
```

Não afirmar automaticamente:

```text
"usina falhou"
"geração foi reduzida"
"linha sofreu dano"
```

Sem evidência operacional adicional.

---

## Script

```text
scripts/11_build_asset_exposure.py
```

Saída:

```text
outputs/contracts/asset_exposure_v1.parquet
```

---

# 16. Fase 11 — Construir `grid_state_v1`

Agora juntar por:

```text
hora
+
cell_id
```

- clima;
- anomalias;
- percentis;
- incidentes;
- capacidade de geração;
- geração quando georreferenciada;
- subestações;
- hubs;
- exposição de transmissão.

Script:

```text
scripts/12_build_grid_state.py
```

Saída:

```text
outputs/contracts/grid_state_v1.parquet
```

---

# 17. Fase 12 — Pipeline de demanda ONS por subsistema

A previsão de demanda **não será por célula de 0,1°**.

Unidade de previsão:

```text
subsistema ONS
```

e depois:

```text
SIN
```

---

## 17.1 Preparar carga

Script:

```text
scripts/13_prepare_load.py
```

Converter para série horária consistente.

Saída:

```text
data/processed/demand/load_hourly.parquet
```

Campos:

```text
interval_start_utc
subsystem_id
load_mw
```

---

# 18. Fase 13 — Engenharia de atributos da demanda

Criar três grupos.

## Histórico

```text
lag_1h
lag_2h
lag_24h
lag_48h
lag_168h
```

Começar simples e revisar depois.

---

## Calendário

```text
hour
day_of_week
weekend
holiday
month
```

---

## Clima

Não usar uma única célula para representar um subsistema.

Agregar células de forma documentada.

Primeiro MVP:

```text
média
mediana
p90
máximo
percentual de células em incidente
```

Posteriormente usar ponderação:

```text
população
carga
ativos
capacidade instalada
```

conforme o objetivo.

Registrar sempre:

```text
weighting_method
```

---

# 19. Fase 14 — Treinar os experimentos de demanda

Rodar separadamente para cada subsistema.

Experimentos:

```text
E0 = baseline D-1 / D-7

E1 = histórico + calendário

E2 = E1 + clima bruto

E3 = E2 + anomalias + incidentes
```

O objetivo não é testar dezenas de algoritmos.

Primeiro usar **um algoritmo principal igual em E1, E2 e E3** para conseguir medir o valor incremental do clima.

---

## Split

Sempre temporal:

```text
PASSADO → treino
FUTURO → teste
```

Nunca embaralhar a série.

---

## Horizonte inicial

Contrato final:

```text
24 horas
```

Pode começar validando:

```text
1h
6h
24h
```

mas a entrega necessária para o sistema é a janela das próximas 24 horas.

---

## Saída

Por subsistema e hora:

```text
demand_p10_mw
demand_p50_mw
demand_p90_mw
```

---

## Métricas

```text
MAE
RMSE
WAPE
cobertura p10-p90
erro durante eventos extremos
```

---

## Scripts

```text
scripts/14_train_demand_models.py
scripts/15_backtest_demand.py
scripts/16_forecast_demand.py
```

---

# 20. Regra crítica para clima futuro

ERA5-Land é reanálise histórica.

Não usar:

```text
ERA5-Land futuro observado
```

como se estivesse disponível no momento da previsão operacional.

Durante o desenvolvimento podem existir dois modos:

```text
PERFECT_WEATHER_BACKTEST
```

usa ERA5-Land observado para medir o limite do ganho climático.

e:

```text
OPERATIONAL_FORECAST
```

usa previsão meteorológica que realmente estaria disponível antes da hora prevista.

Os resultados devem informar qual modo foi utilizado.

---

# 21. Fase 15 — Estado de geração e oferta

## Observado

Usar:

```text
Geração por Usina ONS
```

Agregações:

```text
usina
célula
tipo
subsistema
SIN
```

---

## Futuro

Quando disponível e validado:

```text
DESSEM
```

para programação de:

```text
demanda
geração por fonte
```

Nunca usar geração verificada do futuro em um backtest operacional.

---

# 22. Fase 16 — Índices do Motor 1

O Motor 1 deve terminar produzindo três sinais principais.

---

## 22.1 Pressão de demanda `D`

```text
D_s,h =
percentil da demanda prevista
dentro do histórico comparável
```

Faixa:

```text
0 ≤ D ≤ 1
```

---

## 22.2 Pressão de oferta `S`

```text
S_s,h =
1 - adequação normalizada de oferta
```

Pode combinar, no futuro:

- programação DESSEM;
- indisponibilidade;
- desvio de geração;
- outros sinais físicos válidos.

Regra:

```text
se não houver fonte confiável:
S = null
```

Nunca inventar um valor.

---

## 22.3 Exposição climática `C`

Exemplo:

```text
C_zone,t =
Σ(weight_cell × max incident_score_cell)
/
Σ(weight_cell)
```

`C` serve principalmente para:

```text
explicação
auditoria
mapa
```

Não multiplicar o clima diretamente na tarifa se seu efeito já estiver refletido em `D` ou `S`.

---

# 23. Fase 17 — Publicar `system_signal_v1`

Script:

```text
scripts/17_build_system_signal.py
```

Produzir:

```text
outputs/contracts/system_signal_v1.parquet
```

Para cada hora:

```text
SUBSYSTEM N
SUBSYSTEM NE
SUBSYSTEM S
SUBSYSTEM SE/CO
SIN
```

Janela:

```text
24 horas
```

---

## Testes obrigatórios

- [ ] exatamente uma linha por hora/zona;
- [ ] janela completa de 24 h;
- [ ] `p10 <= p50 <= p90`;
- [ ] `D`, `S` e `C` dentro de `[0,1]` ou `null` quando permitido;
- [ ] nomes de tipos de geração preservados;
- [ ] `data_freshness_ok` presente;
- [ ] `quality_flags` presente.

---

# 24. Motor 1 está pronto quando...

Ele consegue executar:

```bash
python scripts/run_motor_sin.py --date YYYY-MM-DD
```

e produzir:

```text
grid_state_v1.parquet
asset_exposure_v1.parquet
system_signal_v1.parquet
quality_report.json
```

sem executar nenhum código do Motor 2.

---

# 25. Fase 18 — Implementação independente do Motor 2

O Motor 2 deve ser iniciado **antes do Motor 1 estar pronto**.

Ele utiliza:

```text
contracts/fixtures/system_signal_v1_example.parquet
```

Assim as equipes trabalham em paralelo.

---

# 26. Fase 19 — Parser tarifário

Entrada:

```text
CSV ANEEL
```

O parser precisa identificar de forma unívoca:

```text
distribuidora
vigência
base tarifária
subgrupo
modalidade
classe
subclasse
detalhe
posto tarifário
unidade
TE
TUSD
```

---

## Separar obrigatoriamente

```text
R$/MWh
```

de:

```text
R$/kW
```

Nunca somar os dois.

---

## Tarifa-base volumétrica

Para linhas em R$/MWh:

```text
B_h =
(VlrTUSD + VlrTE) / 1000
```

Resultado:

```text
R$/kWh
```

---

## Script

```text
scripts/20_prepare_tariffs.py
```

---

# 27. Fase 20 — Resolver posto tarifário

Criar tabela versionada:

```text
distributor
day_type
start_local_time
end_local_time
tariff_post
valid_from
valid_to
```

Script:

```text
scripts/21_resolve_tariff_post.py
```

O posto não deve ser inferido pelo nome da modalidade.

A regra deve usar:

```text
distribuidora
+
vigência
+
hora local
+
tipo de dia
```

---

# 28. Fase 21 — Associar distribuidora ao sinal sistêmico

No MVP:

```text
distribuidora
    ↓
subsistema ONS principal
```

Guardar essa associação em tabela configurável:

```text
configs/distributor_subsystem_map.csv
```

Futuro:

```text
BDGD
+
área de concessão
+
células
    ↓
zone_type = DISTRIBUTOR
```

Essa evolução não deve exigir reescrever a lógica tarifária.

---

# 29. Fase 22 — Calcular sinal bruto

Entrada:

```text
D = pressão de demanda
S = pressão de oferta
E = sinal econômico opcional
```

Não usar `C` diretamente como terceiro multiplicador climático.

Equação:

```text
signal =
wD * centered(D)
+
wS * centered(S)
+
wE * centered(E)
```

Os pesos ativos devem somar:

```text
1
```

---

## Multiplicador bruto

```text
m_raw =
1 + beta * signal
```

---

## Tarifa bruta

```text
Tariff_raw =
BaseTariff * m_raw
```

Todos os pesos e `beta` ficam em:

```text
configs/tariff.yaml
```

Nenhum desses parâmetros deve ser apresentado como regra regulatória vigente.

---

# 30. Fase 23 — Guardrails

Nunca publicar `m_raw` diretamente.

Aplicar em sequência:

---

## 30.1 Piso e teto

```text
m_min <= m <= m_max
```

---

## 30.2 Limite de rampa

```text
|m_h - m_h-1| <= delta_max
```

---

## 30.3 Neutralidade aproximada

Objetivo:

```text
Σ consumo_ref × tarifa_base × multiplicador
≈
Σ consumo_ref × tarifa_base
```

O preço muda no tempo, mas o desenho experimental não deve simplesmente aumentar a receita esperada.

---

## 30.4 Cap de conta

Quando houver perfil de consumo:

```text
Bill_dynamic
<=
(1 + cap_bill) × Bill_reference
```

---

## 30.5 Fallback

Se:

```text
data_freshness_ok = false
```

ou qualidade insuficiente:

```text
multiplier = 1
```

Resultado:

```text
tarifa dinâmica = tarifa-base
```

---

# 31. Fase 24 — Saída do Motor 2

Script:

```text
scripts/22_simulate_dynamic_tariff.py
```

Entrada:

```text
system_signal_v1
+
perfil tarifário
+
tarifa-base
+
regras de posto
+
configs
```

Saída:

```text
outputs/contracts/tariff_v1.parquet
```

E relatório:

```text
outputs/reports/tariff_simulation.json
```

---

# 32. Motor 2 está pronto quando...

Consegue rodar:

```bash
python scripts/run_motor_tarifa.py \
  --signal contracts/fixtures/system_signal_v1_example.parquet \
  --profile PROFILE_ID \
  --date YYYY-MM-DD
```

sem instalar:

```text
ERA5
geopandas do Motor 1
modelos ML do Motor 1
dados ONS do Motor 1
```

---

# 33. Fase 25 — Teste de integração

Somente agora juntar os dois.

Fluxo:

```text
run_motor_sin.py
        ↓
system_signal_v1.parquet
        ↓
run_motor_tarifa.py
        ↓
tariff_v1.parquet
```

Teste mínimo de CI:

```text
fixture system_signal_v1
        ↓
Motor 2
        ↓
tariff_v1 válido
```

E separadamente:

```text
fixture grid_state_v1
+
fixture asset_exposure_v1
        ↓
mock da futura API/mapa
```

---

# 34. Estratégia de escalabilidade para o Brasil

Não executar dez anos de clima do país inteiro já no primeiro commit.

A expansão deve ocorrer em quatro níveis.

---

## Nível A — Teste funcional

```text
1 região pequena
1 ano de clima
1 mês de geração
```

Objetivo:

```text
validar formatos
joins
timestamps
células
algoritmos
```

---

## Nível B — Um subsistema

```text
1 subsistema
2–3 anos de clima
alguns meses de geração
```

Objetivo:

```text
validar agregações regionais
```

---

## Nível C — SIN completo com período curto

```text
Brasil/SIN
1 ano
```

Objetivo:

```text
validar performance e particionamento
```

---

## Nível D — Produção científica

```text
Brasil/SIN
10 anos completos de baseline
+
ano corrente
```

Objetivo:

```text
baseline climático oficial da aplicação
```

---

# 35. Particionamento dos dados

Evitar um único arquivo gigante.

Sugestão:

```text
climate/
  year=2025/
    month=01/
    month=02/

generation/
  year=2025/
    month=01/

grid_state/
  run_date=2026-09-19/

asset_exposure/
  run_date=2026-09-19/

system_signal/
  run_date=2026-09-19/
```

Para arquivos tabulares:

```text
Parquet
```

Para geometrias:

```text
GeoParquet
```

Manter o arquivo bruto original da fonte em `data/raw`.

---

# 36. Qualidade de dados obrigatória

Toda execução deve gerar:

```text
quality_report.json
```

Campos mínimos:

```text
run_id
source
rows_read
rows_output
missing_timestamps
duplicate_timestamps
missing_values
unknown_categories
geocoding_quality
data_start
data_end
freshness
warnings
errors
```

Regra:

> Nunca corrigir silenciosamente um problema estrutural.

---

# 37. Logging

Todos os scripts devem registrar:

```text
START
fonte
período
quantidade de registros
transformações
warnings
artefatos gerados
END
```

Usar `logging`, não `print()` como sistema principal de observabilidade.

---

# 38. Configuração

Não colocar no código:

```text
p95
p99
pesos
beta
m_min
m_max
delta_max
janelas
paths
```

Tudo deve ser configurável.

Exemplo:

```yaml
climate:
  baseline_years: 10
  seasonal_window_days: 15

incidents:
  extreme_heat_percentile: 0.95
  severe_heat_percentile: 0.99

tariff:
  beta: 0.20
  multiplier_min: 0.85
  multiplier_max: 1.30
  max_hourly_ramp: 0.10
```

Os valores são parâmetros experimentais.

---

# 39. Testes mínimos por módulo

## Climate

- [ ] timezone;
- [ ] célula correta;
- [ ] baseline não usa ano alvo;
- [ ] percentis em `[0,1]`;
- [ ] noite não gera déficit solar indevido.

## Generation

- [ ] tipos desconhecidos preservados;
- [ ] geração não negativa sem flag;
- [ ] chaves de usina controladas;
- [ ] registros sem coordenada preservados.

## Assets

- [ ] pontos dentro da célula correta;
- [ ] geometria esquemática marcada;
- [ ] hub score reproduzível.

## Demand

- [ ] split temporal;
- [ ] nenhum lag usa futuro;
- [ ] ERA5 futuro não entra no modo operacional;
- [ ] p10 ≤ p50 ≤ p90.

## Motor 2

- [ ] MWh separado de kW;
- [ ] tarifa-base selecionada de forma unívoca;
- [ ] piso;
- [ ] teto;
- [ ] rampa;
- [ ] fallback;
- [ ] neutralidade;
- [ ] cap de conta.

---

# 40. Divisão prática entre 3 desenvolvedores

## Desenvolvedor A — Clima + geoespacial

Responsável por:

```text
grade
ERA5-Land
baseline 10 anos
anomalias
incidentes
joins célula
grid_state
```

Entregas principais:

```text
grid_state_v1
```

---

## Desenvolvedor B — ONS + ML + ativos

Responsável por:

```text
carga
geração por usina
capacidade
geocodificação
subestações
LTs
hubs
forecast de demanda
asset_exposure
system_signal
```

Entregas principais:

```text
asset_exposure_v1
system_signal_v1
```

---

## Desenvolvedor C — Tarifas + integração

Responsável por:

```text
parser ANEEL
perfil tarifário
posto tarifário
tarifa-base
Motor 2
guardrails
fixtures
testes de contrato
```

Entrega principal:

```text
tariff_v1
```

Ele pode trabalhar desde o primeiro dia com fixture do Motor 1.

---

# 41. Dependências entre os desenvolvedores

```text
DEV A ─────────────┐
clima              │
                   ├──► Motor 1
DEV B ─────────────┘       │
ONS + ML + ativos          │
                           ▼
                  system_signal_v1
                           │
                           ▼
DEV C ───────────────► Motor 2
```

Mas:

```text
DEV C não espera Motor 1.
```

Ele usa:

```text
fixture system_signal_v1
```

até a integração real.

---

# 42. Ordem de implementação sugerida

## Sprint 1 — Fundação

### Dia 1

- estrutura do repositório;
- configs;
- schemas;
- fixtures;
- ambiente Python;
- teste de contrato.

### Dia 2

- grade 0,1°;
- parser inicial de tarifa;
- ingestão ONS geração;
- ingestão pequena ERA5-Land.

### Dia 3

- normalização climática;
- cadastro de usinas;
- perfil/posto tarifário;
- fixtures completas.

### Dia 4

- baseline climático em pequeno recorte;
- geocodificação de usinas;
- primeiro Motor 2 com sinal mock.

### Dia 5

- incidentes;
- mapa estático simples;
- guardrails;
- primeiro `grid_state_v1`.

---

## Sprint 2 — Motor 1

### Dia 6

- subestações;
- linhas;
- capacidade de transformação.

### Dia 7

- hubs;
- geração por célula;
- geração por subsistema.

### Dia 8

- asset exposure.

### Dia 9

- carga por subsistema;
- E0 e E1.

### Dia 10

- E2 e E3;
- métricas;
- previsão 24 h inicial.

---

## Sprint 3 — Integração nacional

### Dia 11

- `D`;
- `C`;
- `S = null` inicialmente se ainda não houver fonte válida.

### Dia 12

- `system_signal_v1`;
- testes.

### Dia 13

- Motor 2 com sinal real;
- `tariff_v1`.

### Dia 14

- pipeline ponta a ponta;
- quality reports.

### Dia 15

- freeze;
- correções;
- documentação;
- demo CLI.

Depois disso:

```text
escala nacional completa
+
baseline 10 anos
+
DESSEM
+
Django
```

---

# 43. CLI final esperada antes do Django

## Atualizar dados

```bash
python scripts/download_data.py --date 2026-09-19
```

## Executar Motor 1

```bash
python scripts/run_motor_sin.py \
  --issue-time 2026-09-19T18:00:00Z \
  --horizon 24
```

## Executar Motor 2

```bash
python scripts/run_motor_tarifa.py \
  --signal outputs/contracts/system_signal_v1.parquet \
  --profile PROFILE_ID
```

## Pipeline completo

```bash
python scripts/run_pipeline.py \
  --issue-time 2026-09-19T18:00:00Z \
  --horizon 24 \
  --profile PROFILE_ID
```

---

# 44. Artefatos que devem existir antes do Django

```text
outputs/contracts/
├── grid_state_v1.parquet
├── asset_exposure_v1.parquet
├── system_signal_v1.parquet
└── tariff_v1.parquet
```

Além de:

```text
outputs/reports/
├── motor_sin_quality.json
├── tariff_quality.json
├── demand_metrics.csv
└── run_manifest.json
```

---

# 45. `run_manifest.json`

Cada execução ponta a ponta deve registrar:

```text
run_id
issue_time
forecast_horizon
model_version
contract_versions
config_versions
data_sources
source_freshness
baseline_period
created_at
git_commit
```

Isso garante rastreabilidade.

---

# 46. Critérios de aceite antes de iniciar Django

## Motor 1

- [ ] grade nacional consistente;
- [ ] baseline climático reproduzível;
- [ ] incidentes por célula;
- [ ] geração por tipo;
- [ ] usinas georreferenciadas com qualidade;
- [ ] subestações e LTs;
- [ ] hubs;
- [ ] exposição de ativos;
- [ ] previsão de demanda nos quatro subsistemas;
- [ ] horizonte 24 h;
- [ ] `system_signal_v1` válido.

## Motor 2

- [ ] funciona somente com fixture;
- [ ] seleciona tarifa-base;
- [ ] resolve posto tarifário;
- [ ] calcula 24 valores horários;
- [ ] aplica guardrails;
- [ ] fallback funciona;
- [ ] produz `tariff_v1`;
- [ ] simula conta de perfil fictício.

## Integração

- [ ] Motor 1 → contrato;
- [ ] contrato → Motor 2;
- [ ] Motor 2 não importa pacote do Motor 1;
- [ ] mudanças internas não quebram os schemas;
- [ ] testes automatizados passam.

---

# 47. O que fica para depois

Não bloquear o MVP por:

```text
BDGD completa
fluxo de potência
modelagem hidrológica por bacia
modelo físico de potência eólica
modelo físico de geração fotovoltaica
probabilidade de falha de ativos
Django
autenticação
billing real
tarifa regulatória real
integração com medidores
```

Esses itens são evoluções.

---

# 48. Primeira meta funcional

A primeira versão completa deve conseguir responder:

> Em quais regiões do Brasil/SIN existem condições climáticas anômalas agora ou nas próximas horas?

Depois:

> Existem usinas, centros geradores, subestações ou linhas relevantes nessas regiões?

Depois:

> Como estão demanda e geração por subsistema?

Depois:

> Qual é o sinal horário agregado do sistema?

Finalmente:

> Como esse sinal alteraria, em uma simulação protegida, a tarifa-base de determinado perfil?

---

# 49. Fluxo completo do produto

```text
ERA5-Land histórico
        │
        ├────► baseline climático 10 anos
        │
Forecast climático
        │
        ▼
incidentes por célula
        │
        ├──────────────┐
        │              │
        ▼              ▼
usinas/geração     subestações/LTs
        │              │
        └──────┬───────┘
               ▼
        exposição de ativos
               │
ONS carga ─────┤
               │
ONS geração ───┤
               ▼
       MOTOR 1 — SIN
               │
               ▼
       system_signal_v1
               │
               ▼
       MOTOR 2 — TARIFA
               │
               ▼
          tariff_v1
               │
               ▼
       Django / interface
```

---

# 50. Decisão operacional mais importante

A implementação deve respeitar esta ordem:

```text
primeiro validar
depois escalar
depois automatizar
depois criar a interface
```

Não:

```text
baixar tudo
+
treinar tudo
+
construir frontend
+
tentar integrar no final
```

A primeira vitória do projeto é um pipeline pequeno, reproduzível e testado.

A segunda é escalar esse mesmo pipeline para todo o SIN.

A terceira é integrar o resultado a Django sem alterar a ciência dos dois motores.
