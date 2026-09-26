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

## Política de oferta no MVP

O Balanço ONS é observado. Logo, não deve ser usado como se fosse oferta futura conhecida. Nesta versão:

- `supply_pressure = null` por padrão;
- Motor 2 renormaliza os pesos ativos;
- geração verificada pode ser anexada somente em backtest como contexto, com `OBSERVED_GENERATION_RETROSPECTIVE_ONLY`;
- a evolução natural é DESSEM ou outra fonte de oferta futura com disponibilidade temporal auditada.

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
