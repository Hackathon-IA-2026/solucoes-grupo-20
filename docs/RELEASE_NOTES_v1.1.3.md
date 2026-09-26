# Release notes — v1.1.3

Correção metodológica do piloto real para previsão day-ahead.

## Mudanças

- substitui o backtest recursivo por **direct multi-horizon**: um modelo independente para cada H01...H24;
- features de carga passam a ser explicitamente ancoradas na origem (`issue_lag_0h`, `issue_lag_1h`, `issue_lag_2h`, `issue_lag_24h`, `issue_lag_48h`, `issue_lag_168h`);
- nenhuma previsão de horizonte anterior é usada como entrada de horizonte posterior;
- calendário permanece calculado no fuso civil explícito e joins/storage permanecem UTC;
- E1/E2/E3 continuam usando Ridge para manter o estimador constante e isolar o ganho das features climáticas;
- p10/p90 passam a ser calibrados **separadamente por horizonte**, usando quantis assimétricos dos resíduos em um bloco cronológico pré-teste;
- o bloco de calibração não participa do fit do ponto e o holdout não participa nem do fit nem da calibração;
- `--calibration-hours` foi adicionado ao piloto, default 720 h;
- previsões registram estratégia, método, tamanho e cobertura empírica da calibração;
- testes anti-leakage verificam também que alterar H01 observado não altera a previsão H02 já emitida.

## Compatibilidade

Os contratos `grid_state_v1`, `asset_exposure_v1`, `system_signal_v1` e `tariff_v1` não mudam. O restante do pipeline foi preservado. A alteração é concentrada no motor experimental do piloto real (`scripts/29_run_real_pilot.py`).

## Validação do pacote

52 testes passaram. 2 testes de I/O Parquet são pulados apenas em ambientes sem `pyarrow`.
