"""
fix_auditoria_conc51.py — Quincuagesimoprimera ronda de auditoría.

Correcciones — nombres inglés sin sufijo -o/-a (español INN requiere terminación):

  A) SILDENAFIL -> SILDENAFILO (INN español con -o):
     - id=522: SILDENAFIL SO 50mg (n=10) -> auto-merge id=624 (SILDENAFILO SO 50mg, n=134->144)

  B) TADALAFIL -> TADALAFILO (INN español con -o):
     - id=784: TADALAFIL SO 20mg (n=19) -> auto-merge id=1203 (n=212->231)
     - id=1281: TADALAFIL SO 5mg (n=45) -> auto-merge id=1444 (n=177->222)

  C) VARDENAFIL -> VARDENAFILO (INN español con -o):
     - id=2554: VARDENAFIL SO 20mg (n=3) -> auto-merge id=1934 (n=3->6)

  D) VERAPAMIL -> VERAPAMILO (INN español con -o):
     - id=317: VERAPAMIL SO 120mg (n=2) -> auto-merge id=315 (n=8->10)

  E) SEVELAMER -> SEVELAMERO (INN español con -o):
     - id=1384: SEVELAMER SO 800mg (n=8) -> auto-merge id=1778 (n=5->13)

  F) TREPROSTINIL -> TREPROSTINILO (INN español con -o):
     - id=2157: TREPROSTINIL INHALADO 0.6mg/mL (n=5) -> sin merge
     - id=1845: TREPROSTINIL IN 1mg/mL (n=6) -> sin merge
     - id=1849: TREPROSTINIL IN 10mg/mL (n=6) -> auto-merge id=2316 (n=2->8)
     - id=1844: TREPROSTINIL IN 2.5mg/mL (n=8) -> sin merge
     - id=1608: TREPROSTINIL IN 5mg/mL (n=6) -> auto-merge id=2315 (n=2->8)

  G) TEMOZOLAMIDA -> TEMOZOLOMIDA (typo: a->o en posicion 7; INN correcto):
     - id=1663: TEMOZOLAMIDA SO 100mg (n=7) -> auto-merge id=638 (n=3->10)
     - id=1664: TEMOZOLAMIDA SO 20mg (n=5) -> auto-merge id=640 (n=4->9)
     - id=1662: TEMOZOLAMIDA SO 250mg (n=4) -> auto-merge id=639 (n=2->6)
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'merge']}

    # -- A. SILDENAFIL -> SILDENAFILO -------------------------------------------------
    print("\n=== A. SILDENAFIL -> SILDENAFILO ===")
    n['A'] += rename_dci(con, 522, "SILDENAFILO", {"SILDENAFIL": "SILDENAFILO"})

    # -- B. TADALAFIL -> TADALAFILO ---------------------------------------------------
    print("\n=== B. TADALAFIL -> TADALAFILO ===")
    td_map = {"TADALAFIL": "TADALAFILO"}
    n['B'] += rename_dci(con, 784, "TADALAFILO", td_map)
    n['B'] += rename_dci(con, 1281, "TADALAFILO", td_map)

    # -- C. VARDENAFIL -> VARDENAFILO -------------------------------------------------
    print("\n=== C. VARDENAFIL -> VARDENAFILO ===")
    n['C'] += rename_dci(con, 2554, "VARDENAFILO", {"VARDENAFIL": "VARDENAFILO"})

    # -- D. VERAPAMIL -> VERAPAMILO ---------------------------------------------------
    print("\n=== D. VERAPAMIL -> VERAPAMILO ===")
    n['D'] += rename_dci(con, 317, "VERAPAMILO", {"VERAPAMIL": "VERAPAMILO"})

    # -- E. SEVELAMER -> SEVELAMERO ---------------------------------------------------
    print("\n=== E. SEVELAMER -> SEVELAMERO ===")
    n['E'] += rename_dci(con, 1384, "SEVELAMERO", {"SEVELAMER": "SEVELAMERO"})

    # -- F. TREPROSTINIL -> TREPROSTINILO ---------------------------------------------
    print("\n=== F. TREPROSTINIL -> TREPROSTINILO ===")
    trep_map = {"TREPROSTINIL": "TREPROSTINILO"}
    n['F'] += rename_dci(con, 2157, "TREPROSTINILO", trep_map)
    n['F'] += rename_dci(con, 1845, "TREPROSTINILO", trep_map)
    n['F'] += rename_dci(con, 1849, "TREPROSTINILO", trep_map)
    n['F'] += rename_dci(con, 1844, "TREPROSTINILO", trep_map)
    n['F'] += rename_dci(con, 1608, "TREPROSTINILO", trep_map)

    # -- G. TEMOZOLAMIDA -> TEMOZOLOMIDA ----------------------------------------------
    print("\n=== G. TEMOZOLAMIDA -> TEMOZOLOMIDA ===")
    tmz_map = {"TEMOZOLAMIDA": "TEMOZOLOMIDA"}
    n['G'] += rename_dci(con, 1663, "TEMOZOLOMIDA", tmz_map)
    n['G'] += rename_dci(con, 1664, "TEMOZOLOMIDA", tmz_map)
    n['G'] += rename_dci(con, 1662, "TEMOZOLOMIDA", tmz_map)

    # -- H. Post-fix auto-merge -------------------------------------------------------
    print("\n=== H. Post-fix auto-merge ===")
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
