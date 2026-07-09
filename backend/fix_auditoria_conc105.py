"""
Ronda 105 — Normalización de principios_dci en cum_normalizado.

Sincroniza principios_dci con el dci_key del grupo asignado para 700 productos
en 35 patrones de sustitución. Incluye correcciones de asignación de grupo para
casos donde el producto está en el grupo equivocado.

Categorías:
  - Sinónimos HIOSCINA: HIOSCINA / HIOSCINA BUTILBROMURO / HIOSCINA N-BUTILBROMURO /
    ESCOPOLAMINA / HIOSCINA BUTILBROMURO / IBUPROFENO||SCOPOLAMINA → BUTILBROMURO DE HIOSCINA
  - Typo: OOLANZAPINAA → OLANZAPINA
  - Ortografía: CLORFENAMINA → CLORFENIRAMINA
  - Género: ENTACAPONE → ENTACAPONA
  - Acento: CAFÉ(con tilde) → CAFEINA; ÁCIDO CLAVULÁNICO → ACIDO CLAVULANICO;
    EXTRACTOS ALERGENICOS (acento) → sin acento; ARTICAINA (acento) → sin acento
  - Duplicados: BETAMETASONA||BETAMETASONA → BETAMETASONA; DEXAMETASONA||DEXAMETASONA;
    CALCIO||POTASIO||SODIO||SODIO → CALCIO||POTASIO||SODIO
  - INN: TRIGLICERIDOS DE CADENA MEDIANA → CADENA MEDIA; GELATINA SUCCILINADA → SUCCINILADA
  - Nombre comercial→INN: LAMICOL→TERBINAFINA; OVALE CHAMPU→KETOCONAZOL; DCI→KETOCONAZOL
  - Sinónimo: TRETINOINA → ACIDO RETINOICO (en el contexto del grupo)
  - Neosaldina: BUTILBROMURO DE HIOSCINA||CAFEÍNA||METAMIZOL → CAFEINA||ISOMETEPTENO||METAMIZOL
  - Tenaflox: METRONIDAZOL en grupo LEVOFLOXACINO → LEVOFLOXACINO
  - FEIBA: FACTOR VIII → FACTOR VIII INHIBIDOR BYPASS ACTIVITY
  - Baxul F: BROMHEXINA||FENILEFRINA||PARACETAMOL en grupo BACLOFENO → mover a grupo correcto

Uso:
    python fix_auditoria_conc105.py [--dry-run]
"""

import sqlite3
import json
import sys
from datetime import datetime

DRY_RUN = '--dry-run' in sys.argv
DB = 'farmavigia.db'

conn = sqlite3.connect(DB)
c = conn.cursor()

fixes_dci = 0
fixes_grupo = 0

print(f"{'[DRY-RUN] ' if DRY_RUN else ''}Ronda 105 - Normalizacion DCI en cum_normalizado")
print("=" * 70)

# ---------------------------------------------------------------------------
# Fase 1: Correcciones de asignación de grupo
# Productos en grupo equivocado — el dci_key del grupo no corresponde al producto
# ---------------------------------------------------------------------------

print("\n--- Fase 1: Correcciones de asignación de grupo ---")

# 1a. Baxul F (BROMHEXINA||FENILEFRINA||PARACETAMOL) está en el grupo BACLOFENO
#     → mover al grupo BROMHEXINA||FENILEFRINA||PARACETAMOL
BAXUL_IDS = ['20007872-1', '20007872-2']
BAXUL_DCI_KEY = 'BROMHEXINA||FENILEFRINA||PARACETAMOL'

c.execute("SELECT id, cum_ids FROM grupos_equivalencia WHERE dci_key=?", (BAXUL_DCI_KEY,))
bromhex_grupo = c.fetchone()

# Encontrar el grupo BACLOFENO que los contiene
c.execute("SELECT id, cum_ids FROM grupos_equivalencia WHERE dci_key='BACLOFENO'")
bac_grupos = c.fetchall()

