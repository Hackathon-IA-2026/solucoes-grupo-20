Predicta Django Web Studio v1.8.0
================================

Principais mudanças
-------------------
- nova área **Clima & geração** na navegação principal;
- mapa territorial com **localização de usinas** e **pontos climáticos com eventos**;
- destaque para usinas **próximas de eventos regionais** (proxy espacial do MVP);
- correlações exploratórias entre **clima, geração e demanda**;
- comparação média entre horas com e sem evento climático;
- curvas diárias em **horário de São Paulo** para demanda, geração e intensidade climática;
- catálogo de usinas georreferenciadas embutido em `configs/generation_assets_catalog.json`.

Observações metodológicas
-------------------------
- UTC permanece como base de auditoria/armazenamento; a leitura operacional da tela usa `America/Sao_Paulo`.
- Proximidade planta-evento usa pontos climáticos representativos e raio aproximado de 300 km.
- A tela é diagnóstica e explicativa; não substitui análise elétrica oficial.
