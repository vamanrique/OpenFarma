"""
fix_auditoria_conc2.py — Segunda ronda de auditoría de concentraciones.

Correcciones:
  A) VAGINAL mg/g → % (w/w: 1mg/g = 0.1%)
  B) VAGINAL mg/mL → % (w/v: 1mg/mL = 0.1%)  → fusión con grupos % existentes
  C) TOPICO mg/g → % para los componentes no-UI
  D) NASAL % → mg/mL (soluciones) | mg/dose → mcg/dosis (sprays)
  E) OTICO % → mg/mL
  F) LIQUIDO_ORAL % restantes → mg/mL
  G) Correcciones puntuales (dimeticona combo, azelastina)
"""
import sqlite3, sys, re, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


def fmt(val: float) -> str:
    """Format float without trailing zeros."""
    return f"{val:g}"


def mgpg_to_pct(conc: str) -> str | None:
    """Convert each 'X mg/g' component to 'Y%'. UI/g parts kept as-is."""
    parts = [p.strip() for p in conc.split('+')]
    out = []
    changed = False
    for p in parts:
        m = re.match(r'^([\d.]+)\s*mg/g$', p, re.I)
        if m:
            val = float(m.group(1)) / 10  # 1mg/g = 0.1%
            out.append(f"{fmt(val)}%")
            changed = True
        else:
            out.append(p)
    return ' + '.join(out) if changed else None


def mgml_to_pct(conc: str) -> str | None:
    """Convert each 'X mg/mL' component to 'Y%' for creams/gels."""
    parts = [p.strip() for p in conc.split('+')]
    out = []
    changed = False
    for p in parts:
        m = re.match(r'^([\d.]+)\s*mg/mL$', p, re.I)
        if m:
            val = float(m.group(1)) / 10  # 1mg/mL ≈ 0.1% for topical
            out.append(f"{fmt(val)}%")
            changed = True
        else:
            out.append(p)
    return ' + '.join(out) if changed else None


def pct_to_mgml(conc: str) -> str:
    """Convert X% to X*10 mg/mL. Handles + separated combos."""
    parts = [p.strip() for p in conc.split('+')]
    out = []
    for p in parts:
        m = re.match(r'^([\d.]+)\s*%$', p)
        if m:
            val = float(m.group(1)) * 10
            out.append(f"{fmt(val)} mg/mL")
        else:
            out.append(p)
    return ' + '.join(out)


def mg_to_mcg_dosis(conc: str) -> str:
    """Convert 'X mg' or 'X mg + Y mg' per-nasal-spray-dose to mcg/dosis."""
    parts = [p.strip() for p in conc.split('+')]
    out = []
    for p in parts:
        m = re.match(r'^([\d.]+)\s*mg$', p)
        if m:
            mcg = float(m.group(1)) * 1000
            out.append(f"{fmt(mcg)} mcg/dosis")
        else:
            out.append(p)
    return ' + '.join(out)


def merge_into(con, keep_id: int, delete_id: int):
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (delete_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP] id={keep_id} o {delete_id} no existe")
        return 0
    merged = list(dict.fromkeys(
        json.loads(keep[0] or '[]') + json.loads(rem[0] or '[]')
    ))
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
        (json.dumps(merged), len(merged), keep_id)
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (delete_id,))
    print(f"  [MERGE] id={delete_id}→{keep_id}: {keep[1]}+{rem[1]}={len(merged)} prods")
    return 1