for bgid, bcum_ids_json in bac_grupos:
    bcum_ids = json.loads(bcum_ids_json)
    affected = [cid for cid in BAXUL_IDS if cid in bcum_ids]
    if affected:
        print(f"  BACLOFENO grupo id={bgid}: remover {affected}")
        if not DRY_RUN:
            new_ids = [x for x in bcum_ids if x not in BAXUL_IDS]
            c.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=? WHERE id=?",
                      (json.dumps(new_ids), len(new_ids), datetime.now().isoformat(), bgid))
        fixes_grupo += len(affected)

if bromhex_grupo:
    bgid2, bcum_ids_json2 = bromhex_grupo
    current_ids = json.loads(bcum_ids_json2)
    to_add = [cid for cid in BAXUL_IDS if cid not in current_ids]
    if to_add:
        print(f"  BROMHEXINA grupo id={bgid2}: agregar {to_add}")
        if not DRY_RUN:
            new_ids = current_ids + to_add
            c.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=? WHERE id=?",
                      (json.dumps(new_ids), len(new_ids), datetime.now().isoformat(), bgid2))
else:
    # Crear nuevo grupo
    print(f"  Creando nuevo grupo para {BAXUL_DCI_KEY}")
    if not DRY_RUN:
        c.execute("""INSERT INTO grupos_equivalencia (dci_key, grupo_via, cum_ids, n_productos, revisado_ia, actualizado_en)
                     VALUES (?, 'SOLIDO_ORAL', ?, ?, 0, ?)""",
                  (BAXUL_DCI_KEY, json.dumps(BAXUL_IDS), len(BAXUL_IDS), datetime.now().isoformat()))
        print(f"    → Grupo creado id={c.lastrowid}")

# ---------------------------------------------------------------------------
# Fase 2: Sincronizar principios_dci con dci_key del grupo asignado
# Estrategia: para cada grupo, todos los productos en cum_ids deben tener
#             principios_dci == sorted(dci_key.split("||"))
# ---------------------------------------------------------------------------

print("\n--- Fase 2: Sincronizacion principios_dci -> dci_key ---")

c.execute("SELECT id, dci_key, cum_ids FROM grupos_equivalencia")
grupos = c.fetchall()

pair_counts: dict[tuple, int] = {}

for grupo_id, dci_key, cum_ids_json in grupos:
    cum_ids = json.loads(cum_ids_json)
    dci_list = sorted(dci_key.split("||"))
    expected_json = json.dumps(dci_list, ensure_ascii=False)

    for cum_id in cum_ids:
        exp, cons = cum_id.rsplit('-', 1)
        c.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                  (exp, cons))
        r = c.fetchone()
        if not r or not r[0]:
            continue
        try:
            current = json.loads(r[0])
        except Exception:
            continue
        current_key = "||".join(sorted(current))
        if current_key != dci_key:
            pair = (current_key, dci_key)
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
            if not DRY_RUN:
                c.execute(
                    "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                    (expected_json, exp, cons)
                )
            fixes_dci += 1

for (cur, exp), n in sorted(pair_counts.items(), key=lambda x: -x[1]):
    print(f"  n={n:3d}  {cur!r:60s} -> {exp!r}")

# ---------------------------------------------------------------------------
# Resumen y checkpoint
# ---------------------------------------------------------------------------

print(f"\n{'[DRY-RUN] ' if DRY_RUN else ''}Resumen:")
print(f"  fixes_dci (principios_dci actualizados): {fixes_dci}")
print(f"  fixes_grupo (productos movidos de grupo): {fixes_grupo}")

if not DRY_RUN:
    conn.commit()
    print("\nCommit realizado.")
    print("WAL checkpoint...")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print("Checkpoint completado.")
else:
    print("\nDRY-RUN: sin cambios en la base de datos.")

conn.close()
