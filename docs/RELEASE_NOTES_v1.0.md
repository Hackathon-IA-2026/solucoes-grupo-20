# Release v1.0 — MVP pré-Django completo

Esta versão consolida as fases 0–25 do Plano Prático v0.2 em um repositório executável.

## Adicionado desde v0.3

- Fase 4: detecção de incidentes climáticos por célula/hora.
- Fases 5–7: geração ONS compatível, geocodificação e centros de geração.
- Fases 8–10: subestações, linhas, hubs e exposição climática de ativos.
- Fase 11: publicação e validação de `grid_state_v1`.
- Fases 12–14: carga, features, treino, backtest e forecast probabilístico simples.
- Fases 15–17: geração/oferta, D/S/C e `system_signal_v1`.
- Fases 18–24: Motor 2 independente, parser tarifário, postos, sinal e guardrails.
- Fase 25: integração Motor 1 → contrato → Motor 2.
- Demo sintético reproduzível com quatro subsistemas.
- CLIs `run_motor_sin.py`, `run_motor_tarifa.py` e `run_pipeline.py`.

## Validação no ambiente de empacotamento

- `python -m compileall`: OK.
- `pytest`: 39 testes passaram; 2 testes de I/O Parquet foram pulados porque `pyarrow` não está instalado no ambiente de empacotamento.
- Um smoke test ponta a ponta foi executado em memória, cobrindo incidentes → ativos → `grid_state_v1` → demanda → `system_signal_v1` → `tariff_v1`; os quatro contratos finais validaram com sucesso.

`pyarrow` continua sendo dependência obrigatória do projeto e é necessário para executar a demo com arquivos Parquet localmente.
