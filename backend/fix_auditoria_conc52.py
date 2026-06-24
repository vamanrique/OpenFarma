"""
fix_auditoria_conc52.py — Quincuagesimosegunda ronda de auditoría.

Correcciones — typos y nombres erróneos:

  A) RILPIRIVINA -> RILPIVIRINA (typo: I->VI; INN español = rilpivirina):
     - id=1498: RILPIRIVINA SO 25mg (n=2) -> sin merge (combos ya usan RILPIVIRINA)

  B) TETROSFOSMINA -> TETRAFOSMINA (typo: TETROS->TETRA; INN = tetrafosmina):
     - id=2364: TETROSFOSMINA IN 0.2mg (n=2) -> auto-merge id=527 (n=2->4)

  C) THIMEROSAL -> TIMEROSAL (inglés->español; INN español = timerosal):
     - id=205: THIMEROSAL TOP 0.1% (n=1) -> sin merge

  D) TECNETIO -> TECNECIO (typo: E->EC; tecnecio es el nombre español del elemento):
     - id=763: TECNETIO TC-99M EXAMETAZIMA IN 0.2mg (n=1) -> sin merge

  E) TECNECIO (99MTC) PERTECNECTATO -> TECNECIO (99MTC) PERTECNETATO (typo: extra C):
     - id=3689: TECNECIO (99MTC) PERTECNECTATO INHALADO SIN_CONC (n=1) -> sin merge

  F) CEFTAROLINA FOSAMILO -> CEFTAROLINA FOSAMIL (INN correcto sin -o final):
     - id=1518: CEFTAROLINA FOSAMILO IN 600mg (n=2) -> sin merge
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'F', 'merge']}

    # -- A. RILPIRIVINA -> RILPIVIRINA ------------------------------------------------
    print("\n=== A. RILPIRIVINA -> RILPIVIRINA ===")
    n['A'] += rename_dci(con, 1498, "RILPIVIRINA", {"RILPIRIVINA": "RILPIVIRINA"})

    # -- B. TETROSFOSMINA -> TETRAFOSMINA ---------------------------------------------
    print("\n=== B. TETROSFOSMINA -> TETRAFOSMINA ===")
    n['B'] += rename_dci(con, 2364, "TETRAFOSMINA", {"TETROSFOSMINA": "TETRAFOSMINA"})

    # -- C. THIMEROSAL -> TIMEROSAL ---------------------------------------------------
    print("\n=== C. THIMEROSAL -> TIMEROSAL ===")
    n['C'] += rename_dci(con, 205, "TIMEROSAL", {"THIMEROSAL": "TIMEROSAL"})

    # -- D. TECNETIO -> TECNECIO ------------------------------------------------------
    print("\n=== D. TECNETIO TC-99M EXAMETAZIMA -> TECNECIO TC-99M EXAMETAZIMA ===")
    n['D'] += rename_dci(con, 763, "TECNECIO TC-99M EXAMETAZIMA",
                         {"TECNETIO TC-99M EXAMETAZIMA": "TECNECIO TC-99M EXAMETAZIMA"})

    # -- E. PERTECNECTATO -> PERTECNETATO ---------------------------------------------
    print("\n=== E. TECNECIO (99MTC) PERTECNECTATO -> TECNECIO (99MTC) PERTECNETATO ===")
    n['E'] += rename_dci(con, 3689, "TECNECIO (99MTC) PERTECNETATO",
                         {"TECNECIO (99MTC) PERTECNECTATO": "TECNECIO (99MTC) PERTECNETATO"})

    # -- F. CEFTAROLINA FOSAMILO -> CEFTAROLINA FOSAMIL -------------------------------
    print("\n=== F. CEFTAROLINA FOSAMILO -> CEFTAROLINA FOSAMIL ===")
    n['F'] += rename_dci(con, 1518, "CEFTAROLINA FOSAMIL",
                         {"CEFTAROLINA FOSAMILO": "CEFTAROLINA FOSAMIL"})

    # -- G. Post-fix auto-merge -------------------------------------------------------
    print("\n=== G. Post-fix auto-merge ===")
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
