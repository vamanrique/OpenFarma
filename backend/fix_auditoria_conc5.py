"""
fix_auditoria_conc5.py — Quinta ronda de auditoría.

Correcciones:
  A) TIPIRACILO||TRIFLURIDINA id=2510: 9.42mg→8.19mg (misread) → merge id=2508
  B) CLORFENIRAMINA||FENILEFRINA||PARACETAMOL id=3786: scrambled → merge id=1572
  C) ACIDO CLAVULANICO||AMOXICILINA id=3802: scrambled → merge id=2616
  D) Electrolyte ORS groups ids 3607,3608,3686: same formula, different ordering → merge
  E) FENILALANINA amino acid groups ids 772,780,1536: same values, different ordering → merge
  F) ITRACONAZOL||SECNIDAZOL id=836: per-pack/3 values → per-capsule (×3)
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
        print(f"  [SKIP merge] {del_id}→{keep_id}: one doesn't exist")
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


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'F', 'merge']}

    # ── A. TIPIRACILO||TRIFLURIDINA id=2510 ─────────────────────────────────
    print("\n=== A. TIPIRACILO||TRIFLURIDINA ===")
    # Product label: "Lonsurf 20mg+8.19mg" but group has 9.42+20
    # 8.19+20 is correct (standard Lonsurf 20mg strength)
    n['A'] += fix_conc(cur, 2510, "8.19 mg + 20 mg", "A_tipiracilo")
    n['merge'] += merge_into(con, 2508, 2510)

    # ── B. CLORFENIRAMINA||FENILEFRINA||PARACETAMOL id=3786 scrambled ────────
    print("\n=== B. CLORFENIRAMINA||FENILEFRINA||PARACETAMOL ===")
    # DCI alpha: CLORF < FENIL < PARA → "C+F+P" order
    # id=3786 "500+10+4" = CLORF=500 (wrong), PARA=4 (wrong) → scrambled
    # Correct: CLORF=4, FENIL=10, PARA=500 = same as id=1572
    n['B'] += fix_conc(cur, 3786, "4 mg + 10 mg + 500 mg", "B_clorf_scrambled")
    n['merge'] += merge_into(con, 1572, 3786)

    # ── C. ACIDO CLAVULANICO||AMOXICILINA id=3802 scrambled ──────────────────
    print("\n=== C. ACIDO CLAVULANICO||AMOXICILINA ===")
    # DCI alpha: ACIDO CLAVULANICO < AMOXICILINA
    # id=3802 "80+11.4" = CLAV=80 (wrong), AMOX=11.4 (wrong) → scrambled
    # Correct: CLAV=11.4, AMOX=80 = same as id=2616
    n['C'] += fix_conc(cur, 3802, "11.4 mg/mL + 80 mg/mL", "C_amoxiclav_scrambled")
    n['merge'] += merge_into(con, 2616, 3802)

    # ── D. Electrolyte ORS groups: merge 3607, 3686 → 3608 ──────────────────
    print("\n=== D. Electrolyte ORS groups ===")
    # id=3607, 3608, 3686 all have same 7 values (Pediasol/Hidraplen ORS)
    # in different ordering. Merge into id=3608 (most products, n=11)
    # then fix to pharmacologically correct ordering:
    # CALCIO=0.294, MAGNESIO=0.117, POTASIO=0.408, SODIO=1.493, DEXTROSA=45.5, Zn-GLUC=0.139, Na-LAC=6.292
    n['D'] += merge_into(con, 3608, 3607)
    n['D'] += merge_into(con, 3608, 3686)
    CORRECT_ORS = "0.294 mg/mL + 0.117 mg/mL + 0.408 mg/mL + 1.493 mg/mL + 45.5 mg/mL + 0.139 mg/mL + 6.292 mg/mL"
    n['D'] += fix_conc(cur, 3608, CORRECT_ORS, "D_ors_correct_order")
    n['merge'] += n['D'] - 1  # recount: 2 merges
    n['D'] = 1  # 1 concentration fix

    # ── E. FENILALANINA amino acid groups: merge 780, 1536 → 772 ─────────────
    print("\n=== E. FENILALANINA amino acid groups ===")
    # Same 10 AA values in different orderings (Ketosteril/Prevlog same formula)
    # Merge all into id=772 (most products, n=5), keep its concentracion_norm
    n['E'] += merge_into(con, 772, 780)
    n['E'] += merge_into(con, 772, 1536)
    n['merge'] += n['E']
    n['E'] = 0  # no concentration fix needed, just merges

    # ── F. ITRACONAZOL||SECNIDAZOL id=836: per-capsule fix ───────────────────
    print("\n=== F. ITRACONAZOL||SECNIDAZOL ===")
    # id=836 "33.33+166.66": 33.33×3=100mg itra, 166.66×3=500mg secnida
    # Albisec = 100mg itraconazol + 500mg secnidazol per capsule (3-cap course)
    # CUM stored total-divided-by-3 → fix to per-capsule values
    # DCI alpha: ITRACONAZOL < SECNIDAZOL → "itra + secni" order
    # Check if "100 mg + 500 mg" group exists:
    cur.execute("""
        SELECT id FROM grupos_equivalencia
        WHERE dci_key='ITRACONAZOL||SECNIDAZOL'
          AND concentracion_norm='100 mg + 500 mg'
    """)
    existing = cur.fetchone()
    if existing:
        n['F'] += fix_conc(cur, 836, "100 mg + 500 mg", "F_itracon_percap")
        n['merge'] += merge_into(con, existing[0], 836)
    else:
        n['F'] += fix_conc(cur, 836, "100 mg + 500 mg", "F_itracon_percap")

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
