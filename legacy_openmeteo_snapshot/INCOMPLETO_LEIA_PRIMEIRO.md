# Snapshot parcial do OpenMeteo

Este ZIP contém somente os arquivos cujo conteúdo atual está disponível no histórico desta conversa e que podem ser reconstruídos com fidelidade.

## Incluídos
- openmeteo_pipeline/config.py
- openmeteo_pipeline/parser.py (com correção `from datetime import date`)
- openmeteo_pipeline/detectors.py
- openmeteo_pipeline/reports.py
- openmeteo_pipeline/models.py
- openmeteo_pipeline/canonical_mapper.py (Etapa 3)
- openmeteo_pipeline/historical.py
- openmeteo_pipeline/storage.py
- tests/test_pipeline_integrity.py
- config/event_rules.json
- requirements.txt

## Não disponíveis em versão completa/atual no chat
- executar_openmeteo.py
- README.md
- .gitignore
- config/locations.json
- openmeteo_pipeline/__init__.py
- openmeteo_pipeline/baseline.py
- openmeteo_pipeline/client.py
- openmeteo_pipeline/collector.py
- openmeteo_pipeline/exporter.py
- openmeteo_pipeline/geocoding.py
- tests/__init__.py
- tests/test_baseline.py
- tests/test_detectors.py
- tests/test_geocoding.py
- tests/test_parser.py
- specs/001-openmeteo-weather-events/*
- dados RAW/staging/export gerados localmente

Para um snapshot completo e fiel, envie a pasta atual `OpenMeteo/` (ou um ZIP dela). Não é seguro inventar os arquivos ausentes a partir de interfaces parciais.
