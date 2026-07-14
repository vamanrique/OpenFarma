"""
fix_auditoria_conc22.py — Vigesimosegunda ronda de auditoría.

Correcciones:
  A) ZINC UNDECILENATO -> UNDECILENATO DE ZINC (sinónimo DCI):
     - id=2842 "ACIDO UNDECILENICO||ZINC UNDECILENATO" 5%+20% n=3
       -> rename -> merge en id=2831 (mismo dci/via/conc, n=5 -> n=8)
  B) VITAMINA B12 -> CIANOCOBALAMINA (INN estándar):
     - id=1905 prenatal SOLIDO_ORAL: VITAMINA B12 -> CIANOCOBALAMINA en dci_key
       (producto P-Natal; ya tiene COLECALCIFEROL correcto)
     - id=3214 Prenavit SOLIDO_ORAL: VITAMINA B12 -> CIANOCOBALAMINA
                                      + VITAMINA D3 -> COLECALCIFEROL en dci_key
     - sync cum_normalizado para ambos grupos
  C) ALFATOCOFEROL -> TOCOFEROL ALFA (INN) + VITAMINA A -> RETINOL (INN):
     - id=2800 Lifertron E SOLIDO_ORAL SIN_CONCENTRACION
       dci "ALFATOCOFEROL||VITAMINA A" -> "RETINOL||TOCOFEROL ALFA"
       (no merge: conc distinta de id=3668 "50000 UI + 150 UI")
     - sync cum_normalizado: ALFATOCOFEROL->TOCOFEROL ALFA, VITAMINA A->RETINOL
  D) Post-fix auto-merge duplicados
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

    # -- A. ZINC UNDECILENATO -> UNDECILENATO DE ZINC --------------------------------
    print("\n=== A. ZINC UNDECILENATO -> UNDECILENATO DE ZINC ===")
    n['A'] += rename_dci(con, 2842, "ACIDO UNDECILENICO||UNDECILENATO DE ZINC",
                         {"ZINC UNDECILENATO": "UNDECILENATO DE ZINC"})
    # auto-merge will catch 2842 -> 2831 (same dci+via+conc after rename)

    # -- B. VITAMINA B12 -> CIANOCOBALAMINA (INN) ------------------------------------
    print("\n=== B. VITAMINA B12 -> CIANOCOBALAMINA normalizacion ===")
    # id=1905: only VITAMINA B12 needs fix (already has COLECALCIFEROL, DHA, RETINOL)
    # Old: 'ACIDO ASCORBICO||ACIDO FOLICO||CALCIO||COLECALCIFEROL||DHA||HIERRO||NICOTINAMIDA||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL||VITAMINA B12||ZINC'
    # New: 'ACIDO ASCORBICO||ACIDO FOLICO||CALCIO||CIANOCOBALAMINA||COLECALCIFEROL||DHA||HIERRO||NICOTINAMIDA||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL||ZINC'
    n['B'] += rename_dci(con, 1905,
                         "ACIDO ASCORBICO||ACIDO FOLICO||CALCIO||CIANOCOBALAMINA||COLECALCIFEROL||DHA||HIERRO||NICOTINAMIDA||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL||ZINC",
                         {"VITAMINA B12": "CIANOCOBALAMINA"})

    # id=3214: two fixes - VITAMINA B12 + VITAMINA D3
    # Old: 'ACIDO ASCORBICO||ACIDO FOLICO||CALCIO||HIERRO||NICOTINAMIDA||PANTOTENATO DE CALCIO||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL||VITAMINA B12||VITAMINA D3'
    # New: 'ACIDO ASCORBICO||ACIDO FOLICO||CALCIO||CIANOCOBALAMINA||COLECALCIFEROL||HIERRO||NICOTINAMIDA||PANTOTENATO DE CALCIO||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL'
    n['B'] += rename_dci(con, 3214,
                         "ACIDO ASCORBICO||ACIDO FOLICO||CALCIO||CIANOCOBALAMINA||COLECALCIFEROL||HIERRO||NICOTINAMIDA||PANTOTENATO DE CALCIO||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL",
                         {"VITAMINA B12": "CIANOCOBALAMINA", "VITAMINA D3": "COLECALCIFEROL"})

    # -- C. ALFATOCOFEROL -> TOCOFEROL ALFA + VITAMINA A -> RETINOL ------------------
    print("\n=== C. ALFATOCOFEROL->TOCOFEROL ALFA + VITAMINA A->RETINOL ===")
    # id=2800: ALFATOCOFEROL||VITAMINA A -> RETINOL||TOCOFEROL ALFA (alphabetical)
    n['C'] += rename_dci(con, 2800, "RETINOL||TOCOFEROL ALFA",
                         {"ALFATOCOFEROL": "TOCOFEROL ALFA", "VITAMINA A": "RETINOL"})
    # Note: concentracion_norm=SIN_CONCENTRACION differs from id=3668 (50000 UI + 150 UI)
    # so no auto-merge expected

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
