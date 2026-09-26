# Release v1.5.0 — Django Web Studio

## Entregue

- aplicação Django local em `manage.py` + `web/studio`;
- dashboard com status de datasets, métricas, modelos e próxima ação;
- pipeline visual com explicação, dependências, parâmetros e execução assíncrona por subprocesso seguro;
- logs persistidos em `outputs/web/runs/` e histórico em SQLite;
- Data Explorer de Parquet/CSV com preview, schema, missing, estatísticas e gráfico temporal;
- tela de Experimentos com MAE, RMSE, WAPE, cobertura e gráfico H01–H24;
- treino/congelamento genérico de famílias E1/E2/E3 via `scripts/43_train_model_family.py`;
- catálogo de modelos e promoção de uma família ativa;
- inferência genérica de modelo congelado E1/E2/E3;
- produto com mapa esquemático do SIN, distribuidora, perfil ANEEL e consumo mensal;
- comparação visual de tarifa-base TE+TUSD versus tarifa dinâmica experimental;
- interface responsiva sem dependência de biblioteca JS externa para gráficos.

## Segurança do MVP

A interface executa apenas etapas registradas em whitelist. Mesmo assim, o `runserver` é para uso local e não deve ser publicado diretamente na internet.

## Validação no ambiente de build

- `compileall`: OK;
- `pytest`: 70 passed, 2 skipped (somente I/O Parquet sem pyarrow no ambiente de build);
- Django runtime não pôde ser instalado no ambiente de empacotamento por ausência de acesso de rede. A dependência está declarada em `.[web]`; executar `python manage.py check` após instalação local.
