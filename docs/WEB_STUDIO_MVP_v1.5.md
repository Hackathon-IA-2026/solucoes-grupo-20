# Predicta Web Studio v1.5

A camada Django transforma o pipeline técnico em uma interface local para três públicos ao mesmo tempo:

1. **produto/negócio** — entende o fluxo, vê resultados e simula o cliente;
2. **dados/energia** — inspeciona datasets, contratos, métricas e limitações;
3. **desenvolvimento/ML** — executa etapas, treina/congela modelos e acompanha logs.

## Princípio arquitetural

Django **não contém a ciência** do Predicta. Ele orquestra os scripts e bibliotecas que já existem no repositório. Isso evita criar uma segunda implementação das regras de features, backtest ou tarifa.

```text
Django / Studio
  ├─ executa scripts versionados
  ├─ lê Parquet/CSV/JSON
  ├─ registra execuções no SQLite
  ├─ seleciona uma família de modelos congelada
  └─ apresenta Motor 1 + Motor 2 ao usuário
```

## Telas

- **Visão geral:** estado dos artefatos, modelo ativo, resultados e execuções recentes.
- **Pipeline:** cards explicativos e executáveis por etapa, com dependências, parâmetros e logs.
- **Dados:** preview seguro de carga ONS, clima, métricas, contratos e tarifas; schema, missing e estatísticas.
- **Experimentos:** MAE, RMSE, WAPE, cobertura p10-p90 e gráfico H01-H24; execução E1/E2/E3; treino para deployment.
- **Modelos:** catálogo de `manifest.json`, promoção de uma família ativa e treino/congelamento E1/E2/E3.
- **Produto:** mapa esquemático do SIN, seleção de distribuidora/perfil, consumo mensal e comparação tarifa-base × tarifa Predicta.

## Execução de jobs

O botão de uma etapa cria `PipelineRun` no SQLite e inicia:

```bash
python manage.py run_pipeline_stage <UUID>
```

O comando permitido vem de um **registro fechado de etapas**. A interface não executa comandos arbitrários enviados pelo navegador. Os logs ficam em:

```text
outputs/web/runs/<UUID>.log
```

## Limites explícitos do MVP

- o mapa é navegação esquemática por subsistema; não é fronteira elétrica oficial;
- E2/E3 históricos ainda usam `PERFECT_WEATHER_BACKTEST` até conectar forecast meteorológico operacional;
- `supply_pressure` permanece `null` sem fonte futura validada de oferta;
- o comparador tarifário usa TE+TUSD volumétricas e não reproduz todos os itens de uma fatura regulada;
- `runserver` é servidor de desenvolvimento local. Não expor à internet.
