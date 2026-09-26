# Status — Fase 0 e início da Fase 1

## Fase 0 — congelar contratos

Implementado nesta entrega:

- [x] `grid_state_v1` definido em Pydantic + JSON Schema;
- [x] `asset_exposure_v1` definido em Pydantic + JSON Schema;
- [x] `system_signal_v1` definido em Pydantic + JSON Schema;
- [x] `tariff_v1` definido em Pydantic + JSON Schema;
- [x] fixture sintética `system_signal_v1` com 24 h para N, NE, S, SE/CO e SIN;
- [x] fixture sintética de tarifa-base;
- [x] fixture sintética `tariff_v1` de 24 h;
- [x] validação de coluna ausente/extra;
- [x] validação de chave duplicada;
- [x] validação de timestamp UTC/hora cheia;
- [x] validação de valores normalizados em `[0,1]`;
- [x] validação `p10 <= p50 <= p90`;
- [x] validação de janela horária contínua;
- [x] testes automatizados;
- [x] bootstrap que materializa Parquet quando `pyarrow` está instalado.

## Fase 1 — grade espacial nacional

Inicializado:

- [x] `cell_id` determinístico a partir de índices globais de 0,1°;
- [x] EPSG:4326 documentado;
- [x] script `scripts/01_build_grid.py`;
- [x] máscara simplificada do Brasil para bootstrap;
- [x] teste de estabilidade de célula e fronteira simples;
- [ ] substituir máscara Natural Earth por malha oficial/versionada antes de produção;
- [ ] gerar e versionar manifest/quality report da grade nacional;
- [ ] validar interseção com futuros datasets ONS/ANEEL.

## Próximo passo recomendado

Seguir a Fase 2 em recorte pequeno: **1 ano + região pequena**, com ERA5-Land horário, normalização em UTC e mapeamento direto para `cell_id`. Não baixar dez anos do Brasil inteiro antes desse teste.
