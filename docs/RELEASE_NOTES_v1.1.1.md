# Predicta v1.1.1 — Hotfix ONS SIN

Correção do adaptador `Balanço de Energia nos Subsistemas`: o arquivo oficial inclui uma quinta linha agregada por hora com `id_subsistema = SIN` e `nom_subsistema = SISTEMA INTERLIGADO NACIONAL`.

A v1.1 rejeitava esse identificador como desconhecido antes de produzir `load_hourly.parquet`. A v1.1.1 preserva a linha agregada como `subsystem_id = SIN`, além de N, NE, S e SE/CO.

Adicionado teste regressivo com o esquema e valores observados no recurso ONS 2025.
