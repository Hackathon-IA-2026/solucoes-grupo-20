# Release notes — v1.1.2

Hotfix metodológico do piloto real.

- backtest E0/E1/E2/E3 convertido para origem fixa e previsão recursiva t+1...t+24;
- observações futuras de carga bloqueadas como lags dentro de cada origem;
- calendário derivado em timezone civil explícita, mantendo storage/join em UTC;
- métricas adicionadas por horizonte H01...H24;
- previsões passam a registrar `issue_time_utc` e `horizon_hour`;
- `forecast_24h()` também trunca `load_history` no issue time para evitar leakage acidental;
- treino/forecast passam a compartilhar o mesmo gerador de features de calendário;
- testes regressivos de timezone e anti-leakage.

Validação do pacote: 50 testes passaram; 2 testes de I/O Parquet são pulados quando `pyarrow` não está instalado no ambiente de build.
