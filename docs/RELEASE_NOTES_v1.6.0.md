# Release notes — v1.6.0

- Navegação reorganizada: Dados → Features → Modelagem → Validação → Modelos → Produto.
- XGBoost implementado como alternativa ao Ridge no backtest e deployment H01-H24.
- Validações configuráveis preservadas com IDs distintos; não sobrescrevem automaticamente execuções com parâmetros diferentes.
- Histórico ONS multi-ano incremental via `45_sync_ons_history.py`.
- Preview da cobertura temporal de carga e clima.
- GeoJSON real de 103 áreas de concessão no Produto.
- Clique no mapa → CNPJ → perfis tarifários ANEEL.
- CSV tarifário completo incluído compactado em `references/`.
- Preparação tarifa+geografia via `44_prepare_tariff_geography.py`.
- Correção robusta de datas ISO ANEEL (`YYYY-MM-DD`) e formatos dia/mês em fixtures.
- TE/TUSD em MWh ou kWh normalizados para R$/kWh.
- Duplicatas tarifárias só são colapsadas quando economicamente idênticas.
- Produto mostra TE, TUSD, tarifa-base, data de referência e tarifa dinâmica 24h.
- Mapeamento distribuidora→subsistema explicitamente marcado como proxy geográfica do MVP.
- Novos testes para XGBoost, parser tarifário, CNPJ e seleção segura de tarifa.
