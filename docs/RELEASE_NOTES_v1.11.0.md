# Predicta Django Web Studio v1.11.0

## Mudança principal

O downloader climático histórico foi reorganizado para um data lake incremental por ano, com retomada robusta em limites de API.

### Open-Meteo

- E2 horário dividido em janelas anuais não sobrepostas.
- E3 baseline e E3 target também divididos por ano.
- cache imutável por ponto/ano em diretório estável, independente do período de treino;
- checkpoint atualizado após cada batch e após cada ano;
- restart reaproveita registros já persistidos e solicita somente pontos ausentes;
- cooldown global após sequência configurável de HTTP 429;
- `Retry-After`, retry exponencial e pausa entre batches preservados;
- defaults mais conservadores: batch=6, delay=2s, retries=10, backoff=10s, cooldown=90s após 3×429;
- remoção do `DeprecationWarning` de `pd.Timedelta(days=...)` no script 53.

### Migração v1.10 → v1.11

O RAW multi-ano já baixado pela v1.10 pode ser repartido localmente em arquivos anuais. O pipeline completo executa essa migração automaticamente nos diretórios legados da mesma janela, evitando perder batches que já tinham sido concluídos antes de um 429.

### Operacional

O baseline operacional passa a usar o mesmo cache anual compartilhado do treinamento e deixa de fazer uma chamada target fictícia de um dia apenas para conseguir parsear o manifest.

### Validação

Foram adicionados testes para:

- divisão correta de janelas anuais com anos parciais;
- partições `year=YYYY` do cache horário;
- cooldown global após três 429 consecutivos;
- conversão local de RAW multi-ano legado para cache anual.
