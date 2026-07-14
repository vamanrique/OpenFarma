"""
fix_auditoria_conc12.py — Duodécima ronda de auditoría.

Correcciones:
  A) NAFAZOLINA id=3438: "0.001 mg/mL" -> "1 mg/mL"
     - Todos los demás productos nafazolina oftálmica son 1 mg/mL (0.1%)
     - "Luz Zul" 0.001 mg/mL es 1000x menos que todos los demás: claramente error ETL
     - También actualiza concentracion_mg_ml en cum_normalizado
     - Merge en id=3060 (NAFAZOLINA 1 mg/mL, n=41)
  B) DESMOPRESINA NASAL: merge id=3276 (0.1 mg/mL) -> id=1800 (10 mcg/dosis)
     - Mismos productos "Dicpresina Spray Nasal" (expediente 20080728)
     - ETL asignó algunos a grupo mcg/dosis (cuando tenía dosis_mg) y otros a mg/mL
     - 0.1 mg/mL = 100 mcg/mL; 10 mcg/spray (a 0.1 mL/spray) = misma concentración
  C) COLISTINA||HIDROCORTISONA||NEOMICINA OTICO id=3910: corregir orden de componentes
     - Concentracion_norm debe seguir el orden alfabético del dci_key
     - "5 mg/mL + 1.538 mg/mL + 5 mg/mL" (COLISTINA=5, HIDROCORTISONA=1.538)
     - Corrección: "1.538 mg/mL + 5 mg/mL + 5 mg/mL" (COLISTINA=1.538, HIDROCORTISONA=5)
     - Componentes del producto Fixamicin: hidrocortisona=5, colistina=1.538, neomicina=5
  D) ESTRADIOL TRANSDERMICO id=2013: "1.5 mg" -> "1.53 mg"
     - Producto "Lenzetto" tiene dosis_mg=1.53; la concentración 1.5 es un redondeo inexacto
  E) Post-fix auto-merge duplicados
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP merge] {del_id}->{keep_id}: missing")
        return 0
    merged = list(dict.fromkeys(
        json.loads(keep[0] or '[]') + json.loads(rem[0] or '[]')
    ))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}->{keep_id}: total={len(merged)}")
    return 1


def fix_conc(cur, gid: int, new_conc: str, tag: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{row[0]}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. NAFAZOLINA id=3438: error 1000x -----------------------------------------
    print("\n=== A. NAFAZOLINA id=3438 ===")
    n['A'] += fix_conc(cur, 3438, "1 mg/mL", "A_nafazolina_1000x")
    # Sync concentracion_mg_ml in cum_normalizado for Luz Zul products
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3438")
    g = cur.fetchone()
    if g:
        cids = json.loads(g[0] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("""
                UPDATE cum_normalizado
                SET concentracion_mg_ml=1.0,
                    componentes=replace(componentes, '0.001', '1.0')
                WHERE expediente_cum=? AND consecutivo_cum=?
                AND concentracion_mg_ml < 0.01
            """, (exp, consec))
            if cur.rowcount:
                updated += 1
        print(f"  [A] cum_normalizado: {updated} productos actualizados a 1 mg/mL")
    n['merge'] += merge_into(con, 3060, 3438)

    # -- B. DESMOPRESINA NASAL: merge id=3276 -> id=1800 ----------------------------
    print("\n=== B. DESMOPRESINA NASAL merge ===")
    # Both groups are "Dicpresina Spray Nasal" (expediente 20080728)
    # id=1800 "10 mcg/dosis" is the preferred clinical format
    # id=3276 "0.1 mg/mL" = same concentration, different unit expression
    n['merge'] += merge_into(con, 1800, 3276)

    # -- C. COLISTINA||HIDROCORTISONA||NEOMICINA id=3910: fix component order --------
    print("\n=== C. COLISTINA||HIDROCORTISONA||NEOMICINA id=3910 ===")
    # DCI alphabetical: COLISTINA=1.538, HIDROCORTISONA=5.0, NEOMICINA=5.0
    # Current norm has them swapped: "5 + 1.538 + 5"
    n['C'] += fix_conc(cur, 3910, "1.538 mg/mL + 5 mg/mL + 5 mg/mL", "C_colistina_swap_fix")

    # -- D. ESTRADIOL TRANSDERMICO id=2013: fix rounding ----------------------------
    print("\n=== D. ESTRADIOL TRANSDERMICO id=2013 ===")
    n['D'] += fix_conc(cur, 2013, "1.53 mg", "D_estradiol_lenzetto_precision")

    # -- E. Post-fix auto-merge duplicados ------------------------------------------
    print("\n=== E. Post-fix auto-merge ===")
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

    # -- Fix n_productos ------------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen --------------------------------------------------------------------
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
