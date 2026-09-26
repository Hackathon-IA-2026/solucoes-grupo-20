# Validação ARCO — 2026-09-20

Teste executado pelo usuário contra o cubo oficial ERA5-Land ARCO de temperatura 2 m:

```text
Dimensions: time: 672384
Time range: 1950-01-02 00:00:00 → 2026-09-15 23:00:00
Frequency: hourly
```

O número de timestamps esperado para uma sequência horária contínua, inclusiva, entre esses dois instantes é exatamente **672.384**. Portanto, o eixo temporal remoto observado não possui buracos nesse intervalo e contém integralmente:

- 2016: 8.784 timestamps (ano bissexto);
- 2017: 8.760 timestamps;
- 2018: 8.760 timestamps.

Isso valida **cobertura temporal remota**. Não significa que os arquivos locais de 2016–2018 já tenham sido materializados. A v0.3 exige validação por célula/variável após o download antes de marcar um ano local como `complete`.
