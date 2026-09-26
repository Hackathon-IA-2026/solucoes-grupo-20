#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path.cwd()
territory = ROOT / "web/studio/services/territory.py"
test_real = ROOT / "tests/unit/test_real_pilot.py"

if not territory.exists():
    raise SystemExit(f"Não encontrei {territory}. Execute este script na raiz do projeto Predicta.")

text = territory.read_text(encoding="utf-8")

old_concat = "    df = pd.concat(rows, ignore_index=True).drop_duplicates('point_id')"
new_concat = """    # Alguns artefatos de grade climática (ex.: climate_points_*_01deg.csv)
    # usam cell_id em vez de point_id. O loader da interface não deve assumir
    # que todo CSV encontrado é um artefato territorial já normalizado.
    if not rows:
        return pd.DataFrame(columns=['point_id'])

    normalized_rows = []
    for frame in rows:
        if frame is None:
            continue
        frame = frame.copy()

        if 'point_id' not in frame.columns:
            if 'cell_id' in frame.columns:
                # Grade canônica 0,1° / ARCO: a célula é o identificador estável.
                frame['point_id'] = frame['cell_id'].astype(str)
            elif frame.empty:
                continue
            else:
                # CSV sem identificador territorial reconhecível: não deve
                # derrubar a página nem contaminar o conjunto de pontos.
                continue

        normalized_rows.append(frame)

    if not normalized_rows:
        return pd.DataFrame(columns=['point_id'])

    df = pd.concat(normalized_rows, ignore_index=True, sort=False)

    if df.empty:
        return df

    df = df.drop_duplicates('point_id')"""

if old_concat in text:
    text = text.replace(old_concat, new_concat, 1)
else:
    print("AVISO: não encontrei a linha exata do pd.concat; talvez o arquivo já tenha sido alterado.")

old_points = "    points = load_points(subsystem_id)\n"
new_points = """    points = load_points(subsystem_id)
    if points.empty:
        return []
"""
# Patch only first occurrence inside event_points_for_date if present and not already protected.
if old_points in text and "points = load_points(subsystem_id)\n    if points.empty:" not in text:
    # Prefer insertion after function signature if possible.
    marker = "def event_points_for_date("
    idx = text.find(marker)
    if idx >= 0:
        sub = text[idx:]
        pos = sub.find(old_points)
        if pos >= 0:
            abspos = idx + pos
            text = text[:abspos] + text[abspos:].replace(old_points, new_points, 1)

territory.write_text(text, encoding="utf-8")
print(f"OK: patch aplicado em {territory}")

# Warning não bloqueante: tornar o delta explícito se a linha exata existir.
if test_real.exists():
    t = test_real.read_text(encoding="utf-8")
    old = "target-pd.Timedelta(hours=24*d)"
    new = "target-np.timedelta64(d, 'D')"
    if old in t:
        t = t.replace(old, new)
        test_real.write_text(t, encoding="utf-8")
        print(f"OK: warning de timedelta ajustado em {test_real}")
    else:
        print("INFO: linha do warning não encontrada ou já corrigida.")

print("\nAgora rode:")
print("  python manage.py test web.studio.tests.StudioWebSmokeTests.test_main_pages_render_without_project_artifacts -v 2")
print("  python manage.py test web.studio -v 2")
