"""
fix_auditoria_conc27.py — Vigesimoséptima ronda de auditoría.

Correcciones:
  A) id=263: último grupo con ALUMINIO HIDROXIDO/MAGNESIO CARBONATO/MAGNESIO HIDROXIDO
     -> CARBONATO DE MAGNESIO||HIDROXIDO DE ALUMINIO||HIDROXIDO DE MAGNESIO||SIMETICONA
     (conc "282 mg + 85 mg + 25 mg" conserva: MgCO3=None en todos los productos, dato incompleto ETL)
  B) VITAMINA E -> TOCOFEROL (INN estándar):
     - id=3141 GINKGO BILOBA||VITAMINA E -> GINKGO BILOBA||TOCOFEROL (n=2)
  C) VITAMINA A||VITAMINA D -> COLECALCIFEROL||RETINOL (Emulsión de Scott, LIQUIDO_ORAL SIN_CONC):
     - id=3355 -> COLECALCIFEROL||RETINOL (no merge: id=2785 es SOLIDO_ORAL)
  D) CONDROITINA SULFATO SODICO -> CONDROITINA SULFATO:
     - id=1220 LIQUIDO_ORAL SIN_CONC -> merge con id=1002 (n=13 -> n=28)
     - id=1229 SOLIDO_ORAL 1200+1500+2400 -> merge con id=1221 (n=15 -> n=24)
  E) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. id=263: último ALUMINIO HIDROXIDO||MAGNESIO CARBONATO||... ----------------
    print("\n=== A. id=263: ultimo grupo ALUMINIO HIDROXIDO/MAGNESIO CARBONATO ===")
    n['A'] += rename_dci(con, 263,
                         "CARBONATO DE MAGNESIO||HIDROXIDO DE ALUMINIO||HIDROXIDO DE MAGNESIO||SIMETICONA",
                         {
                             "ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO",
                             "MAGNESIO CARBONATO": "CARBONATO DE MAGNESIO",
                             "MAGNESIO HIDROXIDO": "HIDROXIDO DE MAGNESIO",
                         })

    # -- B. VITAMINA E -> TOCOFEROL (INN) -------------------------------------------
    print("\n=== B. id=3141: VITAMINA E -> TOCOFEROL ===")
    n['B'] += rename_dci(con, 3141, "GINKGO BILOBA||TOCOFEROL",
                         {"VITAMINA E": "TOCOFEROL"})

    # -- C. VITAMINA A||VITAMINA D -> COLECALCIFEROL||RETINOL (Emulsion de Scott) ----
    print("\n=== C. id=3355: VITAMINA A||VITAMINA D -> COLECALCIFEROL||RETINOL ===")
    n['C'] += rename_dci(con, 3355, "COLECALCIFEROL||RETINOL",
                         {"VITAMINA A": "RETINOL", "VITAMINA D": "COLECALCIFEROL"})

    # -- D. CONDROITINA SULFATO SODICO -> CONDROITINA SULFATO -----------------------
    print("\n=== D. CONDROITINA SULFATO SODICO -> CONDROITINA SULFATO ===")
    cs_map = {"CONDROITINA SULFATO SODICO": "CONDROITINA SULFATO"}
    new_cs_dci = "CONDROITINA SULFATO||GLUCOSAMINA SULFATO||METILSULFONILMETANO"
    n['D'] += rename_dci(con, 1220, new_cs_dci, cs_map)
    # auto-merge: 1220 (LIQUIDO_ORAL SIN_CONC, n=15) -> 1002 (n=13) -> total=28
    n['D'] += rename_dci(con, 1229, new_cs_dci, cs_map)
    # auto-merge: 1229 (SOLIDO_ORAL 1200+1500+2400, n=9) -> 1221 (n=15) -> total=24

    # -- E. Post-fix auto-merge -------------------------------------------------------
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
