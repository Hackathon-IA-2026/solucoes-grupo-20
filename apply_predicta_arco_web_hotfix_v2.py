#!/usr/bin/env python3
from pathlib import Path

ROOT = Path.cwd()
target = ROOT / "web/studio/services/territory.py"

if not target.exists():
    raise SystemExit(
        f"Não encontrei {target}\n"
        "Execute este script a partir da raiz do projeto Predicta."
    )

text = target.read_text(encoding="utf-8")

old = """    df['subsystem_id'] = df['subsystem_id'].map(canonical_subsystem)"""

new = """    # Compatibilidade entre artefatos territoriais legados e a grade
    # climática canônica usada pelo ERA5-Land ARCO.
    #
    # Os climate_points_*_01deg.csv têm cell_id/latitude/longitude e podem
    # não carregar subsystem_id, pois o subsistema já é conhecido pelo
    # argumento desta função. Não devemos derrubar a interface por isso.
    if 'subsystem_id' not in df.columns:
        df['subsystem_id'] = canonical_subsystem(subsystem_id)
    else:
        df['subsystem_id'] = df['subsystem_id'].map(canonical_subsystem)
        # Se algum artefato trouxe subsystem_id vazio, o contexto da chamada
        # é a fonte autoritativa para completar o valor.
        df['subsystem_id'] = df['subsystem_id'].fillna(
            canonical_subsystem(subsystem_id)
        )"""

if old not in text:
    if "if 'subsystem_id' not in df.columns:" in text:
        print("INFO: correção de subsystem_id já parece estar aplicada.")
    else:
        raise SystemExit(
            "Não encontrei a linha esperada:\n"
            "    df['subsystem_id'] = df['subsystem_id'].map(canonical_subsystem)\n\n"
            "O arquivo pode ter sido alterado. Não fiz uma substituição arriscada."
        )
else:
    text = text.replace(old, new, 1)
    target.write_text(text, encoding="utf-8")
    print(f"OK: compatibilidade de subsystem_id aplicada em {target}")

print("""
Agora rode, nesta ordem:

1) Teste que estava falhando:
   python manage.py test \
     web.studio.tests.StudioWebSmokeTests.test_main_pages_render_without_project_artifacts \
     -v 2

2) Suíte web:
   python manage.py test web.studio -v 2

3) Se ambos passarem:
   python scripts/47_run_full_automation.py
""")
