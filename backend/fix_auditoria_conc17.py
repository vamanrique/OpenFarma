"""
fix_auditoria_conc17.py — Decimoséptima ronda de auditoría.

Correcciones:
  A) CALCIO||COLECALCIFEROL id=1172: "315 mg" -> "315 mg + 200 UI"
     - ETL nota: "colecalciferol en UI (200 UI)" — Citragel = calcio 315mg + colecalciferol 200 UI
     - Merge en id=615 (CALCIO||COLECALCIFEROL "315 mg + 200 UI", n=6)
  B) LANREOTIDA id=789/788: total mg -> concentración real 300 mg/mL
     - Somatuline Autogel 60mg/0.2mL = 300mg/mL; 90mg/0.3mL = 300mg/mL
     - ETL dejó "60 mg" y "90 mg" (total) por no encontrar volumen explícito
     - Merge en id=2422 (LANREOTIDA 300 mg/mL, n=4 = Acrogal 60/90mg)
  C) SOMATROPINA id=550: "5.3 mg/mL" -> "5.3 mg"
     - Genotropin 5.3mg polvo para inyección: es total mg por vial, no concentración
     - Merge en id=559 (SOMATROPINA "5.3 mg", n=7)
  D) GUAYACOLATO DE GLICERILO -> GUAIACOLATO DE GLICERILO (typo/variante ortográfica)
     - id=3169 GUAYACOLATO: rename dci_key + merge en id=3021 (GUAIACOLATO 20 mg/mL, n=4)
     - id=3279 GUAYACOLATO||N-ACETILCISTEINA: rename dci_key (conc ya corregida en ronda 15)
     - Sync cum_normalizado principios_dci: GUAYACOLATO -> GUAIACOLATO
  E) BROMHEXINA||GUAIFENSINA id=3522: DCI typo GUAIFENSINA->GUAIFENESINA + conc completa
     - Curatos Medicbrand: BROMHEXINA=0.08mg/mL + GUAIFENSINA=2.0mg/mL (de 100mL formula)
     - "0.8 mg/mL" (solo BROMHEXINA, 10x err) -> "0.08 mg/mL + 2 mg/mL"
     - Sync cum_normalizado principios_dci: GUAIFENSINA -> GUAIFENESINA
  F) Post-fix auto-merge duplicados
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


def sync_dci_in_cum(cur, cum_ids, old_dci: str, new_dci: str) -> int:
    updated = 0
    for cid in cum_ids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = json.loads(p[0])
            new_pdci = [new_dci if d == old_dci else d for d in pdci]
            if new_pdci != pdci:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(new_pdci), exp, consec))
                updated += 1
    return updated


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. CALCIO||COLECALCIFEROL id=1172 ----------------------------------------
    print("\n=== A. CALCIO||COLECALCIFEROL id=1172 ===")
    n['A'] += fix_conc(cur, 1172, "315 mg + 200 UI", "A_calcio_colecalciferol_200ui")
    n['merge'] += merge_into(con, 615, 1172)

    # -- B. LANREOTIDA: total mg -> 300 mg/mL ------------------------------------
    print("\n=== B. LANREOTIDA 60/90mg -> 300 mg/mL ===")
    n['B'] += fix_conc(cur, 789, "300 mg/mL", "B_lanreotida_60mg_0.2ml")
    n['B'] += fix_conc(cur, 788, "300 mg/mL", "B_lanreotida_90mg_0.3ml")
    # auto-merge catches these into id=2422

    # -- C. SOMATROPINA id=550: 5.3 mg/mL -> 5.3 mg (polvo, no solución) ---------
    print("\n=== C. SOMATROPINA id=550 ===")
    n['C'] += fix_conc(cur, 550, "5.3 mg", "C_somatropina_polvo_vs_sol")
    # auto-merge catches this into id=559

    # -- D. GUAYACOLATO -> GUAIACOLATO (typo/variante) ----------------------------
    print("\n=== D. GUAYACOLATO -> GUAIACOLATO ===")
    for gid, old_dci, new_dci in [
        (3169, 'GUAYACOLATO DE GLICERILO', 'GUAIACOLATO DE GLICERILO'),
        (3279, 'GUAYACOLATO DE GLICERILO', 'GUAIACOLATO DE GLICERILO'),
    ]:
        cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and old_dci in (row[0] or ''):
            new_dci_key = row[0].replace(old_dci, new_dci)
            cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_dci_key, gid))
            print(f"  [D] id={gid}: dci '{row[0]}' -> '{new_dci_key}'")
            n['D'] += 1
            # sync cum_normalizado
            cids = json.loads(row[1] or '[]')
            upd = sync_dci_in_cum(cur, cids, old_dci, new_dci)
            if upd:
                print(f"    cum_normalizado: {upd} productos actualizados")
    # Global sync for any remaining GUAYACOLATO in cum_normalizado
    cur.execute("SELECT expediente_cum, consecutivo_cum, principios_dci FROM cum_normalizado WHERE principios_dci LIKE '%GUAYACOLATO%'")
    extra = 0
    for exp, consec, pdci_json in cur.fetchall():
        pdci = json.loads(pdci_json)
        new_pdci = ['GUAIACOLATO DE GLICERILO' if d == 'GUAYACOLATO DE GLICERILO' else d for d in pdci]
        if new_pdci != pdci:
            cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                        (json.dumps(new_pdci), exp, consec))
            extra += 1
    if extra:
        print(f"  [D] cum_normalizado global: {extra} adicionales GUAYACOLATO->GUAIACOLATO")

    # -- E. BROMHEXINA||GUAIFENSINA id=3522: DCI typo + conc completa -------------
    print("\n=== E. BROMHEXINA||GUAIFENSINA id=3522 ===")
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=3522")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='BROMHEXINA||GUAIFENESINA', concentracion_norm='0.08 mg/mL + 2 mg/mL'
            WHERE id=3522
        """)
        print(f"  [E] id=3522: '{row[0]}' -> BROMHEXINA||GUAIFENESINA, conc -> '0.08 mg/mL + 2 mg/mL'")
        n['E'] += 1
        # sync cum_normalizado
        cids = json.loads(row[1] or '[]')
        upd = sync_dci_in_cum(cur, cids, 'GUAIFENSINA', 'GUAIFENESINA')
        print(f"  [E] cum_normalizado: {upd} productos GUAIFENSINA->GUAIFENESINA")
    # Global sync
    cur.execute("SELECT expediente_cum, consecutivo_cum, principios_dci FROM cum_normalizado WHERE principios_dci LIKE '%GUAIFENSINA%'")
    extra = 0
    for exp, consec, pdci_json in cur.fetchall():
        pdci = json.loads(pdci_json)
        new_pdci = ['GUAIFENESINA' if d == 'GUAIFENSINA' else d for d in pdci]
        if new_pdci != pdci:
            cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                        (json.dumps(new_pdci), exp, consec))
            extra += 1
    if extra:
        print(f"  [E] global: {extra} adicionales GUAIFENSINA->GUAIFENESINA")

    # -- F. Post-fix auto-merge duplicados ----------------------------------------
    print("\n=== F. Post-fix auto-merge ===")
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
