# Predicta Web Studio v1.6.3

## Hotfix Produto

- Corrige erro `VariableDoesNotExist` após simular tarifa dinâmica.
- O template passa a ler `result.customer.distributor_id` e `result.customer.subsystem_id`.
- O nome da concessão continua vindo de `result.concession.sigla`, com fallback explícito e seguro para o agente tarifário.
- Adiciona teste regressivo que renderiza a tela usando o mesmo formato de resultado do Motor 2.
- Não altera modelos, datasets, contratos, cálculo tarifário ou resultados científicos.
