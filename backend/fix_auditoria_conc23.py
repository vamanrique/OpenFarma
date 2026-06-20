"""
fix_auditoria_conc23.py — Vigesimotercera ronda de auditoría.

Correcciones:
  A) NIACINAMIDA -> NICOTINAMIDA (INN estándar para niacinamide/nicotinamide):
     - id=293  "NIACINAMIDA||PIRIDOXINA||RIBOFLAVINA||TIAMINA" -> merge en id=208 (misma conc)
     - id=860  "ACIDO ASCORBICO||CIANOCOBALAMINA||NIACINAMIDA||PANTOTENATO DE CALCIO||..."
               + VITAMINA A -> RETINOL
     - id=2009 "...||NIACINAMIDA||PANTOTENATO||..." (Nutragesta prenatal)
               + PANTOTENATO -> PANTOTENATO DE CALCIO
     - id=3133 multivitamínico INYECTABLE SIN_CONCENTRACION
     - id=3213 "DEXTROSA||NIACINAMIDA||PIRIDOXINA||RIBOFLAVINA" INYECTABLE (Venovit)
  B) VITAMINA A -> RETINOL + VITAMINA D -> COLECALCIFEROL en id=3136 (Pediavit Zinc LIQUIDO_ORAL):
     - cod liver oil: Vitamina A=retinol, Vitamina D=colecalciferol (D3)
     - dci_key: ...||VITAMINA A||VITAMINA D||... -> ...||COLECALCIFEROL||...||RETINOL||...
  C) BUTILBROMURO DE HIOSCINA||PARACETAMOL concentración incompleta:
     - id=3788 LIQUIDO_ORAL "100 mg/mL" -> "2 mg/mL + 100 mg/mL"
       (Buscapina Compositum NF gotas: hioscina 2mg/mL + paracetamol 100mg/mL)
       -> merge en id=3255 (misma conc, n=2 -> n=3)
  D) Post-fix auto-merge duplicados
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
    print(f"  [RENAME] id={gid}: '{old_dci[:60]}' -> '{new_dci[:60]}'")
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

    # -- A. NIACINAMIDA -> NICOTINAMIDA (INN) ----------------------------------------
    print("\n=== A. NIACINAMIDA -> NICOTINAMIDA normalizacion ===")
    niac_map = {"NIACINAMIDA": "NICOTINAMIDA"}

    # id=293: simple B-complex; after rename auto-merges into id=208 (same dci+via+conc)
    n['A'] += rename_dci(con, 293,
                         "NICOTINAMIDA||PIRIDOXINA||RIBOFLAVINA||TIAMINA",
                         niac_map)

    # id=860: also rename VITAMINA A -> RETINOL
    n['A'] += rename_dci(con, 860,
                         "ACIDO ASCORBICO||CIANOCOBALAMINA||NICOTINAMIDA||PANTOTENATO DE CALCIO||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||ZINC",
                         {"NIACINAMIDA": "NICOTINAMIDA", "VITAMINA A": "RETINOL"})

    # id=2009: also rename PANTOTENATO -> PANTOTENATO DE CALCIO (free acid abbreviated in ETL)
    n['A'] += rename_dci(con, 2009,
                         "ACIDO ASCORBICO||ACIDO FOLICO||CALCIO||CIANOCOBALAMINA||COBALTO||COBRE||COLECALCIFEROL||FENILALANINA||FLUORURO||HIERRO||MAGNESIO||MANGANESO||MOLIBDENO||NICOTINAMIDA||PANTOTENATO DE CALCIO||PIRIDOXINA||POTASIO||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL||ZINC",
                         {"NIACINAMIDA": "NICOTINAMIDA", "PANTOTENATO": "PANTOTENATO DE CALCIO"})

    # id=3133: multivitamínico INYECTABLE
    n['A'] += rename_dci(con, 3133,
                         "ACIDO ASCORBICO||ACIDO FOLICO||BIOTINA||CIANOCOBALAMINA||COLECALCIFEROL||DEXPANTENOL||FITOMENADIONA||NICOTINAMIDA||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL",
                         niac_map)

    # id=3213: Venovit INYECTABLE
    n['A'] += rename_dci(con, 3213,
                         "DEXTROSA||NICOTINAMIDA||PIRIDOXINA||RIBOFLAVINA",
                         niac_map)

    # -- B. VITAMINA A -> RETINOL + VITAMINA D -> COLECALCIFEROL en id=3136 -----------
    print("\n=== B. VITAMINA A->RETINOL + VITAMINA D->COLECALCIFEROL (id=3136) ===")
    n['B'] += rename_dci(con, 3136,
                         "ACIDO ASCORBICO||CIANOCOBALAMINA||COLECALCIFEROL||DEXPANTENOL||HIERRO||NICOTINAMIDA||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||ZINC",
                         {"VITAMINA A": "RETINOL", "VITAMINA D": "COLECALCIFEROL"})

    # -- C. BUTILBROMURO DE HIOSCINA||PARACETAMOL: conc incompleta -------------------
    print("\n=== C. BUTILBROMURO HIOSCINA||PARACETAMOL: 100mg/mL -> 2mg/mL+100mg/mL ===")
    n['C'] += fix_conc(cur, 3788, "2 mg/mL + 100 mg/mL", "C_buscapina_compositum_nf")
    # auto-merge: id=3788 (n=1) -> id=3255 (2mg/mL+100mg/mL, n=2)

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
