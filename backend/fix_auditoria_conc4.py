"""
fix_auditoria_conc4.py — Cuarta ronda de auditoría.

Correcciones:
  A) DCI key: OLMESARTAN variants → OLMESARTAN MEDOXOMILO (español INN oficial)
  B) Concentraciones salt-form: PERINDOPRIL 3.4→5mg, 6.8→10mg; amlodipino besylate 13.869→10mg
  C) Concentraciones scrambled: AMLODIPINO||INDAPAMIDA||PERINDOPRIL (id=1811, 1812)
  D) Salt forms combos: DROSPIRENONA||ESTRADIOL 1.033→1mg, ACIDO IBANDRONICO 160.34→150mg+224UI→22400UI
  E) METFORMINA||SITAGLIPTINA: 59.69/56.69 (phosphate) → 50mg, merge
  F) BETAMETASONA||CLOTRIMAZOL||GENTAMICINA id=3841 scrambled → merge into id=2677
  G) AZELASTINA||FLUTICASONA: unificar en grupo NASAL 137mcg+50mcg/dosis (id=2100)
  H) Merge duplicados post-DCI
"""
import sqlite3, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        return 0
    merged = list(dict.fromkeys(
        json.loads(keep[0] or '[]') + json.loads(rem[0] or '[]')
    ))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}→{keep_id}: total={len(merged)}")
    return 1


def fix_conc(cur, gid: int, new_conc: str, tag: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya] id={gid} ya tiene '{new_conc}'")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{row[0]}' → '{new_conc}'")
    return 1


