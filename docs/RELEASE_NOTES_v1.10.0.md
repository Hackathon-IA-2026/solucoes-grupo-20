Predicta Django Web Studio v1.10.0
=================================

Mudanças principais
-------------------
- remove o conceito de um único `climate_year` do pipeline completo;
- clima histórico passa a acompanhar automaticamente todo o período ONS/treino;
- baseline E3 rolling sem vazamento para cada ano Y: Y-10..Y-1;
- grade canônica Brasil 0,1° continua sendo materializada integralmente;
- catálogo climático ativo passa a usar células exatas 0,1° em uma lattice regional determinística + todas as células que contêm usinas;
- modo `full` opcional permite requisitar todas as células mapeadas do Brasil (alto custo de API/armazenamento);
- associação usina -> cell_id -> contexto/evento E3 é persistida;
- tela Clima & geração prefere células 0,1° e marca exposição `EXACT_01DEG_CELL` quando há evento na mesma célula da usina;
- Open-Meteo passa a usar múltiplas coordenadas por requisição, cache RAW, pausa entre batches e retry exponencial de HTTP 429/5xx respeitando `Retry-After`;
- o caminho legado `34_download_e3_context.py` também ganhou retry automático para 429;
- forecast operacional H01-H24 usa os pontos de grade gerados e chamadas multi-location;
- baseline operacional reutiliza o baseline rolling do treinamento quando o ano já está disponível.

Importante
----------
A grade geométrica é 0,1° em todo o Brasil. Por padrão, a coleta remota usa modo `adaptive` para evitar volume impraticável no hackathon: amostra regional de células 0,1° + todas as células de usinas. `--climate-grid-mode full` implementa a coleta para todas as células mapeadas, mas é deliberadamente opt-in por custo e limites do provedor.
