# Adaptação do snapshot OpenMeteo para o Predicta

O snapshot de 2026-09-18 é parcial, mas contém padrões reutilizáveis. Esta fundação reaproveita apenas o que pode ser sustentado pelos arquivos disponíveis.

## O que foi preservado

| Snapshot OpenMeteo | Predicta |
|---|---|
| baseline com dez anos completos anteriores | `complete_previous_years: 10`, sem ano-alvo |
| `era5_land` como modelo histórico | ERA5-Land como fonte histórica climática |
| status `operational_baseline_not_official_climatological_normal` | mesmo status explícito |
| regras versionadas em config | `configs/incidents.yaml` versionado |
| timestamps com timezone e conversão segura | contrato exige UTC timezone-aware |
| RAW com hash SHA-256 e deduplicação | `motor_sin/common/provenance.py` |
| separação RAW / staging/derivado | `data/raw`, `interim`, `processed` |
| evento derivado não equivale a dano operacional | contratos usam exposição/coincidência, não falha |

## O que mudou por causa do novo problema

O snapshot era orientado a **localidade + dia**. O Predicta é orientado a:

```text
célula 0,1° × hora UTC
```

Por isso:

- baseline deixa de ser `cidade × mês` e passa a `cell_id × variável × hora × janela sazonal (DOY ±15)`;
- temperatura deixa de usar apenas `max/min` diário e passa a valor horário + percentil/anomalia;
- chuva diária de 50/100 mm **não foi convertida automaticamente** para mm/h;
- rajada máxima diária não foi tratada como equivalente a vento ERA5-Land 10 m;
- `storm_candidate` diário/composto não foi transportado sem uma regra de simultaneidade horária validada;
- eventos canônicos municipais foram substituídos por `grid_state_v1` e `asset_exposure_v1`.

## Regra metodológica importante

Os limiares percentílicos são uma **linha de base operacional do projeto**, não uma normal climatológica oficial. Essa distinção permanece explícita para evitar uma interpretação científica mais forte do que os dados suportam.
