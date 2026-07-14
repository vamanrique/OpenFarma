"""
fix_auditoria_conc18.py — Decimoctava ronda de auditoría.

Correcciones:
  A) ADALIMUMAB: ids 1960/1961/1962 -> "100 mg/mL" (misma concentracion, diferente volumen de jeringa)
     - ETL confundió "100 mg/mL" (concentración en label) con dosis total
     - Calculó: 100mg / 0.4mL = 250, 100mg / 0.8mL = 125, 100mg / 0.2mL = 500 (error)
     - Todos son Humira AC 100mg/mL (alta concentración, citrate-free)
     - Merge en id=2494 (ADALIMUMAB 100 mg/mL, n=6)
     - Fix cum_normalizado concentracion_mg_ml
  B) ACIDO RETINOICO -> TRETINOINA (sinónimos: ambos = all-trans retinoic acid)
     - id=241 TOPICO "0.05%" -> rename dci_key + merge en id=207 (TRETINOINA 0.05%, n=9)
     - id=863 ACIDO RETINOICO||ERITROMICINA -> ERITROMICINA||TRETINOINA
       + conc "0.03%" -> "4% + 0.025%" (ERITROMICINA=40mg/g=4%, TRETINOINA=0.25mg/g=0.025%)
     - Sync cum_normalizado principios_dci: ACIDO RETINOICO -> TRETINOINA
  C) CLORHEXIDINA||PROPAN-2-OL id=3470: "2%" -> "2% + 70%"
     - PROPAN-2-OL (alcohol isopropílico) 70% v/v no convertible a mg/mL pero sí a %
  D) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'merge']}

    # -- A. ADALIMUMAB: 250/125/500 mg/mL -> 100 mg/mL ----------------------------
    print("\n=== A. ADALIMUMAB ETL error: concentración confundida con dosis ===")
    for gid in [1960, 1961, 1962]:
        n['A'] += fix_conc(cur, gid, "100 mg/mL", f"A_adalimumab_humira_100mgml")
        # Fix concentracion_mg_ml in cum_normalizado
        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
        g = cur.fetchone()
        if g:
            cids = json.loads(g[0] or '[]')
            updated = 0
            for cid in cids:
                exp, consec = cid.split('-')
                cur.execute("""
                    UPDATE cum_normalizado SET concentracion_mg_ml=100.0
                    WHERE expediente_cum=? AND consecutivo_cum=?
                    AND concentracion_mg_ml > 110.0
                """, (exp, consec))
                if cur.rowcount:
                    updated += 1
            if updated:
                print(f"    cum_normalizado: {updated} productos -> 100 mg/mL")
    # Merge all into id=2494 (100 mg/mL Atenfe biosimilar, n=6)
    for gid in [1960, 1961, 1962]:
        n['merge'] += merge_into(con, 2494, gid)

    # -- B. ACIDO RETINOICO -> TRETINOINA (sinónimos INN) --------------------------
    print("\n=== B. ACIDO RETINOICO -> TRETINOINA ===")
    # B1: id=241 single-component group
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=241")
    row = cur.fetchone()
    if row and 'ACIDO RETINOICO' in (row[0] or ''):
        cur.execute("UPDATE grupos_equivalencia SET dci_key='TRETINOINA' WHERE id=241")
        print(f"  [B1] id=241: dci '{row[0]}' -> 'TRETINOINA'")
        n['B'] += 1
        cids = json.loads(row[1] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
            p = cur.fetchone()
            if p and p[0]:
                pdci = json.loads(p[0])
                new_pdci = ['TRETINOINA' if d == 'ACIDO RETINOICO' else d for d in pdci]
                if new_pdci != pdci:
                    cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                                (json.dumps(new_pdci), exp, consec))
                    updated += 1
        print(f"    cum_normalizado: {updated} productos actualizados")

    # B2: id=863 ACIDO RETINOICO||ERITROMICINA -> ERITROMICINA||TRETINOINA
    # Alphabetical: ERITROMICINA (E) < TRETINOINA (T)
    # concentracion_norm: ERITROMICINA=40mg/g=4%, TRETINOINA=0.25mg/g=0.025% -> "4% + 0.025%"
    cur.execute("SELECT dci_key, concentracion_norm, cum_ids FROM grupos_equivalencia WHERE id=863")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='ERITROMICINA||TRETINOINA', concentracion_norm='4% + 0.025%'
            WHERE id=863
        """)
        print(f"  [B2] id=863: dci '{row[0]}'->ERITROMICINA||TRETINOINA, conc '{row[1]}'->'4% + 0.025%'")
        n['B'] += 1
        cids = json.loads(row[2] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
            p = cur.fetchone()
            if p and p[0]:
                pdci = json.loads(p[0])
                new_pdci = ['TRETINOINA' if d == 'ACIDO RETINOICO' else d for d in pdci]
                if new_pdci != pdci:
                    cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                                (json.dumps(new_pdci), exp, consec))
                    updated += 1
        print(f"    cum_normalizado: {updated} productos ACIDO RETINOICO->TRETINOINA")

    # Global sync: any remaining ACIDO RETINOICO in cum_normalizado
    cur.execute("SELECT expediente_cum, consecutivo_cum, principios_dci FROM cum_normalizado WHERE principios_dci LIKE '%ACIDO RETINOICO%'")
    extra = 0
    for exp, consec, pdci_json in cur.fetchall():
        pdci = json.loads(pdci_json)
        new_pdci = ['TRETINOINA' if d == 'ACIDO RETINOICO' else d for d in pdci]
        if new_pdci != pdci:
            cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                        (json.dumps(new_pdci), exp, consec))
            extra += 1
    if extra:
        print(f"  [B] global: {extra} adicionales ACIDO RETINOICO->TRETINOINA")

    # -- C. CLORHEXIDINA||PROPAN-2-OL id=3470: "2%" -> "2% + 70%" ----------------
    print("\n=== C. CLORHEXIDINA||PROPAN-2-OL id=3470 ===")
    n['C'] += fix_conc(cur, 3470, "2% + 70%", "C_clorhexidina_isopropanol_70pct")

    # -- D. Post-fix auto-merge duplicados ----------------------------------------
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

    # -- Fix n_productos -----------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen -------------------------------------------------------------------
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
