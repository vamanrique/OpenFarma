"""
fix_auditoria_conc55.py — Quincuagesimoquinta ronda de auditoría.

Correcciones — orden de palabras y normalización de nombre:

  A) BISMUTO SUBSALICILATO -> SUBSALICILATO DE BISMUTO (orden INN español: [sal] de [metal]):
     - id=366: BISMUTO SUBSALICILATO SO 262mg (n=13) -> auto-merge id=2512 (total=20)
     - id=3025: BISMUTO SUBSALICILATO LO 17.5mg/mL (n=14) -> sin merge
     - id=2512: BISMUTO, SUBSALICILATO DE SO 262mg (n=7) -> auto-merge id=366

  B) LEVOAMLODIPINO / LEVO-AMLODIPINO -> LEVAMLODIPINO (forma canónica WHO INN):
     - id=1694: IRBESARTAN||LEVOAMLODIPINO SO 300mg+2.5mg (n=15) -> sin merge
     - id=1700: IRBESARTAN||LEVOAMLODIPINO SO 150mg+2.5mg (n=15) -> sin merge
     - id=1576: LEVOAMLODIPINO||VALSARTAN SO 2.5mg+80mg (n=6) -> sin merge
     - id=1773: LEVO-AMLODIPINO||VALSARTAN SO 2.5mg+160mg (n=9) -> sin merge
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


def rename_dci(con, gid: int, new_dci: str, sync_map: dict) -> int:
    cur = con.cursor()
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_dci = row[0]
    if old_dci == new_dci:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_dci, gid))
    print(f"  [RENAME] id={gid}: '{old_dci[:70]}' -> '{new_dci[:70]}'")
    cids = safe_json(row[1])
    updated = 0
    for cid in cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                    (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = safe_json(p[0])
            new_pdci = [sync_map.get(d, d) for d in pdci]
            if new_pdci != pdci:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(new_pdci), exp, consec))
                updated += 1
    if updated:
        print(f"    cum_normalizado: {updated} productos actualizados")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # -- A. BISMUTO SUBSALICILATO -> SUBSALICILATO DE BISMUTO -------------------------
    print("\n=== A. BISMUTO SUBSALICILATO -> SUBSALICILATO DE BISMUTO ===")
    bism_map = {"BISMUTO SUBSALICILATO": "SUBSALICILATO DE BISMUTO",
                "BISMUTO, SUBSALICILATO DE": "SUBSALICILATO DE BISMUTO"}
    n['A'] += rename_dci(con, 366, "SUBSALICILATO DE BISMUTO", bism_map)
    n['A'] += rename_dci(con, 3025, "SUBSALICILATO DE BISMUTO", bism_map)
    n['A'] += rename_dci(con, 2512, "SUBSALICILATO DE BISMUTO", bism_map)

    # -- B. LEVOAMLODIPINO / LEVO-AMLODIPINO -> LEVAMLODIPINO -------------------------
    print("\n=== B. LEVOAMLODIPINO/LEVO-AMLODIPINO -> LEVAMLODIPINO ===")
    levo_map = {"LEVOAMLODIPINO": "LEVAMLODIPINO", "LEVO-AMLODIPINO": "LEVAMLODIPINO"}
    n['B'] += rename_dci(con, 1694, "IRBESARTAN||LEVAMLODIPINO", levo_map)
    n['B'] += rename_dci(con, 1700, "IRBESARTAN||LEVAMLODIPINO", levo_map)
    n['B'] += rename_dci(con, 1576, "LEVAMLODIPINO||VALSARTAN", levo_map)
    n['B'] += rename_dci(con, 1773, "LEVAMLODIPINO||VALSARTAN", levo_map)

    # -- C. Post-fix auto-merge -------------------------------------------------------
    print("\n=== C. Post-fix auto-merge ===")
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
