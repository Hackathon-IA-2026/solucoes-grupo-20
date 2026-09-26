# Predicta Django Web Studio v1.9.0

## Automação ponta a ponta

Nova tela **Automação** com dois fluxos:

1. **Executar pipeline completo + treinar Ridge e XGBoost**
   - testes e contratos;
   - grade espacial;
   - histórico ONS multi-ano;
   - mapa + tarifas ANEEL;
   - E2/E3 e baseline climático de 10 anos para N, NE, SE/CO e S;
   - validação Ridge e XGBoost com o mesmo holdout;
   - treinamento/congelamento H01–H24 dos dois algoritmos por subsistema;
   - registry regional com seleção automática pelo menor WAPE da janela de promoção do MVP;
   - rollover do baseline climático para o ano operacional;
   - previsão meteorológica Open-Meteo disponível no issue time;
   - previsão de demanda operacional H01–H24;
   - publicação de `system_signal_v1` para os quatro subsistemas.

2. **Atualizar operacional H01–H24 agora**
   - não retreina;
   - força atualização do arquivo ONS do ano corrente;
   - reaproveita o baseline anual se já estiver pronto;
   - atualiza weather forecast, demanda e `system_signal_v1`.

## Segurança metodológica

- o publish operacional é bloqueado quando a carga ONS está mais antiga que o limite configurado;
- clima operacional usa `weather_mode=OPERATIONAL_FORECAST`, nunca `PERFECT_WEATHER_BACKTEST`;
- o baseline operacional é Y-10…Y-1 para o ano do issue time;
- `supply_pressure` continua nulo até existir uma fonte futura de oferta confiável;
- seleção automática por WAPE é uma regra de promoção do MVP e não substitui uma avaliação final cega em produção.

## Cobertura espacial

Foram adicionados arquivos de pontos representativos para N, NE e S. Eles mantêm o mesmo princípio do piloto SE/CO: proxy espacial explícito, não fronteira elétrica oficial do ONS.
