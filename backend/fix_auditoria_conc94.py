"""
fix_auditoria_conc94.py — Nonagésimocuarta ronda de auditoría.

  A) Split id=2755 (HIERRO | LIQUIDO_ORAL | 25 mg/mL, 12 productos):
     Grupo mixto: Sulfato Ferroso (ATC B03AA07) + Gluconato Ferroso (ATC B03AA01).
     - SULFATO FERROSO 25mg/mL: expedientes 19963969 (×2), 19963970 (×2), 19995854 (×1),
       19998072 (×1), 20071876 (×1) = 7 productos.
     - GLUCONATO FERROSO 25mg/mL: expediente 20092846 (×5) = 5 productos (Anemikids
       Solucion, misma marca que grupos 2753/2754 pero a mayor concentración).

  B) id=2758 (Ferrokids Gotas, 6 productos, ATC B03AB02):
     'HIERRO' → 'FUMARATO FERROSO'
     ATC B03AB02 = ferrous fumarate (fumarato ferroso). Ferrokids Gotas (Chalver)
     son gotas pediátricas de fumarato ferroso 30 mg/mL. Sin merge: único grupo.

  C) id=2751 (Herrex Gotas, 2 productos, ATC B03AB04):
     'HIERRO' → 'CITRATO FERRICO AMONICO'
     ATC B03AB04 = ferric ammonium citrate (citrato ferrico amonico).
     Herrex Gotas (Farma de Colombia/Chalver) = hierro elemental como citrato ferrico
     amonico, 50 mg/mL. Sin merge: único grupo LIQUIDO_ORAL 50mg/mL.

  D) id=2752 (Herrex Jarabe + Eurofer Jarabe, 7 productos):
     'HIERRO' → 'CITRATO FERRICO AMONICO'
     Herrex Jarabe: ATC B03AB04 (citrato ferrico amonico), confirmado.
     Eurofer Jarabe (Eurodrug): ATC B03AC02 es error de codificación INVIMA — B03AC02
     es hierro sacarosa PARENTERAL; un jarabe oral no puede ser hierro sacarosa. Eurofer
     jarabe es también citrato ferrico amonico oral.
     Sin merge con id=2751: conc 10 mg/mL ≠ 50 mg/mL.
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"

SULFATO_EXPS = {"19963969", "19963970", "19995854", "19998072", "20071876"}
GLUCONATO_EXPS = {"20092846"}


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


def split_hierro_25(con) -> int:
    """Split id=2755 HIERRO 25mg/mL into SULFATO FERROSO and GLUCONATO FERROSO."""
    cur = con.cursor()
    cur.execute("SELECT cum_ids, grupo_via, concentracion_norm FROM grupos_equivalencia WHERE id=2755")
    row = cur.fetchone()
    if not row:
        print("  [SKIP] id=2755 no existe")
        return 0

    all_cids = safe_json(row[0])
    via = row[1]
    conc = row[2]

    sulfato_cids = [c for c in all_cids if c.split('-')[0] in SULFATO_EXPS]
    gluconato_cids = [c for c in all_cids if c.split('-')[0] in GLUCONATO_EXPS]
    other_cids = [c for c in all_cids if c.split('-')[0] not in SULFATO_EXPS and c.split('-')[0] not in GLUCONATO_EXPS]

    print(f"  id=2755 total={len(all_cids)}: sulfato={len(sulfato_cids)}, gluconato={len(gluconato_cids)}, other={len(other_cids)}")
    if other_cids:
        print(f"  [WARN] unclassified: {other_cids}")

    # Update id=2755 to SULFATO FERROSO with sulfato products
    cur.execute("UPDATE grupos_equivalencia SET dci_key='SULFATO FERROSO', cum_ids=?, n_productos=? WHERE id=2755",
                (json.dumps(sulfato_cids), len(sulfato_cids)))
    print(f"  id=2755 -> SULFATO FERROSO | {via} | {conc} | n={len(sulfato_cids)}")

    # Update principios_dci for sulfato products
    up_s = 0
    for cid in sulfato_cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            if safe_json(p[0]) != ["SULFATO FERROSO"]:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(["SULFATO FERROSO"]), exp, consec))
                up_s += 1
    if up_s: print(f"    cum_normalizado SULFATO: {up_s} actualizados")

    # Create new group GLUCONATO FERROSO 25mg/mL
    cur.execute("""
        INSERT INTO grupos_equivalencia (dci_key, grupo_via, concentracion_norm, cum_ids, n_productos, revisado_ia)
        VALUES ('GLUCONATO FERROSO', ?, ?, ?, ?, 1)
    """, (via, conc, json.dumps(gluconato_cids), len(gluconato_cids)))
    new_id = cur.lastrowid
    print(f"  [CREATE] id={new_id}: GLUCONATO FERROSO | {via} | {conc} | n={len(gluconato_cids)}")

    # Update principios_dci for gluconato products
    up_g = 0
    for cid in gluconato_cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            if safe_json(p[0]) != ["GLUCONATO FERROSO"]:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(["GLUCONATO FERROSO"]), exp, consec))
                up_g += 1
    if up_g: print(f"    cum_normalizado GLUCONATO: {up_g} actualizados")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # A. Split id=2755 HIERRO 25mg/mL
    print("\n=== A. Split id=2755 HIERRO 25mg/mL ===")
    n['A'] += split_hierro_25(con)

    # B. id=2758 Ferrokids Gotas: HIERRO → FUMARATO FERROSO
    print("\n=== B. id=2758 Ferrokids Gotas 30mg/mL: HIERRO -> FUMARATO FERROSO ===")
    n['B'] += rename_dci(con, 2758, "FUMARATO FERROSO", {"HIERRO": "FUMARATO FERROSO"})

    # C. id=2751 Herrex Gotas: HIERRO → CITRATO FERRICO AMONICO
    print("\n=== C. id=2751 Herrex Gotas 50mg/mL: HIERRO -> CITRATO FERRICO AMONICO ===")
    n['C'] += rename_dci(con, 2751, "CITRATO FERRICO AMONICO", {"HIERRO": "CITRATO FERRICO AMONICO"})

    # D. id=2752 Herrex+Eurofer Jarabe: HIERRO → CITRATO FERRICO AMONICO
    print("\n=== D. id=2752 Herrex+Eurofer Jarabe 10mg/mL: HIERRO -> CITRATO FERRICO AMONICO ===")
    n['D'] += rename_dci(con, 2752, "CITRATO FERRICO AMONICO", {"HIERRO": "CITRATO FERRICO AMONICO"})

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
