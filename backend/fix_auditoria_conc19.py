"""
fix_auditoria_conc19.py — Decimonovena ronda de auditoría.

Correcciones:
  A) OFTALMICO — concentración incompleta (ETL usó solo componente menor):
     - id=2725 DEXTRAN 70||HIDROXIPROPILMETILCELULOSA: "1 mg/mL" -> "1 mg/mL + 3 mg/mL"
     - id=3123 DEXTRANO 70||HIPROMELOSA: DCI typo DEXTRANO->DEXTRAN + "10 mg/mL" -> "1 mg/mL + 3 mg/mL"
       -> merge en id=2725 (DEXTRAN 70 Tears Naturale, n=3->6)
     - id=3532 CONDROITINA SULFATO SODICO||HIALURONATO: DCI typo SULFATO SODICO->SULFATO DE SODIO
       + ETL interpretó % como mg/mL: 0.1% HA = 1 mg/mL, 0.18% CS = 1.8 mg/mL
       -> "0.1 mg/mL" -> "1.8 mg/mL + 1 mg/mL", fix cum_normalizado concentracion_mg_ml
       -> merge en id=3352 (CONDROITINA SULFATO DE SODIO||HIALURONATO DE SODIO, n=5->8)
     - id=3148 CLORURO DE POTASIO||CLORURO DE SODIO: "50 mg/mL" -> "12.5 mg/mL + 37.5 mg/mL"
       (ETL sumó KCl=12.5 + NaCl=37.5 = 50 mg/mL)
  B) INYECTABLE — concentración incompleta o unidad errónea:
     - id=2740 BSS: "0.64%" (solo NaCl) -> "3.9 mg/mL + 1.7 mg/mL + 0.48 mg/mL + 0.3 mg/mL + 0.75 mg/mL + 6.4 mg/mL"
       (ACETATO=3.9, CITRATO=1.7, CaCl2=0.48, MgCl=0.3, KCl=0.75, NaCl=6.4)
     - id=2804 ACEITE DE SOYA||TRIGLICERIDOS DE CADENA MEDIA: "20%" -> "100 mg/mL + 100 mg/mL"
       (Lipofundin MCT/LCT 20%: 100mg/mL ACEITE SOYA + 100mg/mL MCT; INYECTABLE usa mg/mL)
     - id=2279 BENDAMUSTINA: "11.2 mg/mL" -> "45 mg/mL"
       (Purpulz 180Mg/4mL = 45mg/mL; ETL tomó dosis=45 en vez de 180, calculó 45/4=11.25)
       + Fix cum_normalizado: dosis_total_mg=45->180, concentracion_mg_ml=11.25->45
  C) LIQUIDO_ORAL — ORS electrolíticos con conc errónea:
     - id=3464 CITRATO DE POTASIO||CITRATO DE SODIO||CLORURO DE SODIO||DEXTROSA||GLUCONATO DE ZINC:
       "45 mg/mL" -> "2.16 mg/mL + 0.94 mg/mL + 2.076 mg/mL + 22.73 mg/mL + 0.061 mg/mL"
       (Hidraplus 45; "45" = mEq/L Na, no concentración mg/mL)
     - id=3463: misma fórmula, "450 mg/mL" (x10 error) -> misma conc -> merge en id=3464
     - id=3452 CITRATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO||DEXTROSA||GLUCONATO DE ZINC:
       "75 mg/mL" -> "2.9 mg/mL + 1.5 mg/mL + 2.6 mg/mL + 13.5 mg/mL + 0.061 mg/mL"
       + Fix cum_normalizado GLUCONATO DE ZINC 60.43 -> 0.061 (ETL confundió mg/L con mg/mL)
     - id=3688 ACIDO ASCORBICO||ASCORBATO DE SODIO: "100 mg/mL" -> "72.5 mg/mL + 31.9 mg/mL"
       (Roxidil gotas: AA=72.5 + Ascorbato=31.9; ETL usó suma redondeada)
  D) TOPICO — segundo componente faltante:
     - id=1294 ACIDO SALICILICO||RUIBARBO: "1%" -> "0.1% + 0.5%"
       (ACIDO SALICILICO=1.0mg/mL=0.1%, RUIBARBO=5.0mg/mL=0.5%)
  E) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. OFTALMICO multi-componente -----------------------------------------------
    print("\n=== A. OFTALMICO multi-componente ===")

    # A1: DEXTRAN 70||HIPROMELOSA id=2725: "1 mg/mL" -> "1 mg/mL + 3 mg/mL"
    n['A'] += fix_conc(cur, 2725, "1 mg/mL + 3 mg/mL", "A_dextran70_hipromelosa")

    # A2: DEXTRANO 70||HIPROMELOSA id=3123: DCI typo + "10 mg/mL" -> "1 mg/mL + 3 mg/mL"
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=3123")
    row = cur.fetchone()
    if row and 'DEXTRANO 70' in (row[0] or ''):
        new_dci = row[0].replace('DEXTRANO 70', 'DEXTRAN 70')
        cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=3123", (new_dci,))
        print(f"  [A2] id=3123: dci '{row[0]}' -> '{new_dci}'")
        n['A'] += 1
        cids = json.loads(row[1] or '[]')
        upd = sync_dci_in_cum(cur, cids, 'DEXTRANO 70', 'DEXTRAN 70')
        if upd:
            print(f"    cum_normalizado: {upd} DEXTRANO 70->DEXTRAN 70")
        # Fix concentracion_mg_ml: 10.0 -> 1.0 (ETL extrapoló mal)
        fixed = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("UPDATE cum_normalizado SET concentracion_mg_ml=1.0 WHERE expediente_cum=? AND consecutivo_cum=? AND concentracion_mg_ml=10.0", (exp, consec))
            if cur.rowcount:
                fixed += 1
        if fixed:
            print(f"    concentracion_mg_ml: {fixed} corregidos 10.0->1.0")
    n['A'] += fix_conc(cur, 3123, "1 mg/mL + 3 mg/mL", "A_dextrano70_hipromelosa_conc")
    # auto-merge via D step

    # A3: CONDROITINA SULFATO SODICO||HIALURONATO id=3532:
    # DCI fix + % interpretado como mg/mL -> corregir a mg/mL reales
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=3532")
    row = cur.fetchone()
    if row and 'CONDROITINA SULFATO SODICO' in (row[0] or ''):
        new_dci = row[0].replace('CONDROITINA SULFATO SODICO', 'CONDROITINA SULFATO DE SODIO')
        cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=3532", (new_dci,))
        print(f"  [A3] id=3532: dci '{row[0]}' -> '{new_dci}'")
        n['A'] += 1
        cids = json.loads(row[1] or '[]')
        upd = sync_dci_in_cum(cur, cids, 'CONDROITINA SULFATO SODICO', 'CONDROITINA SULFATO DE SODIO')
        if upd:
            print(f"    cum_normalizado DCI: {upd} productos actualizados")
        # Fix cum_normalizado: componentes ETL leyó 0.1% como 0.1mg/mL (debe ser 1.0mg/mL)
        # y 0.18% como 0.18mg/mL (debe ser 1.8mg/mL); corregir concentracion_mg_ml
        fixed = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("UPDATE cum_normalizado SET concentracion_mg_ml=1.8 WHERE expediente_cum=? AND consecutivo_cum=? AND concentracion_mg_ml IN (0.1, 0.18)", (exp, consec))
            if cur.rowcount:
                fixed += 1
        if fixed:
            print(f"    concentracion_mg_ml: {fixed} productos 0.1/0.18->1.8")
        # Also update components JSON for CONDROITINA SULFATO SODICO->SULFATO DE SODIO in componentes
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
            p = cur.fetchone()
            if p and p[0]:
                comps = json.loads(p[0])
                changed = False
                for c in comps:
                    if c.get('dci') == 'CONDROITINA SULFATO SODICO':
                        c['dci'] = 'CONDROITINA SULFATO DE SODIO'
                        c['concentracion_mg_ml'] = 1.8
                        changed = True
                    elif c.get('dci') == 'HIALURONATO DE SODIO' and c.get('concentracion_mg_ml') in (0.1, 0.18):
                        c['concentracion_mg_ml'] = 1.0
                        changed = True
                if changed:
                    cur.execute("UPDATE cum_normalizado SET componentes=? WHERE expediente_cum=? AND consecutivo_cum=?",
                                (json.dumps(comps), exp, consec))
    n['A'] += fix_conc(cur, 3532, "1.8 mg/mL + 1 mg/mL", "A_condroitina_sulfato_sodico")
    # auto-merge id=3532->3352 via E step

    # A4: CLORURO DE POTASIO||CLORURO DE SODIO id=3148: "50 mg/mL" -> "12.5 mg/mL + 37.5 mg/mL"
    n['A'] += fix_conc(cur, 3148, "12.5 mg/mL + 37.5 mg/mL", "A_kcl_nacl_oftalmico_sum")

    # -- B. INYECTABLE multi-componente ---------------------------------------------
    print("\n=== B. INYECTABLE multi-componente ===")

    # B1: BSS id=2740: "0.64%" -> 6-component string (ETL tomó solo NaCl en %)
    n['B'] += fix_conc(cur, 2740, "3.9 mg/mL + 1.7 mg/mL + 0.48 mg/mL + 0.3 mg/mL + 0.75 mg/mL + 6.4 mg/mL",
                       "B_bss_6component")

    # B2: Lipofundin MCT/LCT id=2804: "20%" -> "100 mg/mL + 100 mg/mL" (INYECTABLE usa mg/mL)
    n['B'] += fix_conc(cur, 2804, "100 mg/mL + 100 mg/mL", "B_lipofundin_mct_lct_20pct")

    # B3: BENDAMUSTINA id=2279: Purpulz 180Mg/4mL; ETL tomó dosis=45 en vez de 180
    n['B'] += fix_conc(cur, 2279, "45 mg/mL", "B_bendamustina_purpulz_180mg_4ml")
    # Fix cum_normalizado: dosis_total_mg 45->180, concentracion_mg_ml 11.25->45
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=2279")
    g = cur.fetchone()
    if g:
        cids = json.loads(g[0] or '[]')
        fixed = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("""UPDATE cum_normalizado SET dosis_total_mg=180.0, concentracion_mg_ml=45.0
                           WHERE expediente_cum=? AND consecutivo_cum=?
                           AND dosis_total_mg < 50 AND volumen_ml_por_unidad=4.0""",
                        (exp, consec))
            if cur.rowcount:
                fixed += 1
        if fixed:
            print(f"    cum_normalizado: {fixed} Purpulz dosis 45->180, conc 11.25->45")

    # -- C. LIQUIDO_ORAL ORS electrolíticos -----------------------------------------
    print("\n=== C. LIQUIDO_ORAL ORS ===")

    ORS45_CONC = "2.16 mg/mL + 0.94 mg/mL + 2.076 mg/mL + 22.73 mg/mL + 0.061 mg/mL"
    # C1: id=3464 Hidraplus45: "45 mg/mL" -> componentes reales
    n['C'] += fix_conc(cur, 3464, ORS45_CONC, "C_hidraplus45_ors_conc")
    # C2: id=3463 duplicada de id=3464: "450 mg/mL" -> misma conc -> auto-merge
    n['C'] += fix_conc(cur, 3463, ORS45_CONC, "C_hidraplus45_dup_450_x10err")

    # C3: id=3452 Hidraplus75: "75 mg/mL" -> componentes reales
    ORS75_CONC = "2.9 mg/mL + 1.5 mg/mL + 2.6 mg/mL + 13.5 mg/mL + 0.061 mg/mL"
    n['C'] += fix_conc(cur, 3452, ORS75_CONC, "C_hidraplus75_ors_conc")
    # Fix cum_normalizado GLUCONATO DE ZINC 60.43 -> 0.061 (mg/L error)
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3452")
    g = cur.fetchone()
    if g:
        cids = json.loads(g[0] or '[]')
        fixed = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
            p = cur.fetchone()
            if p and p[0]:
                comps = json.loads(p[0])
                changed = False
                for c in comps:
                    if c.get('dci') in ('GLUCONATO DE ZINC', 'ZINC GLUCONATO') and c.get('concentracion_mg_ml', 0) > 1.0:
                        c['concentracion_mg_ml'] = 0.061
                        changed = True
                if changed:
                    cur.execute("UPDATE cum_normalizado SET componentes=? WHERE expediente_cum=? AND consecutivo_cum=?",
                                (json.dumps(comps), exp, consec))
                    fixed += 1
        if fixed:
            print(f"    cum_normalizado: {fixed} ZINC GLUCONATO 60.43->0.061 mg/mL")

    # C4: ACIDO ASCORBICO||ASCORBATO DE SODIO id=3688: "100 mg/mL" -> "72.5 mg/mL + 31.9 mg/mL"
    n['C'] += fix_conc(cur, 3688, "72.5 mg/mL + 31.9 mg/mL", "C_ascorbico_ascorbato_roxidil")

    # -- D. TOPICO ----------------------------------------------------------------
    print("\n=== D. TOPICO multi-componente ===")

    # D1: ACIDO SALICILICO||RUIBARBO id=1294: "1%" -> "0.1% + 0.5%"
    # ACIDO SALICILICO=1.0mg/mL=0.1%, RUIBARBO=5.0mg/mL=0.5%
    n['D'] += fix_conc(cur, 1294, "0.1% + 0.5%", "D_acido_salicilico_ruibarbo")

    # -- E. Post-fix auto-merge duplicados ----------------------------------------
    print("\n=== E. Post-fix auto-merge ===")
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

    # -- Fix n_productos ----------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen ------------------------------------------------------------------
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
