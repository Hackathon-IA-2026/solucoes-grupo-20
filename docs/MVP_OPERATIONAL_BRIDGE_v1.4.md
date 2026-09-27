# Predicta v1.4 — ponte operacional pré-Django

## Objetivo

Congelar a ciência validada no E3 e produzir os artefatos que o Django poderá consumir sem retreinar modelos.

## Camada offline

1. E0/E1/E2/E3 e backtest.
2. Seleção do modelo.
3. `scripts/37_freeze_e3_models.py`.
4. Persistência H01..H24 + manifesto.

## Camada recorrente de inferência

1. carga observada mais recente;
2. previsão meteorológica H01..H24;
3. mesma engenharia de features usada no treino;
4. modelos congelados;
5. `demand_p10/p50/p90`;
6. `system_signal_v1`;
7. Motor 2;
8. `tariff_v1`;
9. API/banco/Django.

## DESSEM obrigatório no produto

O produto e o comando `scripts/39_build_real_system_signal.py` exigem programação
DESSEM nas 24 horas da janela. Não há escolha de adoção baseada em ganho de
acurácia: os testes verificam somente estrutura, contratos e funcionamento.
Nenhum solver DESSEM, processamento de decks ou novo treinamento foi adicionado.

A fonte é [DESSEM - Balanço de Energia Geral, ONS](https://dados.ons.org.br/dataset/balanco_dessem_geral),
com atribuição ONS Dados Abertos, licença CC-BY. O adaptador usa os patamares
semi-horários 1..48, converte o horário explicitamente para UTC e calcula a média
dos dois valores de potência de cada hora. Não soma MW no tempo. Os quatro
subsistemas são preservados, e SIN é a soma desses subsistemas por hora.

O download toma o período e os subsistemas do histórico de carga usado no treino.
Mantém snapshots brutos, URL, SHA256 e instante real de captura. Os dados horários
ficam em `data/processed/generation/dessem_schedule_hourly.parquet`; isso prepara
a referência alinhada ao treino, sem inserir automaticamente novas features no
modelo congelado nem alegar disponibilidade histórica dos arquivos.

```bash
.venv/bin/python scripts/65_prepare_dessem.py --end 2026-09-27
```

Na captura de 26/09/2026, foram preparados 488 dias e 58.560 registros horários
entre 23/05/2025 e 27/09/2026, incluindo SIN. O catálogo não cobre o início do
histórico local em 2023 e contém lacunas posteriores; 30/05/2026 responde 404 nos
dois formatos. A lista completa está em `outputs/reports/dessem_download.json`.
Não há preenchimento artificial de datas. Somente janelas completas são oferecidas
no seletor de replay do produto.

### Sinal experimental

Para demanda Predicta $D$ e demanda programada DESSEM $P$, ambas em MW médios
do mesmo subsistema e hora, `supply_pressure` transporta $S = D / (D + P)$.
Valores iguais resultam em 0,5, neutro para a contribuição centrada de S no Motor 2.
Isso é um indicador de desvio em relação à programação, **não** capacidade de
geração, reserva, fluxo de potência, CMO/PLD ou risco de falta de energia.
Não se interpreta geração local menor que demanda como escassez de um subsistema
importador. A demanda programada não substitui a previsão p50 do Predicta.

Pesos e guardrails do Motor 2 permanecem inalterados. Ativar S também altera a
normalização dos pesos: S=0,5 não garante a mesma tarifa do caso sem DESSEM.
Os valores D, P, S, método e proveniência ficam em `main_drivers_json.dessem`,
sem mudar os campos do contrato v1. O gráfico do produto compara DESSEM e
Predicta em GW; a API e os artefatos conservam MW.

### Temporalidade

Uso operacional exige disponibilidade comprovada do snapshot até o instante
explícito de emissão da previsão. Capturar um arquivo hoje não comprova que ele
estava disponível num dia passado; a data do arquivo não é a data de publicação.
O ONS também informa que seus dados podem ser revisados.

`--allow-dessem-replay` permite explicitamente o cenário retrospectivo, marcado
com `DESSEM_REPLAY_NOT_ASOF`. O produto bloqueia a promoção desse sinal para o
modo operacional. O atalho `scripts/42_run_historical_mvp_bridge.py` repassa essa
mesma opção; a etapa de construção do sinal no Pipeline técnico oferece um
checkbox desmarcado por padrão. Clima observado continua marcado como
`PERFECT_WEATHER_BACKTEST_NOT_OPERATIONAL`, inclusive quando previsão e contexto
contêm `weather_mode`.

Chamadas antigas da biblioteca sem DESSEM continuam com `supply_pressure=null`
e pesos renormalizados. A exigência é aplicada no produto e no gerador da demo.
Geração ONS observada continua separada, somente como contexto retrospectivo
com `OBSERVED_GENERATION_RETROSPECTIVE_ONLY`.

### Reproduzir a demo

A janela preparada é SE/CO, 15/09/2026, 00h..23h em São Paulo. Usa a família E3
congelada `E3_SECO_DIRECT_V1_4_0`, cujo histórico de treino/calibração termina em
01/01/2026. É uma demonstração retrospectiva com clima observado, não uma
previsão operacional atual nem validação de desempenho da adição do DESSEM.

```bash
.venv/bin/python scripts/38_forecast_frozen_e3.py \
	--climate data/processed/climate/zone_climate_hourly_e3.parquet \
	--model-dir models/demand/e3_seco_v1 --issue-time 2026-09-15T02:00:00Z \
	--allow-perfect-weather \
	--output data/processed/demand/e3_dessem_demo_forecast_24h.parquet \
	--report outputs/reports/dessem_demo_forecast.json
.venv/bin/python scripts/39_build_real_system_signal.py \
	--forecast data/processed/demand/e3_dessem_demo_forecast_24h.parquet \
	--allow-dessem-replay --run-id dessem-demo-20260915 \
	--report outputs/reports/dessem_demo_signal.json
```

No Produto, selecionar SE/CO, a janela disponível, uma concessão e seu perfil
tarifário vigente. A comparação DESSEM x Predicta aparece junto do resultado
tarifário, mantendo a curva de consumo do cliente separada da demanda do subsistema.

Verificações estruturais, sem critério de ganho para adoção:

```bash
.venv/bin/python -m pytest -q tests/unit/test_mvp_bridge_v140.py tests/unit/test_tariff.py
.venv/bin/python manage.py test tests.test_web_api --noinput
```

Execução local em 26/09/2026: 12 testes dos motores e 10 testes web passaram.
A simulação real CPFL Paulista, B1 convencional residencial, 300 kWh/mês com curva
sintética, passou nos contratos e nos limites de piso, teto, rampa e conta do caso
verificado. A comparação com/sem o componente S confirmou propagação até a tarifa
final, sem alegar benefício econômico. O produto foi conferido em desktop e
celular, com 24 valores DESSEM e duas curvas de demanda.

## `system_signal_v1` do piloto

O sinal de demanda é o percentil da previsão p50 contra histórico **anterior ao issue time**, comparável por hora civil local e mês quando há amostra suficiente.

`climate_exposure` deriva das frações de eventos E3 e continua sendo explicativo/auditável; não é multiplicado novamente na tarifa.

## Motor tarifário

O parser ANEEL:

- converte R$/MWh para R$/kWh;
- mantém R$/kW fora da tarifa volumétrica;
- normaliza `Não se aplica` em posto tarifário como `UNIQUE`;
- respeita vigência da linha tarifária.

A simulação do cliente pode receber curva horária real. Na ausência dela, são fornecidos perfis sintéticos residencial, comercial e industrial-flat, explicitamente marcados como ilustrativos.

## O que o Django deverá fazer

O Django deverá apenas:

- receber/identificar cliente e perfil;
- consultar último `system_signal_v1` válido;
- executar/consultar o Motor 2;
- exibir comparação e explicações.

Treino, backtest e recomputação integral do baseline climático não pertencem ao request web.
