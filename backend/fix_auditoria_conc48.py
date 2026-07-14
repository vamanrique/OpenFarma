"""
fix_auditoria_conc48.py — Cuadragesimoctava ronda de auditoría.

Correcciones — nombres en inglés y typos (DeepSeek + análisis manual):

  A) LEVOCETIRICINA -> LEVOCETIRIZINA (typo: falta Z; CETIRIZINA es el INN correcto):
     - id=2092: LEVOCETIRICINA SO 5mg (n=4) -> auto-merge id=832 (n=102->106)
     - id=2093: LEVOCETIRICINA||MONTELUKAST SO 5+10mg (n=1) -> auto-merge id=2097 (n=31->32)
     - id=1697: DEXTROMETORFANO||FENILEFRINA||IBUPROFENO||LEVOCETIRICINA SO (n=19) -> auto-merge id=1525 (n=54->73)
     - id=1788: FENILEFRINA||LEVOCETIRICINA||PARACETAMOL LO SIN_CONC (n=15) -> auto-merge id=1787 (n=30->45)

  B) LINEZOLIDA -> LINEZOLID (INN WHO sin -a; LINEZOLID es la forma mayoritaria con n=52):
     - id=1641: LINEZOLIDA IN 2mg/mL (n=4) -> auto-merge id=641 (n=31->35)
     - id=3901: LINEZOLIDA SO 600mg (n=3) -> auto-merge id=663 (n=21->24)

  C) LOXOPROFEN -> LOXOPROFENO (inglés -> español INN -o):
     - id=1853: LOXOPROFEN SO 60mg (n=5) -> auto-merge id=1854 (n=7->12)

  D) MEBROFENIN -> MEBROFENINA (inglés -> español INN -a):
     - id=2569: MEBROFENIN IN 40mg (n=1) -> sin merge (concentracion distinta)

  E) METOXALEM -> METOXALENO (inglés -> español INN -o; psoraleno):
     - id=403: METOXALEM SO 10mg (n=9) -> sin merge (no existe METOXALENO SO)
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    lc_map = {"LEVOCETIRICINA": "LEVOCETIRIZINA"}

    # -- A. LEVOCETIRICINA -> LEVOCETIRIZINA -----------------------------------------
    print("\n=== A. LEVOCETIRICINA -> LEVOCETIRIZINA ===")
    n['A'] += rename_dci(con, 2092, "LEVOCETIRIZINA", lc_map)
    n['A'] += rename_dci(con, 2093, "LEVOCETIRIZINA||MONTELUKAST", lc_map)
    n['A'] += rename_dci(con, 1697,
        "DEXTROMETORFANO||FENILEFRINA||IBUPROFENO||LEVOCETIRIZINA", lc_map)
    n['A'] += rename_dci(con, 1788,
        "FENILEFRINA||LEVOCETIRIZINA||PARACETAMOL", lc_map)

    # -- B. LINEZOLIDA -> LINEZOLID (INN oficial sin -a) ------------------------------
    print("\n=== B. LINEZOLIDA -> LINEZOLID ===")
    lz_map = {"LINEZOLIDA": "LINEZOLID"}
    n['B'] += rename_dci(con, 1641, "LINEZOLID", lz_map)
    n['B'] += rename_dci(con, 3901, "LINEZOLID", lz_map)

    # -- C. LOXOPROFEN -> LOXOPROFENO -------------------------------------------------
    print("\n=== C. LOXOPROFEN -> LOXOPROFENO ===")
    n['C'] += rename_dci(con, 1853, "LOXOPROFENO", {"LOXOPROFEN": "LOXOPROFENO"})

    # -- D. MEBROFENIN -> MEBROFENINA -------------------------------------------------
    print("\n=== D. MEBROFENIN -> MEBROFENINA ===")
    n['D'] += rename_dci(con, 2569, "MEBROFENINA", {"MEBROFENIN": "MEBROFENINA"})

    # -- E. METOXALEM -> METOXALENO ---------------------------------------------------
    print("\n=== E. METOXALEM -> METOXALENO ===")
    n['E'] += rename_dci(con, 403, "METOXALENO", {"METOXALEM": "METOXALENO"})

    # -- F. Post-fix auto-merge -------------------------------------------------------
    print("\n=== F. Post-fix auto-merge ===")
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
