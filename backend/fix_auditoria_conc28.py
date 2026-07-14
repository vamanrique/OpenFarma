"""
fix_auditoria_conc28.py — Vigesimoctava ronda de auditoría.

Correcciones:
  A) CONDROITIN -> CONDROITINA (id=754 LIQUIDO_ORAL SIN_CONC, n=7)
     -> merge con id=951 (CONDROITINA||GLUCOSAMINA LIQUIDO_ORAL SIN_CONC, n=57 -> n=64)
  B) ZINC OXIDO -> OXIDO DE ZINC (forma DE estándar):
     - id=1467: ZINC OXIDO TOPICO 25% -> OXIDO DE ZINC -> merge id=1473 (n=10+23=33)
     - id=2635: HIDROCORTISONA||LIDOCAINA||SUBACETATO DE ALUMINIO||ZINC OXIDO RECTAL
       -> HIDROCORTISONA||LIDOCAINA||OXIDO DE ZINC||SUBACETATO DE ALUMINIO
       + fix conc "35+2.5+50+180" -> "35+2.5+180+50" (OXIDO(3°)<SUBACETATO(4°) en orden alphabético)
     - id=3399: HIERRO (III) OXIDO||ZINC OXIDO TOPICO -> HIERRO (III) OXIDO||OXIDO DE ZINC
       (H<O: mismo orden, no requiere reorden de conc)
  C) DTPA normalización -> ACIDO PENTETICO (INN):
     - id=1868: ACIDO DIETILEN TRIAMINO PENTAACETICO 10mg INYECTABLE -> merge id=2568 (n=2)
     - id=2571: ACIDO DIETILENTRIAMINOPENTAACETICO 5mg -> ACIDO PENTETICO (nuevo grupo)
  D) DMSA normalización:
     - id=2574: ACIDO 2,3-DIMERCAPTOSUCCINICO 1mg -> ACIDO DIMERCAPTOSUCCINICO
       (distinto conc de id=3335 SIN_CONC: no hay merge)
  E) MAGNESIO OXIDO -> OXIDO DE MAGNESIO:
     - id=2018: ACIDO CITRICO||MAGNESIO OXIDO||PICOSULFATO DE SODIO LIQUIDO_ORAL SIN_CONC
       -> ACIDO CITRICO||OXIDO DE MAGNESIO||PICOSULFATO DE SODIO (A<O<P: misma posición relativa)
  F) Post-fix auto-merge duplicados
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


def fix_conc(cur, gid: int, new_conc: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya conc] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [FIX_CONC] id={gid}: '{row[0]}' -> '{new_conc}'")
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

    # -- A. CONDROITIN -> CONDROITINA ------------------------------------------------
    print("\n=== A. id=754: CONDROITIN -> CONDROITINA ===")
    n['A'] += rename_dci(con, 754, "CONDROITINA||GLUCOSAMINA",
                         {"CONDROITIN": "CONDROITINA"})
    # auto-merge: 754 (n=7) -> 951 (CONDROITINA||GLUCOSAMINA LIQUIDO_ORAL SIN_CONC, n=57)

    # -- B. ZINC OXIDO -> OXIDO DE ZINC ----------------------------------------------
    print("\n=== B. ZINC OXIDO -> OXIDO DE ZINC ===")
    zo_map = {"ZINC OXIDO": "OXIDO DE ZINC"}

    # id=1467: solo ZINC OXIDO 25% -> OXIDO DE ZINC, merge id=1473
    n['B'] += rename_dci(con, 1467, "OXIDO DE ZINC", zo_map)
    # auto-merge 1467->1473 (25% TOPICO)

    # id=2635: HIDROCORTISONA||LIDOCAINA||SUBACETATO DE ALUMINIO||ZINC OXIDO
    # -> HIDROCORTISONA||LIDOCAINA||OXIDO DE ZINC||SUBACETATO DE ALUMINIO
    # conc reorder: OZn(3rd)=180, SA(4th)=50 in new alphabetical order
    n['B'] += rename_dci(con, 2635,
                         "HIDROCORTISONA||LIDOCAINA||OXIDO DE ZINC||SUBACETATO DE ALUMINIO",
                         zo_map)
    fix_conc(cur, 2635, "35 mg/mL + 2.5 mg/mL + 180 mg/mL + 50 mg/mL")

    # id=3399: HIERRO (III) OXIDO||ZINC OXIDO -> same H<O order, no conc reorder
    n['B'] += rename_dci(con, 3399, "HIERRO (III) OXIDO||OXIDO DE ZINC", zo_map)

    # -- C. DTPA: ACIDO PENTETICO (INN) ----------------------------------------------
    print("\n=== C. DTPA -> ACIDO PENTETICO ===")
    n['C'] += rename_dci(con, 1868, "ACIDO PENTETICO",
                         {"ACIDO DIETILEN TRIAMINO PENTAACETICO": "ACIDO PENTETICO"})
    # auto-merge: 1868 (10mg) -> 2568 (ACIDO PENTETICO 10mg INYECTABLE)
    n['C'] += rename_dci(con, 2571, "ACIDO PENTETICO",
                         {"ACIDO DIETILENTRIAMINOPENTAACETICO": "ACIDO PENTETICO"})
    # 2571 (5mg) stays solo (different conc from 2568 10mg)

    # -- D. DMSA: ACIDO DIMERCAPTOSUCCINICO ------------------------------------------
    print("\n=== D. id=2574: ACIDO 2,3-DIMERCAPTOSUCCINICO -> ACIDO DIMERCAPTOSUCCINICO ===")
    n['D'] += rename_dci(con, 2574, "ACIDO DIMERCAPTOSUCCINICO",
                         {"ACIDO 2,3-DIMERCAPTOSUCCINICO": "ACIDO DIMERCAPTOSUCCINICO"})

    # -- E. MAGNESIO OXIDO -> OXIDO DE MAGNESIO --------------------------------------
    print("\n=== E. id=2018: MAGNESIO OXIDO -> OXIDO DE MAGNESIO ===")
    n['E'] += rename_dci(con, 2018,
                         "ACIDO CITRICO||OXIDO DE MAGNESIO||PICOSULFATO DE SODIO",
                         {"MAGNESIO OXIDO": "OXIDO DE MAGNESIO"})

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