def rebuild_dci_key(old_key: str, subs: list) -> str:
    parts = [p.strip() for p in old_key.split('||')]
    new_parts = []
    changed = False
    for p in parts:
        new_p = p
        for old, new in subs:
            if new_p == old:
                new_p = new
                changed = True
        new_parts.append(new_p)
    if not changed:
        return old_key
    return '||'.join(sorted(new_parts))


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A_grupos', 'A_cum', 'B', 'C', 'D', 'E', 'F', 'G', 'merge']}

    # ── A. DCI key: OLMESARTAN variant normalization ─────────────────────────
    print("\n=== A. DCI key OLMESARTAN normalization ===")
    OLMESARTAN_SUBS = [
        ("OLMESARTAN MEDOXOMIL", "OLMESARTAN MEDOXOMILO"),  # English → Spanish INN
        ("OLMESARTAN", "OLMESARTAN MEDOXOMILO"),            # bare → full Spanish INN
        # Note: order matters — MEDOXOMIL must come before bare OLMESARTAN
        # But since we compare component == old, they're mutually exclusive
    ]
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia WHERE dci_key LIKE '%OLMESARTAN%'")
    rows = cur.fetchall()
    for gid, old_key in rows:
        new_key = rebuild_dci_key(old_key, OLMESARTAN_SUBS)
        if new_key != old_key:
            cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_key, gid))
            print(f"  id={gid}: '{old_key}' → '{new_key}'")
            n['A_grupos'] += 1

    # A2. Update cum_normalizado principios_dci
    print("\n=== A2. cum_normalizado principios_dci OLMESARTAN ===")
    cur.execute("""
        SELECT expediente_cum, consecutivo_cum, principios_dci
        FROM cum_normalizado
        WHERE principios_dci LIKE '%OLMESARTAN%'
    """)
    updated = 0
    for exp, consec, pdci_json in cur.fetchall():
        pdci = json.loads(pdci_json) if pdci_json else []
        new_pdci = []
        changed = False
        for p in pdci:
            new_p = p
            if new_p == "OLMESARTAN MEDOXOMIL":
                new_p = "OLMESARTAN MEDOXOMILO"
                changed = True
            elif new_p == "OLMESARTAN":
                new_p = "OLMESARTAN MEDOXOMILO"
                changed = True
            new_pdci.append(new_p)
        if changed:
            cur.execute(
                "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                (json.dumps(new_pdci), exp, consec)
            )
            updated += 1
    print(f"  {updated} registros cum_normalizado actualizados")
    n['A_cum'] = updated

    # ── B. Concentraciones salt-form ─────────────────────────────────────────
    print("\n=== B. Concentraciones salt-form ===")
    # PERINDOPRIL: free acid → arginine salt convention
    n['B'] += fix_conc(cur, 1227, "5 mg", "B_perindopril_3.4→5")
    n['B'] += fix_conc(cur, 1226, "10 mg", "B_perindopril_6.8→10")
    # AMLODIPINO besylate 13.869mg → 10mg free base
    n['B'] += fix_conc(cur, 2475, "10 mg + 25 mg + 40 mg", "B_amlodipino_besylate")
    # DROSPIRENONA||ESTRADIOL: estradiol hemihydrate 1.033mg → 1mg base
    n['B'] += fix_conc(cur, 879, "2 mg + 1 mg", "B_estradiol_hemihydrate")
    # ACIDO IBANDRONICO||COLECALCIFEROL: salt form 160.34mg → 150mg, D3 224UI → 22400UI
    n['B'] += fix_conc(cur, 2466, "150 mg + 22400 UI", "B_ibandronico_D3")

    # ── C. Concentraciones scrambled AMLODIPINO||INDAPAMIDA||PERINDOPRIL ────
    print("\n=== C. AMLODIPINO||INDAPAMIDA||PERINDOPRIL scrambled ===")
    # id=1811 product: Coveratrix 5/1.25/10 → AMLODIPINO=5, INDAPAMIDA=1.25, PERINDOPRIL=10
    # Current (wrong): "10 mg + 1.25 mg + 3.395 mg" (AMLODIPINO=10, PERINDOPRIL=3.395 free acid)
    n['C'] += fix_conc(cur, 1811, "5 mg + 1.25 mg + 10 mg", "C_coveratrix_5_1.25_10")
    # id=1812 product: Coveratrix 10/2.5/5 → AMLODIPINO=10, INDAPAMIDA=2.5, PERINDOPRIL=5
    # Current (wrong): "5 mg + 2.5 mg + 10 mg" (AMLODIPINO=5, PERINDOPRIL=10)
    n['C'] += fix_conc(cur, 1812, "10 mg + 2.5 mg + 5 mg", "C_coveratrix_10_2.5_5")

    # ── D. METFORMINA||SITAGLIPTINA phosphate salt → free base ───────────────
    print("\n=== D. METFORMINA||SITAGLIPTINA phosphate salt ===")
    # id=2389: 850mg+59.69mg (sitagliptina phosphate) → 850+50mg → merge into id=59
    n['D'] += fix_conc(cur, 2389, "850 mg + 50 mg", "D_sitagliptin_phosphate_850")
    n['merge'] += merge_into(con, 59, 2389)
    # id=2390: 1000mg+56.69mg → 1000+50mg → merge into id=56
    n['D'] += fix_conc(cur, 2390, "1000 mg + 50 mg", "D_sitagliptin_phosphate_1000")
    n['merge'] += merge_into(con, 56, 2390)

    # ── E. BETAMETASONA||CLOTRIMAZOL||GENTAMICINA scrambled ──────────────────
    print("\n=== E. BETAMETASONA||CLOTRIMAZOL||GENTAMICINA scrambled ===")
    # id=3841 "0.1%+0.05%+1%" is scrambled: product Corasan = BETA 0.05%, CLOT 1%, GENTA 0.1%
    # Same as id=2677 → rename and merge
    n['E'] += fix_conc(cur, 3841, "0.05% + 1% + 0.1%", "E_BCG_scrambled")
    n['merge'] += merge_into(con, 2677, 3841)

    # ── F. AZELASTINA||FLUTICASONA: unificar en NASAL mcg/dosis ──────────────
    print("\n=== F. AZELASTINA||FLUTICASONA cleanup ===")
    # id=3592 NASAL "1 mg + 0.365 mg" = mg/mL expressed as mg per actuation → 137+50 mcg/dosis
    n['F'] += fix_conc(cur, 3592, "137 mcg/dosis + 50 mcg/dosis", "F_azel_flut_3592")
    n['merge'] += merge_into(con, 2100, 3592)
    # id=2341 INHALADO "1.365 mg/mL" — misclassified nasal spray
    # Change grupo_via to NASAL then fix concentracion and merge
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=2341")
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE grupos_equivalencia SET grupo_via='NASAL', concentracion_norm='137 mcg/dosis + 50 mcg/dosis' WHERE id=2341")
        print(f"  [F_azel_flut_2341] id=2341: via→NASAL, conc '{row[0]}' → '137 mcg/dosis + 50 mcg/dosis'")
        n['F'] += 1
        n['merge'] += merge_into(con, 2100, 2341)

    # ── G. Merge duplicados post-DCI OLMESARTAN ───────────────────────────────
    print("\n=== G. Merge duplicados post-DCI ===")
    cur.execute("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as cnt,
               GROUP_CONCAT(id || ':' || n_productos ORDER BY n_productos DESC)
        FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING cnt > 1
    """)
    for dci, via, conc, cnt, ids_str in cur.fetchall():
        pairs = [(int(x.split(':')[0]), int(x.split(':')[1])) for x in ids_str.split(',')]
        keep_id = pairs[0][0]  # largest n first
        for del_id, _ in pairs[1:]:
            n['merge'] += merge_into(con, keep_id, del_id)

    # ── Fix n_productos ───────────────────────────────────────────────────────
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # ── Resumen ───────────────────────────────────────────────────────────────
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
