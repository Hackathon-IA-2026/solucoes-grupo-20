# Limitações do snapshot de origem

O único código Open-Meteo anexado ao projeto nesta conversa foi `OpenMeteo_snapshot_disponivel_2026-09-18.zip`, cujo próprio arquivo `INCOMPLETO_LEIA_PRIMEIRO.md` declara que módulos relevantes do repositório não estavam disponíveis.

Por isso, a v0.3 não tenta reconstruir silenciosamente módulos ausentes. O snapshot original foi preservado integralmente em `legacy_openmeteo_snapshot/` e a camada ARCO foi implementada como pacote autocontido (`predicta_climate/` + `scripts/56–60`).

Para fazer merge fiel no repositório local mais novo, copie esses módulos/scripts ou forneça posteriormente o ZIP atual do repositório para uma integração linha a linha.
