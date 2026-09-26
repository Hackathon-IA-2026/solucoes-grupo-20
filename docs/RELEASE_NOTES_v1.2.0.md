# v1.2.0 — E2 real climate pilot

- congela o E1 v1.1.4 como baseline de ML do MVP;
- adiciona download de ERA5-Land/Open-Meteo para pontos representativos do SE/CO;
- infere automaticamente o período climático a partir da série ONS utilizada;
- normaliza os pontos para células canônicas 0,1° e agrega clima horário por subsistema;
- marca o método espacial do piloto explicitamente como `MVP_REPRESENTATIVE_POINTS_UNIFORM`;
- E2 usa apenas clima bruto no horário-alvo;
- E3 só é executado quando anomalias/percentis/incidentes realmente existirem;
- preserva literalmente `event_rules.json` do snapshot OpenMeteo e adiciona implementação auditável da semântica térmica de anomalia suportada pelo snapshot;
- não inventa o `baseline.py` ausente no snapshot.
