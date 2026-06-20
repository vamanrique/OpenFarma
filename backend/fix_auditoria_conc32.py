"""
fix_auditoria_conc32.py — Trigesimosegunda ronda de auditoría.

Correcciones — GLUCOSAMINA -> GLUCOSAMINA SULFATO (ETL stripped salt suffix):
  Evidencia: "Glucosamina Sulfato Polvo 1500 Mg" tiene principios_dci=["GLUCOSAMINA"] (id=3129)
  "FlexTril C" usa ["CONDROITINA", "GLUCOSAMINA"] sin SULFATO en ambos (id=951)

  A) Grupos con CONDROITINA SULFATO correcto pero GLUCOSAMINA sin SULFATO:
     - id=749:  CONDROITINA SULFATO||GLUCOSAMINA 400+500 -> GLUCOSAMINA SULFATO
                auto-merge -> id=2015 (CONDROITINA SULFATO||GLUCOSAMINA SULFATO 400+500, n=6+8=14)
     - id=1218: CONDROITINA SULFATO||GLUCOSAMINA||MSM 1200+1500+2400 -> GLUCOSAMINA SULFATO
                auto-merge -> id=1221 (n=4+24=28, luego +id=1219=43)
     - id=2020: CONDROITINA SULFATO||GLUCOSAMINA||MSM 600+750+250 -> GLUCOSAMINA SULFATO
                (no merge existente previo al rename; id=1833 se mergeará aquí)

  B) Grupos con ambos CONDROITINA y GLUCOSAMINA sin SULFATO:
     - id=951:  CONDROITINA||GLUCOSAMINA LO SIN_CONC -> auto-merge id=747 (n=64+8=72)
     - id=1061: CONDROITINA||GLUCOSAMINA SO 1200+1500 -> auto-merge id=1062 (n=8+2=10)
     - id=1146: CONDROITINA||GLUCOSAMINA SO 600+750 (sin merge: no hay grupo CS+GS 600+750)
     - id=1912: CONDROITINA||GLUCOSAMINA SO 400+500 -> auto-merge con id=2015/749 (total=19)
     - id=1219: CONDROITINA||GLUCOSAMINA||MSM SO 1200+1500+2400 -> auto-merge id=1221 (total)
     - id=1383: CONDROITINA||GLUCOSAMINA||MSM LO SIN_CONC -> auto-merge id=1220 (n=3+28=31)
     - id=1833: CONDROITINA||GLUCOSAMINA||MSM SO 600+750+250 -> auto-merge id=2020 (n=2+2=4)

  C) GLUCOSAMINA standalone (Glucosamina Sulfato Polvo):
     - id=3129: GLUCOSAMINA LO SIN_CONC -> GLUCOSAMINA SULFATO (n=56, sin merge existente)

  D) Post-fix auto-merge duplicados

  Nota: C < G y C < G < M: orden de componentes sin cambio, sin reorden de conc.
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

    gs_only = {"GLUCOSAMINA": "GLUCOSAMINA SULFATO"}
    both_map = {"CONDROITINA": "CONDROITINA SULFATO",
                "GLUCOSAMINA": "GLUCOSAMINA SULFATO"}
    cs_gs_2 = "CONDROITINA SULFATO||GLUCOSAMINA SULFATO"
    cs_gs_3 = "CONDROITINA SULFATO||GLUCOSAMINA SULFATO||METILSULFONILMETANO"

    # -- A. CONDROITINA SULFATO correcto, GLUCOSAMINA sin SULFATO --------------------
    print("\n=== A. CONDROITINA SULFATO + GLUCOSAMINA -> GLUCOSAMINA SULFATO ===")
    n['A'] += rename_dci(con, 749, cs_gs_2, gs_only)
    n['A'] += rename_dci(con, 1218, cs_gs_3, gs_only)
    n['A'] += rename_dci(con, 2020, cs_gs_3, gs_only)

    # -- B. Ambos CONDROITINA y GLUCOSAMINA sin SULFATO ------------------------------
    print("\n=== B. CONDROITINA||GLUCOSAMINA -> CONDROITINA SULFATO||GLUCOSAMINA SULFATO ===")
    n['B'] += rename_dci(con, 951,  cs_gs_2, both_map)
    n['B'] += rename_dci(con, 1061, cs_gs_2, both_map)
    n['B'] += rename_dci(con, 1146, cs_gs_2, both_map)
    n['B'] += rename_dci(con, 1912, cs_gs_2, both_map)
    n['B'] += rename_dci(con, 1219, cs_gs_3, both_map)
    n['B'] += rename_dci(con, 1383, cs_gs_3, both_map)
    n['B'] += rename_dci(con, 1833, cs_gs_3, both_map)

    # -- C. GLUCOSAMINA standalone -> GLUCOSAMINA SULFATO ----------------------------
    print("\n=== C. id=3129: GLUCOSAMINA -> GLUCOSAMINA SULFATO ===")
    n['C'] += rename_dci(con, 3129, "GLUCOSAMINA SULFATO", gs_only)

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
