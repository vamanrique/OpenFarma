"""
fix_auditoria_conc93.py — Nonagésimotercera ronda de auditoría.

  A) id=683 (Sulfato Ferroso Tabletas Recubiertas, 35 productos):
     'HIERRO' → 'SULFATO FERROSO'
     ATC B03AA07. Nombre comercial literal: "Sulfato Ferroso Tabletas Recubiertas 300mg".
     Sin merge: único grupo SOLIDO_ORAL 300mg.

  B) id=2753 (Anemidox Suspension, Anemikids Solución, 11 productos):
     'HIERRO' → 'GLUCONATO FERROSO'
     ATC B03AA01 (ferrous gluconate). 6 mg/mL.

  C) id=2754 (Anemidox Gotas Pediatricas, Anemikids Gotas, 8 productos):
     'HIERRO' → 'GLUCONATO FERROSO'
     ATC B03AA01. 6.66 mg/mL. → auto-merge con 2753 (mismo dci+via+conc? NO, conc
     distinta 6 vs 6.66 mg/mL → grupos separados, sin merge).

  D) id=2333 (Cheltin IV, 1 producto):
     'HIERRO' → 'HIERRO SACAROSA'
     ATC B03AC02 (iron sucrose). Cheltin IV 100mg = complejo de hierro sacarosa inyectable.
     → auto-merge con id=2463 (HIERRO SACAROSA|INYECTABLE|100 mg, 1 producto).

  E) id=1045 split: DOXORUBICINA LIPOSOMAL PEGILADA
     Productos confirmados liposomales en id=1045 (DOXORUBICINA|INYECTABLE|2 mg/mL, 18 prod):
       - 19969115 (Doxopeg 2Mg/Ml): 3 CUMs
       - 20037727 (Lipodox - Sun): 2 CUMs
       - 20213556 (Doxorubicina "Liposomal Pegilado"): 1 CUM (el -2)
     Los 12 restantes son doxorubicina convencional → permanecen en id=1045.
     INN: DOXORUBICINA LIPOSOMAL PEGILADA (no hay INN OMS separado, pero INVIMA y
     reguladores colombianos los tratan como entidad distinta al igual que ANFOTERICINA B
     LIPOSOMAL; Caelyx/Doxopeg/Lipodox son pegilados, clasificación diferente de dosis).
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"

LIPOSOMAL_DOXO_EXPEDIENTES = {"19969115", "20037727"}
LIPOSOMAL_DOXO_CIDS = {"20213556-2"}


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
    print(f"  [RENAME] id={gid}: '{old_dci}' -> '{new_dci}'")
    cids = safe_json(row[1])
    updated = 0
    for cid in cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                    (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = safe_json(p[0])
            mapped = [sync_map.get(d, d) for d in pdci]
            new_pdci = list(dict.fromkeys(mapped))
            if new_pdci != pdci:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(new_pdci), exp, consec))
                updated += 1
    if updated:
        print(f"    cum_normalizado: {updated} productos actualizados")
    return 1


def split_doxo_liposomal(con) -> int:
    """Extract liposomal doxorubicin from id=1045 into a new group."""
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos, grupo_via, concentracion_norm FROM grupos_equivalencia WHERE id=1045")
    row = cur.fetchone()
    if not row:
        print("  [SKIP] id=1045 no existe")
        return 0

    all_cids = safe_json(row[0])
    via = row[2]
    conc = row[3]

    lipo_cids = []
    conv_cids = []
    for cid in all_cids:
        exp = cid.split('-')[0]
        if exp in LIPOSOMAL_DOXO_EXPEDIENTES or cid in LIPOSOMAL_DOXO_CIDS:
            lipo_cids.append(cid)
        else:
            conv_cids.append(cid)

    print(f"  id=1045 total={len(all_cids)}: liposomal={len(lipo_cids)}, convencional={len(conv_cids)}")
    if not lipo_cids:
        print("  [SKIP] No liposomal products found")
        return 0

    # Update id=1045 with conventional products only
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=1045",
                (json.dumps(conv_cids), len(conv_cids)))
    print(f"  id=1045 -> DOXORUBICINA convencional: {len(conv_cids)} productos")

    # Create new group for liposomal
    new_dci = "DOXORUBICINA LIPOSOMAL PEGILADA"
    cur.execute("""
        INSERT INTO grupos_equivalencia (dci_key, grupo_via, concentracion_norm, cum_ids, n_productos, revisado_ia)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (new_dci, via, conc, json.dumps(lipo_cids), len(lipo_cids)))
    new_id = cur.lastrowid
    print(f"  [CREATE] id={new_id}: {new_dci} | {via} | {conc} | n={len(lipo_cids)}")

    # Update principios_dci for liposomal products
    updated = 0
    for cid in lipo_cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                    (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = safe_json(p[0])
            new_pdci = [new_dci]
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

    # A. id=683: HIERRO 300mg → SULFATO FERROSO
    print("\n=== A. id=683 Sulfato Ferroso: HIERRO -> SULFATO FERROSO ===")
    n['A'] += rename_dci(con, 683, "SULFATO FERROSO", {"HIERRO": "SULFATO FERROSO"})

    # B. id=2753: HIERRO 6mg/mL → GLUCONATO FERROSO
    print("\n=== B. id=2753 Anemidox/Anemikids 6mg/mL: HIERRO -> GLUCONATO FERROSO ===")
    n['B'] += rename_dci(con, 2753, "GLUCONATO FERROSO", {"HIERRO": "GLUCONATO FERROSO"})

    # C. id=2754: HIERRO 6.66mg/mL → GLUCONATO FERROSO
    print("\n=== C. id=2754 Anemidox/Anemikids Gotas 6.66mg/mL: HIERRO -> GLUCONATO FERROSO ===")
    n['C'] += rename_dci(con, 2754, "GLUCONATO FERROSO", {"HIERRO": "GLUCONATO FERROSO"})

    # D. id=2333: HIERRO 100mg → HIERRO SACAROSA (Cheltin IV)
    print("\n=== D. id=2333 Cheltin IV: HIERRO -> HIERRO SACAROSA ===")
    n['D'] += rename_dci(con, 2333, "HIERRO SACAROSA", {"HIERRO": "HIERRO SACAROSA"})

    # E. Split doxorubicina liposomal pegilada from id=1045
    print("\n=== E. Split id=1045: Doxopeg/Lipodox -> DOXORUBICINA LIPOSOMAL PEGILADA ===")
    n['E'] += split_doxo_liposomal(con)

    # Post-fix auto-merge
    print("\n=== Post-fix auto-merge ===")
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