def apply(cur, gid, new_conc, old_conc, tag):
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{old_conc}' → '{new_conc}'")


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A','B','C','D','E','F','G','merge']}

    # ── A. VAGINAL mg/g → % ──────────────────────────────────────────────────
    print("\n=== A. VAGINAL mg/g → % ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE grupo_via='VAGINAL' AND concentracion_norm LIKE '%mg/g%'")
    for gid, dci, conc in cur.fetchall():
        new = mgpg_to_pct(conc)
        if new:
            apply(cur, gid, new, conc, 'A')
            n['A'] += 1

    # ── B. VAGINAL mg/mL → % ─────────────────────────────────────────────────
    print("\n=== B. VAGINAL mg/mL → % ===")
    VAGINAL_MGML = {
        2714: (1,  2716),   # CLOTRIMAZOL 10mg/mL → 1% → merge into 2716
        2715: (2,  2717),   # CLOTRIMAZOL 20mg/mL → 2% → merge into 2717
        2798: (5,  None),   # ACICLOVIR 50mg/mL → 5%
        3175: (None, None), # CLORURO DE BENZALCONIO 0.5mg/mL → 0.05%
        3410: (None, None), # ACIDO ACETICO 0.77mg/mL → 0.077%
    }
    for gid, (_, merge_target) in VAGINAL_MGML.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if not row:
            continue
        new = mgml_to_pct(row[0])
        if new:
            apply(cur, gid, new, row[0], 'B')
            n['B'] += 1
            if merge_target:
                n['merge'] += merge_into(con, merge_target, gid)

    # ── C. TOPICO mg/g → % ───────────────────────────────────────────────────
    print("\n=== C. TOPICO mg/g → % ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE grupo_via='TOPICO' AND concentracion_norm LIKE '%mg/g%'")
    for gid, dci, conc in cur.fetchall():
        new = mgpg_to_pct(conc)
        if new:
            apply(cur, gid, new, conc, 'C')
            n['C'] += 1

    # ── D. NASAL ─────────────────────────────────────────────────────────────
    print("\n=== D. NASAL ===")
    # D1: CROMOGLICATO 2% → 20 mg/mL
    # D2: OXIMETAZOLINA 0.025% → 0.25mg/mL → merge into id=2721
    NASAL_PCT = {
        3105: (None, None),  # CROMOGLICATO 2% → 20mg/mL
        2720: (None, 2721),  # OXIMETAZOLINA 0.025% → 0.25mg/mL → merge
    }
    for gid, (_, merge_target) in NASAL_PCT.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if not row:
            continue
        new = pct_to_mgml(row[0])
        if new != row[0]:
            apply(cur, gid, new, row[0], 'D_pct→mgml')
            n['D'] += 1
            if merge_target:
                n['merge'] += merge_into(con, merge_target, gid)

    # D3: NASAL mg/dose (metered sprays) → mcg/dosis
    # Only the clearly per-actuation ones (exclude azelastina id=3592 pending verification)
    NASAL_MG_DOSE = {
        11:   None,  # BECLOMETASONA 0.1mg → 100mcg/dosis
        1142: None,  # FLUTICASONA 0.0275mg → 27.5mcg/dosis
        1605: None,  # MOMETASONA 0.1mg → 100mcg/dosis
        1800: None,  # DESMOPRESINA 0.01mg → 10mcg/dosis
        2100: None,  # AZELASTINA||FLUTICASONA 0.137+0.05mg → 137+50mcg/dosis
        2556: None,  # MOMETASONA||OLOPATADINA 0.025+0.6mg → 25+600mcg/dosis
    }
    for gid, _ in NASAL_MG_DOSE.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if not row:
            continue
        new = mg_to_mcg_dosis(row[0])
        if new != row[0]:
            apply(cur, gid, new, row[0], 'D_mg→mcg')
            n['D'] += 1

    # ── E. OTICO % → mg/mL ───────────────────────────────────────────────────
    print("\n=== E. OTICO % → mg/mL ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE grupo_via='OTICO' AND concentracion_norm != 'SIN_CONCENTRACION'")
    for gid, dci, conc in cur.fetchall():
        if conc and '%' in conc and 'mg/mL' not in conc and 'UI' not in conc:
            new = pct_to_mgml(conc)
            if new != conc:
                apply(cur, gid, new, conc, 'E')
                n['E'] += 1

    # ── F. LIQUIDO_ORAL % restantes → mg/mL ──────────────────────────────────
    print("\n=== F. LIQUIDO_ORAL % → mg/mL ===")
    LIQUIDO_PCT = {
        2862: "1.5 mg/mL",   # BENCIDAMINA 0.15%
        2864: "3 mg/mL",     # BENCIDAMINA 0.3%
        3064: "50 mg/mL",    # CARBOCISTEINA 5%
        3065: "20 mg/mL",    # CARBOCISTEINA 2%
    }
    for gid, new_conc in LIQUIDO_PCT.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != new_conc:
            apply(cur, gid, new_conc, row[0], 'F')
            n['F'] += 1

    # ── G. Puntuales ─────────────────────────────────────────────────────────
    print("\n=== G. Puntuales ===")
    PUNTUALES = {
        # DIMETICONA||HIDROXIDO AL||MG: 4% es solo de un componente → incompleto
        3635: "SIN_CONCENTRACION",
    }
    for gid, new_conc in PUNTUALES.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != new_conc:
            apply(cur, gid, new_conc, row[0], 'G')
            n['G'] += 1

    # ── Post-merge: fix duplicates generated ─────────────────────────────────
    print("\n=== Post-merge: nuevos duplicados ===")
    cur.execute("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as cnt, GROUP_CONCAT(id ORDER BY id)
        FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING cnt > 1
    """)
    for dci, via, conc, cnt, ids_str in cur.fetchall():
        ids = list(map(int, ids_str.split(',')))
        keep = ids[0]
        for del_id in ids[1:]:
            n['merge'] += merge_into(con, keep, del_id)

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
    print(f"  TOTAL: {sum(n.values())}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_norm='SIN_CONCENTRACION'")
    sin = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia GROUP BY dci_key,grupo_via,concentracion_norm HAVING COUNT(*)>1")
    dups = len(cur.fetchall())
    print(f"\nDB: {total} grupos | {sin} SIN_CONCENTRACION ({100*sin/total:.1f}%) | {dups} duplicados")
    con.close()


if __name__ == "__main__":
    main()
