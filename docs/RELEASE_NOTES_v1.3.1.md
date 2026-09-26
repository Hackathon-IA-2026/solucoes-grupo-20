# Predicta v1.3.1 — E3 OpenMeteo snapshot hotfix

## Corrigido

A v1.3.0 forçava `wind_gusts_10m_max` no canal `era5_land` do target year. Em execução real, o Open-Meteo retornou essa série completamente nula e o download foi corretamente bloqueado.

A v1.3.1 passa a reproduzir a separação que existe no snapshot fornecido:

- **baseline térmico 2015–2024:** `models=era5_land`, conforme `event_rules.json`;
- **contexto diário do ano-alvo:** não força `models`, seguindo `openmeteo_pipeline/historical.py` do snapshot, que usa a seleção histórica padrão do Open-Meteo e solicita temperatura, precipitação e rajada máxima diária.

As regras de evento não mudaram. `wind_gusts_10m_max` continua sendo a métrica exigida para vento forte/severo/extremo e para o candidato histórico de tempestade.

## Robustez

- o parser aceita o novo canal `target_snapshot_daily`;
- o parser mantém compatibilidade com um manifesto legado completo da v1.3.0;
- scripts 35 e 36 agora informam explicitamente a etapa anterior ausente, em vez de gerar um traceback secundário pouco informativo;
- RAW imutável já baixado continua reutilizável/deduplicável.
