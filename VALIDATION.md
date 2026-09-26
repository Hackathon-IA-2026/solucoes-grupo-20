# Validação do patch ARCO

Validações realizadas antes do empacotamento:

- `py_compile` e AST dos scripts 47, 53, 62 e do instalador: OK.
- Contrato do adaptador ARCO validado offline com xarray sintético:
  - temperatura K -> °C;
  - precipitação horária m -> mm;
  - velocidade e rajada m/s -> km/h;
  - radiação horária J/m² -> W/m²;
  - precipitação e radiação diárias agregadas.
- Compatibilidade arquitetural: scripts 32/54 continuam recebendo os mesmos diretórios, manifests e cache anual produzidos pela camada `batch_openmeteo`; o ARCO é injetado por um endpoint local compatível, portanto não muda o contrato downstream.

## Política padrão

`--climate-historical-backend auto`:

1. cache local existente é reutilizado;
2. qualquer lacuna histórica vai ao proxy local ARCO;
3. Open-Meteo histórico não é chamado;
4. Open-Meteo/ECMWF continua reservado ao forecast operacional H01-H24.

## Sinais esperados no log

```
PREDICTA_ARCO_START: ...
PREDICTA_ARCO_READY: http://127.0.0.1:PORT/v1/archive
PREDICTA_CLIMATE_BACKEND: histórico faltante -> ERA5-Land/ERA5 ARCO
ARCO_PROXY_OK points=... dates=...
```

As mensagens legadas `Open-Meteo E2/E3 ...` podem continuar aparecendo porque pertencem à camada de cache/batching existente. Quando `PREDICTA_ARCO_READY` e `ARCO_PROXY_OK` aparecem, o provedor efetivo do histórico é ARCO.
