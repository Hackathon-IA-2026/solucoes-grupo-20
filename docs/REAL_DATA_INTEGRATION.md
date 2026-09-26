# Integração com dados reais

1. Mantenha os arquivos originais em `data/raw/` e não os sobrescreva.
2. Use `scripts/download_data.py` ou o downloader específico da Fase 2/5 quando tiver a URL exata do recurso oficial.
3. Normalize cada fonte antes de qualquer join.
4. Confira `quality_report.json`/relatórios e aliases de colunas. Se a fonte mudou, ajuste o adaptador explicitamente.
5. Para geração, preserve tipos desconhecidos; não force categorias novas para uma lista fixa.
6. Para geocodificação, não invente coordenadas para registros C/D.
7. Para clima futuro operacional, substitua reanálise observada por forecast disponível no issue time.
8. Para oferta futura, use fonte programada/forecast válida; se não houver, publique `supply_pressure=null`.
9. Para tarifa, confirme vigência, unidade, perfil e posto. Linhas de demanda R$/kW ficam separadas.
10. Antes de escalar Brasil/10 anos, substitua a máscara bootstrap pela fronteira oficial/versionada e teste particionamento/performance.
