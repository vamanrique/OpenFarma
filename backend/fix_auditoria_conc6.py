"""
fix_auditoria_conc6.py — Sexta ronda de auditoría.

Correcciones:
  A) OXITOCINA id=1043: "10 mg/mL" → "10 UI/mL" (INYECTABLE en UI) → merge id=2813
  B) ADRENALINA→EPINEFRINA: DCI key + cum_normalizado sync (7 productos)
     - id=1495 ADRENALINA → EPINEFRINA → merge id=365
     - id=1260 ADRENALINA||ARTICAINA → ARTICAINA||EPINEFRINA + fix conc → merge id=1148
  C) ARTICAINA||EPINEFRINA id=1148: "72mg+0.018mg" per-cartridge → "40 mg/mL + 0.01 mg/mL" per-mL
  D) EPINEFRINA||LIDOCAINA id=2847: "1%" (incompleto) → "0.005 mg/mL + 10 mg/mL"
  E) DEXAMETASONA||NEOMICINA||POLIMIXINA B id=3892: "1.3 mg/mL" → full → merge id=2647
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP merge] {del_id}→{keep_id}: missing")
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
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{row[0]}' → '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # ── A. OXITOCINA id=1043: mg/mL → UI/mL ─────────────────────────────────
    print("\n=== A. OXITOCINA ===")
    n['A'] += fix_conc(cur, 1043, "10 UI/mL", "A_oxitocina")
    n['merge'] += merge_into(con, 2813, 1043)

    # ── B. ADRENALINA → EPINEFRINA ────────────────────────────────────────────
    print("\n=== B. ADRENALINA → EPINEFRINA ===")
    # B1: ADRENALINA mono
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia WHERE id=1495")
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE grupos_equivalencia SET dci_key='EPINEFRINA' WHERE id=1495")
        print(f"  [B1] id=1495: dci '{row[1]}' → 'EPINEFRINA'")
        n['B'] += 1
        n['merge'] += merge_into(con, 365, 1495)

    # B2: ADRENALINA||ARTICAINA → ARTICAINA||EPINEFRINA + fix conc ordering
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=1260")
    row = cur.fetchone()
    if row:
        # Change dci_key and conc: ADRENALINA=0.018, ARTICAINA=72 → ARTICAINA=72, EPINEFRINA=0.018
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='ARTICAINA||EPINEFRINA', concentracion_norm='72 mg + 0.018 mg'
            WHERE id=1260
        """)
        print(f"  [B2] id=1260: dci '{row[1]}' → 'ARTICAINA||EPINEFRINA', conc '{row[2]}' → '72 mg + 0.018 mg'")
        n['B'] += 1
        # Will merge into 1148 after C (once 1148 is fixed to same format OR just merge now)
        # Both id=1260 and id=1148 now have same dci+via+conc → post-merge handles it

    # B3: cum_normalizado ADRENALINA → EPINEFRINA
    cur.execute("SELECT expediente_cum, consecutivo_cum, principios_dci FROM cum_normalizado WHERE principios_dci LIKE '%ADRENALINA%'")
    updated = 0
    for exp, consec, pdci_json in cur.fetchall():
        pdci = json.loads(pdci_json) if pdci_json else []
        new_pdci = [("EPINEFRINA" if p == "ADRENALINA" else p) for p in pdci]
        if new_pdci != pdci:
            cur.execute(
                "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                (json.dumps(new_pdci), exp, consec)
            )
            updated += 1
    print(f"  [B3] cum_normalizado: {updated} registros actualizados")

    # ── C. ARTICAINA||EPINEFRINA id=1148: per-cartridge → per-mL ──────────────
    print("\n=== C. ARTICAINA||EPINEFRINA ===")
    # 1.8mL cartridge: 72mg/1.8=40mg/mL articaine, 0.018mg/1.8=0.01mg/mL epinephrine
    n['C'] += fix_conc(cur, 1148, "40 mg/mL + 0.01 mg/mL", "C_articaina_perml")

    # ── D. EPINEFRINA||LIDOCAINA id=2847: "1%" → full per-mL ────────────────
    print("\n=== D. EPINEFRINA||LIDOCAINA id=2847 ===")
    # Roxicaina 1% + 1:200,000 epi = lidocaine 10mg/mL + epi 0.005mg/mL
    # DCI alpha: EPINEFRINA < LIDOCAINA → "0.005 + 10"
    n['D'] += fix_conc(cur, 2847, "0.005 mg/mL + 10 mg/mL", "D_lidocaina_1pct")

    # ── E. DEXAMETASONA||NEOMICINA||POLIMIXINA B id=3892 ────────────────────
    print("\n=== E. DEXAMETASONA||NEOMICINA||POLIMIXINA B id=3892 ===")
    # "1.3 mg/mL" incomplete → full "1.3 mg/mL + 3.5 mg/mL + 6600 UI/mL" → merge id=2647
    n['E'] += fix_conc(cur, 3892, "1.3 mg/mL + 3.5 mg/mL + 6600 UI/mL", "E_dexa_neo_poli")
    n['merge'] += merge_into(con, 2647, 3892)

    # ── Merge duplicados generados ────────────────────────────────────────────
    print("\n=== Post-merge duplicates ===")
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
