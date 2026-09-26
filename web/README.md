# Predicta Web Studio

A camada web está ativa a partir da v1.5. Ela **não substitui** Motor 1/Motor 2 nem duplica a ciência do projeto; orquestra os scripts existentes, lê os artefatos versionados e apresenta resultados.

## Quickstart

```bash
pip install -e ".[dev,web]"
python manage.py migrate
python manage.py check
python manage.py runserver 127.0.0.1:8000
```

Abra `http://127.0.0.1:8000/`.

Documentação completa: `docs/WEB_STUDIO_MVP_v1.5.md`.
