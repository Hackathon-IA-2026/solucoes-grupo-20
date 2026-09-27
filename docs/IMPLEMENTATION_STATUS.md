# Predicta v1.0 — status das fases

| Fase | Entrega | Status MVP |
|---|---|---|
| 0 | contratos + fixtures + validadores | implementada |
| 1 | grade 0,1° | implementada; máscara bootstrap |
| 2 | ingestão climática | implementada para recorte/snapshot |
| 3 | baseline 10 anos | implementada; E3 também materializa baseline térmico mensal 10 anos conforme snapshot OpenMeteo |
| 4 | incidentes | implementada; E3 aplica regras do snapshot para calor/frio/ondas/chuva/vento/tempestade |
| 5 | geração ONS | downloader genérico + normalizador |
| 6 | geocodificação usinas | implementada; ID > nome |
| 7 | centros de geração | implementada |
| 8 | subestações/LTs | implementada; geometria real ou esquemática explícita |
| 9 | hubs | implementada sem betweenness no MVP |
| 10 | clima × ativos | implementada |
| 11 | grid_state_v1 | implementada e validada |
| 12 | carga ONS | normalizador e agregação horária |
| 13 | atributos demanda | lags + calendário + clima agregado |
| 14 | modelos demanda | E1/E2/E3 direct H01–H24; E3 agora recebe anomalias/eventos reais do baseline 2015–2024 no piloto 2025 |
| 15 | geração/oferta | agregações + entrada futura opcional |
| 16 | D/S/C | implementada; S aceita null |
| 17 | system_signal_v1 | implementada e validada |
| 18 | Motor 2 independente | implementado |
| 19 | parser tarifário | implementado |
| 20 | posto tarifário | implementado |
| 21 | distribuidora→subsistema | config versionada |
| 22 | sinal bruto | implementado |
| 23 | guardrails | implementados |
| 24 | tariff_v1 | implementada e validada |
| 25 | integração | `run_pipeline.py` |

## Não significa produção

“Implementada” significa que a fase possui código executável, contratos e/ou testes no MVP. Não significa que todos os datasets nacionais reais estejam incluídos ou que integrações externas estejam imunes a mudanças de schema. O ZIP deliberadamente não embute grandes bases ONS/ANEEL/ERA5.

## v1.4.0 — ponte operacional

- [x] congelamento dos 24 modelos E3 após seleção held-out;
- [x] inferência H01..H24 sem retreino;
- [x] construção de `system_signal_v1` a partir do piloto real;
- [x] `D` calculado contra histórico comparável anterior ao issue time;
- [x] `C` ligado ao contexto E3;
- [x] `S` aceita `null` na biblioteca; no produto usa comparação obrigatória com a programação DESSEM;
- [x] download DESSEM por subsistema, média horária, snapshots e proveniência;
- [x] comparação DESSEM versus Predicta na página do produto e na API;
- [x] ANEEL TE/TUSD volumétricas normalizadas;
- [x] separação de R$/kW;
- [x] simulação cliente 24h e payload JSON para Django;
- [ ] previsão meteorológica operacional em vez de PERFECT_WEATHER_BACKTEST;
- [ ] disponibilidade DESSEM comprovada no instante de emissão para uma execução operacional;
- [ ] mapeamento localização -> distribuidora automatizado;
- [x] demonstração Django retrospectiva com DESSEM.

Atualização DESSEM de 26/09/2026: 488 dias preparados, 58.560 linhas horárias
incluindo SIN, com lacunas documentadas. A demo SE/CO de 15/09/2026 usa modelo
congelado, clima observado e DESSEM capturado posteriormente. Os testes confirmam
estrutura e integração, não ganho de acurácia, reserva ou economia comprovada.
Comandos e limites: [ponte operacional](MVP_OPERATIONAL_BRIDGE_v1.4.md).
