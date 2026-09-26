# Release v1.4.0

- adiciona persistência de uma família E3 direct multi-horizon H01..H24;
- adiciona inferência sem retreino;
- adiciona `system_signal_v1` do piloto real a partir de forecast/E3 backtest;
- mantém `supply_pressure=null` até haver oferta futura válida;
- permite geração ONS observada apenas como contexto retrospectivo sinalizado;
- melhora parser ANEEL (`Não se aplica` -> `UNIQUE`, datas abertas tratadas explicitamente);
- adiciona perfil de consumo sintético e curva horária real do cliente;
- adiciona payload JSON pronto para consumo por Django;
- adiciona scripts 37–42 e testes de regressão/end-to-end da ponte.
