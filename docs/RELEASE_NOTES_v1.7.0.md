# Predicta Web Studio v1.7.0

## Produto e tempo civil

- interface do consumidor convertida integralmente para `America/Sao_Paulo`;
- UTC permanece somente como contrato interno, persistência e auditoria;
- validade da tarifa ANEEL agora usa a data civil de São Paulo;
- curvas sintéticas são alinhadas à hora local.

## Replay histórico × operação

- novo seletor de modo;
- replay lista janelas completas de 24h a partir de `e3_real_pilot_predictions.parquet`;
- a janela escolhida reconstrói `system_signal_v1` em memória com a mesma lógica do Motor 1;
- modo operacional é bloqueado se o sinal usa `PERFECT_WEATHER_BACKTEST` ou não cobre o horizonte atual.

## Pressão de demanda D

`D` deixa explícita a população de comparação. O Motor 1 usa, em ordem:

1. mesma hora local + mês + `WEEKDAY/WEEKEND`, quando há amostra suficiente;
2. mesma hora local + mês;
3. mesma hora local + janela sazonal de três meses;
4. mesma hora local em todo o histórico disponível.

O método e o tamanho da referência são registrados em `quality_flags`.

## Resposta da demanda

A tela Produto agora calcula um cenário ilustrativo de deslocamento da parcela flexível:

- energia total de 24h é conservada;
- a tarifa dinâmica permanece fixa;
- a parcela flexível é realocada para horários mais baratos;
- há limite de headroom por hora;
- são apresentados custo sem mudança de hábito, custo otimizado, economia diária e extrapolação mensal ilustrativa.

## Validação de build

No ambiente de empacotamento:

```text
83 passed
2 skipped (somente I/O dependente de pyarrow ausente no ambiente de build)
```

O runtime Django deve ser validado no ambiente local com:

```bash
python manage.py check
python manage.py test web.studio
```
