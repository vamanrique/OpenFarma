"""
fix_auditoria_conc31.py — Trigesimoprima ronda de auditoría.

Correcciones — normalización TOCOFEROL (INN) y FLUORURO:
  A) id=661: FLUOR -> FLUORURO (multivitamínico con ginseng, SOLIDO_ORAL):
     - Posición 6 en dci_key: sin cambio de orden, sin reorden conc
  B) id=505: DL-ALFA-TOCOFEROL -> TOCOFEROL (Cernevit INYECTABLE, n=2):
     - DL-ALFA-TOCOFEROL estaba en pos 7; TOCOFEROL pasa a pos 12
     - fix_conc: valor 10.2 mg de pos 7 pasa a pos 12
       "125 + 0.414 + 0.069 + 0.006 + 220UI + 16.15 + 10.2 + 46 + 5.5 + 3500 + 5.67 + 5.8"
       -> "125 + 0.414 + 0.069 + 0.006 + 220UI + 16.15 + 46 + 5.5 + 3500 + 5.67 + 5.8 + 10.2"
  C) TOCOFEROL ALFA -> TOCOFEROL (INN estándar, = vitamina E):
     - id=2800: RETINOL||TOCOFEROL ALFA SOLIDO_ORAL SIN_CONC (n=5)
       -> RETINOL||TOCOFEROL (R<T: mismo orden, sin reorden conc)
     - id=3668: RETINOL||TOCOFEROL ALFA SOLIDO_ORAL 50000+150 UI (n=10)
       -> RETINOL||TOCOFEROL (R<T: mismo orden, sin reorden conc)
     (Ambos quedan con concentraciones distintas: no auto-merge)
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


def fix_conc(cur, gid: int, new_conc: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya conc] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [FIX_CONC] id={gid}: '{row[0][:60]}' -> '{new_conc[:60]}'")
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

    # -- A. id=661: FLUOR -> FLUORURO (posición 6, sin reorden) ----------------------
    print("\n=== A. id=661: FLUOR -> FLUORURO ===")
    n['A'] += rename_dci(con, 661,
                         "ACIDO ASCORBICO||ACIDO FOLICO||CIANOCOBALAMINA||COBRE||COLECALCIFEROL||"
                         "FLUORURO||GINSENG||HIERRO||MAGNESIO||MANGANESO||MOLIBDENO||NICOTINAMIDA||"
                         "PANTOTENATO DE CALCIO||PIRIDOXINA||POTASIO||RETINOL||RIBOFLAVINA||RUTINA||"
                         "TIAMINA||TOCOFEROL||ZINC",
                         {"FLUOR": "FLUORURO"})

    # -- B. id=505: DL-ALFA-TOCOFEROL -> TOCOFEROL + fix conc -----------------------
    print("\n=== B. id=505: DL-ALFA-TOCOFEROL -> TOCOFEROL + fix conc ===")
    # Old: ...|DL-ALFA-TOCOFEROL(pos7=10.2mg)|NICOTINAMIDA(8=46)|PIRIDOXINA(9=5.5)|
    #       RETINOL(10=3500)|RIBOFLAVINA(11=5.67)|TIAMINA(12=5.8)
    # New: ...|NICOTINAMIDA(7=46)|PIRIDOXINA(8=5.5)|RETINOL(9=3500)|
    #       RIBOFLAVINA(10=5.67)|TIAMINA(11=5.8)|TOCOFEROL(12=10.2)
    n['B'] += rename_dci(con, 505,
                         "ACIDO ASCORBICO||ACIDO FOLICO||BIOTINA||CIANOCOBALAMINA||COLECALCIFEROL||"
                         "DEXPANTENOL||NICOTINAMIDA||PIRIDOXINA||RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL",
                         {"DL-ALFA-TOCOFEROL": "TOCOFEROL"})
    fix_conc(cur, 505,
             "125 mg + 0.414 mg + 0.069 mg + 0.006 mg + 220 UI + 16.15 mg + "
             "46 mg + 5.5 mg + 3500 mg + 5.67 mg + 5.8 mg + 10.2 mg")

    # -- C. TOCOFEROL ALFA -> TOCOFEROL (ids 2800, 3668) ----------------------------
    print("\n=== C. TOCOFEROL ALFA -> TOCOFEROL ===")
    toc_map = {"TOCOFEROL ALFA": "TOCOFEROL"}

    # id=2800: SIN_CONC (R<T mismo orden)
    n['C'] += rename_dci(con, 2800, "RETINOL||TOCOFEROL", toc_map)

    # id=3668: 50000+150 UI (R<T mismo orden, sin reorden conc)
    n['C'] += rename_dci(con, 3668, "RETINOL||TOCOFEROL", toc_map)

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
