"""
fix_auditoria_conc33.py — Trigesimotercera ronda de auditoría.

Correcciones — sinonimia de INN y merges:
  A) ACIDO ALFA LIPOICO -> ACIDO TIOCTICO (INN estándar, sinónimo):
     - id=2011: SOLIDO_ORAL 600 mg (n=5)
     - auto-merge -> id=1941 (ACIDO TIOCTICO 600 mg, n=36 -> n=41)
  B) DEXTRAN -> DEXTRAN 70 (especificación de peso molecular estándar en colirios):
     - id=3122: DEXTRAN||HIDROXIPROPILMETILCELULOSA OFTALMICO 1+3 mg/mL (n=2)
     - auto-merge -> id=2725 (DEXTRAN 70||HIDROXIPROPILMETILCELULOSA 1+3 mg/mL, n=6 -> n=8)
  C) SUCCIMERO -> ACIDO DIMERCAPTOSUCCINICO (unificación con forma ya establecida en DB):
     - id=3703: SUCCIMERO INYECTABLE SIN_CONC (n=1, producto: Rphreno)
     - auto-merge -> id=3335 (ACIDO DIMERCAPTOSUCCINICO INYECTABLE SIN_CONC, n=1 -> n=2)
  D) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'merge']}

    # -- A. ACIDO ALFA LIPOICO -> ACIDO TIOCTICO -------------------------------------
    print("\n=== A. id=2011: ACIDO ALFA LIPOICO -> ACIDO TIOCTICO ===")
    n['A'] += rename_dci(con, 2011, "ACIDO TIOCTICO",
                         {"ACIDO ALFA LIPOICO": "ACIDO TIOCTICO"})
    # auto-merge 2011 (n=5) -> 1941 (ACIDO TIOCTICO SO 600mg, n=36) -> total=41

    # -- B. DEXTRAN -> DEXTRAN 70 (mismo orden D<H, sin reorden conc) ---------------
    print("\n=== B. id=3122: DEXTRAN -> DEXTRAN 70 ===")
    n['B'] += rename_dci(con, 3122, "DEXTRAN 70||HIDROXIPROPILMETILCELULOSA",
                         {"DEXTRAN": "DEXTRAN 70"})
    # auto-merge 3122 (n=2) -> 2725 (DEXTRAN 70||HPMC OF 1+3mg/mL, n=6) -> total=8

    # -- C. SUCCIMERO -> ACIDO DIMERCAPTOSUCCINICO ----------------------------------
    print("\n=== C. id=3703: SUCCIMERO -> ACIDO DIMERCAPTOSUCCINICO ===")
    n['C'] += rename_dci(con, 3703, "ACIDO DIMERCAPTOSUCCINICO",
                         {"SUCCIMERO": "ACIDO DIMERCAPTOSUCCINICO"})
    # auto-merge 3703 (n=1) -> 3335 (ACIDO DIMERCAPTOSUCCINICO IN SIN_CONC, n=1) -> total=2

    # -- D. Post-fix auto-merge -------------------------------------------------------
    print("\n=== D. Post-fix auto-merge ===")
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
