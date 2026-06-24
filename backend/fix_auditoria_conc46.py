"""
fix_auditoria_conc46.py — Cuadragesimosexta ronda de auditoría.

Correcciones — nombres en inglés y errores tipográficos en DCI:

  A) IBANDRONATO -> ACIDO IBANDRONICO (INN oficial: acido ibandronico):
     - id=1059: IBANDRONATO SOLIDO_ORAL 150mg (n=5)
       auto-merge -> id=1010 (ACIDO IBANDRONICO SO 150mg, n=22 -> n=27)

  B) ACECLOFENAC -> ACECLOFENACO (nombre en inglés -> español INN):
     - id=1186: ACECLOFENAC SOLIDO_ORAL 100mg (n=22)
       auto-merge -> id=1622 (ACECLOFENACO SO 100mg, n=15 -> n=37)

  C) ADAPALENE -> ADAPALENO (nombre en inglés -> español INN):
     - id=1324: ADAPALENE TOPICO 0.1% (n=4)
       auto-merge -> id=486 (ADAPALENO TOP 0.1%, n=16 -> n=20)

  D) CLOBETAZOL -> CLOBETASOL (typo: Z->S):
     - id=973: CLOBETAZOL TOPICO 0.05% (n=4)
       auto-merge -> id=328 (CLOBETASOL TOP 0.05%, n=96 -> n=100)

  E) DEXLANZOPRAZOL -> DEXLANSOPRAZOL (typo: Z->S):
     - id=2419: DEXLANZOPRAZOL SOLIDO_ORAL 60mg (n=2)
       auto-merge -> id=1649 (DEXLANSOPRAZOL SO 60mg, n=29 -> n=31)
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. IBANDRONATO -> ACIDO IBANDRONICO (id=1059) --------------------------------
    print("\n=== A. IBANDRONATO -> ACIDO IBANDRONICO ===")
    n['A'] += rename_dci(con, 1059, "ACIDO IBANDRONICO", {"IBANDRONATO": "ACIDO IBANDRONICO"})

    # -- B. ACECLOFENAC -> ACECLOFENACO (id=1186) -------------------------------------
    print("\n=== B. ACECLOFENAC -> ACECLOFENACO ===")
    n['B'] += rename_dci(con, 1186, "ACECLOFENACO", {"ACECLOFENAC": "ACECLOFENACO"})

    # -- C. ADAPALENE -> ADAPALENO (id=1324) ------------------------------------------
    print("\n=== C. ADAPALENE -> ADAPALENO ===")
    n['C'] += rename_dci(con, 1324, "ADAPALENO", {"ADAPALENE": "ADAPALENO"})

    # -- D. CLOBETAZOL -> CLOBETASOL (id=973) -----------------------------------------
    print("\n=== D. CLOBETAZOL -> CLOBETASOL ===")
    n['D'] += rename_dci(con, 973, "CLOBETASOL", {"CLOBETAZOL": "CLOBETASOL"})

    # -- E. DEXLANZOPRAZOL -> DEXLANSOPRAZOL (id=2419) --------------------------------
    print("\n=== E. DEXLANZOPRAZOL -> DEXLANSOPRAZOL ===")
    n['E'] += rename_dci(con, 2419, "DEXLANSOPRAZOL", {"DEXLANZOPRAZOL": "DEXLANSOPRAZOL"})

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

    # -- Fix n_productos -------------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen ---------------------------------------------------------------------
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
