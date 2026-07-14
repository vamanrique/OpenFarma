"""
fix_auditoria_conc91.py — Nonagésimoprimera ronda de auditoría.

Surfactantes pulmonares — corrección de denominaciones restantes:

  A) id=684 (Survanta 4mL):
     DCI: 'FOSFOLIPIDOS TOTALES' → 'BERACTANT'
     Conc: '6.2 mg/mL' → SIN_CONCENTRACION
     Survanta = beractant (extracto lipídico bovino). El expediente 19915281
     registró el componente fosfolípidos totales en lugar del INN OMS.
     → auto-merge con id=3554 (BERACTANT|INYECTABLE|SIN_CONCENTRACION, 7 prod.)

  B) id=1088 (Infasurf 3.0mL, 6.0mL):
     DCI: 'FOSFOLIPIDOS' → 'CALFACTANT'
     Conc: '35 mg/mL' → SIN_CONCENTRACION
     Infasurf (ONY Inc.) = calfactant: extracto de pulmón de ternera.
     INN OMS: calfactant. Diferente de beractant (bovino adulto) y poractant
     alfa (porcino). 35 mg/mL es la conc. de fosfolípidos, no del INN único.
     Sin merge: no existe grupo CALFACTANT previo.
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"


def safe_json(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP merge] {del_id}->{keep_id}: missing")
        return 0
    merged = list(dict.fromkeys(safe_json(keep[0]) + safe_json(rem[0])))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}->{keep_id}: total={len(merged)}")
    return 1


def rename_surfactant(con, gid: int, new_dci: str, new_conc: str) -> int:
    cur = con.cursor()
    cur.execute("SELECT dci_key, concentracion_norm, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_dci, old_conc, cum_ids_str = row
    if old_dci == new_dci:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET dci_key=?, concentracion_norm=? WHERE id=?",
                (new_dci, new_conc, gid))
    print(f"  [RENAME] id={gid}: '{old_dci}' -> '{new_dci}'")
    if old_conc != new_conc:
        print(f"    conc: '{old_conc}' -> '{new_conc}'")
    cids = safe_json(cum_ids_str)
    updated = 0
    for cid in cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                    (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = safe_json(p[0])
            if pdci != [new_dci]:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps([new_dci]), exp, consec))
                updated += 1
    if updated:
        print(f"    cum_normalizado: {updated} productos actualizados")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # A. id=684 Survanta 4mL: FOSFOLIPIDOS TOTALES → BERACTANT
    print("\n=== A. id=684 Survanta 4mL: FOSFOLIPIDOS TOTALES -> BERACTANT ===")
    n['A'] += rename_surfactant(con, 684, "BERACTANT", "SIN_CONCENTRACION")

    # B. id=1088 Infasurf: FOSFOLIPIDOS → CALFACTANT
    print("\n=== B. id=1088 Infasurf: FOSFOLIPIDOS -> CALFACTANT ===")
    n['B'] += rename_surfactant(con, 1088, "CALFACTANT", "SIN_CONCENTRACION")

    # Post-fix auto-merge
    print("\n=== Post-fix auto-merge ===")
    cur = con.cursor()
    cur.execute("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as cnt,
               GROUP_CONCAT(id || ':' || n_productos ORDER BY n_productos DESC)
        FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING cnt > 1
    """)
    for dci, via, conc, cnt, ids_str in cur.fetchall():
        pairs = [(int(x.split(':')[0]), int(x.split(':')[1])) for x in ids_str.split(',')]
        keep_id = pairs[0][0]
        for del_id, _ in pairs[1:]:
            n['merge'] += merge_into(con, keep_id, del_id)

    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    print("\n=== RESUMEN ===")
    for k, v in n.items():
        if v:
            print(f"  {k}: {v}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_norm='SIN_CONCENTRACION'")
    sin = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm HAVING COUNT(*) > 1
    """)
    dups = len(cur.fetchall())
    print(f"\nDB: {total} grupos | {sin} SIN_CONCENTRACION | {dups} duplicados")
    con.close()


if __name__ == "__main__":
    main()
