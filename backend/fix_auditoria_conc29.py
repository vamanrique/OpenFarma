"""
fix_auditoria_conc29.py — Vigesimonovena ronda de auditoría.

Correcciones:
  A) ACIDOS OMEGA 3 -> ACIDOS GRASOS OMEGA-3 (INN estándar):
     - id=1749: ACIDOS OMEGA 3||ATORVASTATINA SOLIDO_ORAL 840+10 mg (sin reorden, A<A)
  B) ACIDOS GRASOS OMEGA 3 -> ACIDOS GRASOS OMEGA-3 (añadir guión):
     - id=3439: NutriFlex Big complejo INYECTABLE SIN_CONC (posición relativa sin cambio)
  C) DHA -> ACIDO DOCOSAHEXAENOICO (INN completo):
     - id=1905: P-Natal SOLIDO_ORAL 14 componentes
       DHA estaba en pos 6 (30 mg); pasa a pos 2 después de reordenamiento
       fix_conc: "70 + 0.6 + 125 + 400 + 150 + 30 + 17 + 4 + 2.664 + 3.4 + 3 + 10 + 0.0022 + 15"
       -> "70 + 30 + 0.6 + 125 + 400 + 150 + 17 + 4 + 2.664 + 3.4 + 3 + 10 + 0.0022 + 15"
  D) DALTEPARINA SODICA -> DALTEPARINA (eliminar sufijo sal):
     - id=3041: INYECTABLE 2500 UI -> merge id=3047 (n=2+4=6)
     - id=3039: INYECTABLE 5000 UI -> nuevo grupo DALTEPARINA 5000 UI (n=6)
  E) SODIO BORATO -> BORATO DE SODIO (forma DE estándar):
     - id=3500: Biocalcium Plus LIQUIDO_ORAL SIN_CONC (singleton)
       nueva dci_key: BORATO DE SODIO||CALCIO||COBRE||COLECALCIFEROL||MAGNESIO||MANGANESO||ZINC
  F) SODIO MOLIBDATO -> MOLIBDATO DE SODIO, SODIO PERTECNETATO -> PERTECNETATO DE SODIO:
     - id=3589: generador 99Mo/99mTc INYECTABLE (M<P: mismo orden)
  G) Post-fix auto-merge duplicados
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
    print(f"  [FIX_CONC] id={gid}: '{row[0]}' -> '{new_conc}'")
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'F', 'merge']}

    # -- A. ACIDOS OMEGA 3 -> ACIDOS GRASOS OMEGA-3 ----------------------------------
    print("\n=== A. id=1749: ACIDOS OMEGA 3 -> ACIDOS GRASOS OMEGA-3 ===")
    n['A'] += rename_dci(con, 1749, "ACIDOS GRASOS OMEGA-3||ATORVASTATINA",
                         {"ACIDOS OMEGA 3": "ACIDOS GRASOS OMEGA-3"})

    # -- B. ACIDOS GRASOS OMEGA 3 -> ACIDOS GRASOS OMEGA-3 (añadir guión) -----------
    print("\n=== B. id=3439: ACIDOS GRASOS OMEGA 3 -> ACIDOS GRASOS OMEGA-3 ===")
    n['B'] += rename_dci(con, 3439,
                         "ACEITE DE SOYA||ACIDO ASPARTICO||ACIDO GLUTAMICO||ACIDOS GRASOS OMEGA-3||"
                         "ALANINA||ARGININA||CALCIO||DEXTROSA||FENILALANINA||GLICINA||HISTIDINA||"
                         "ISOLEUCINA||LEUCINA||LISINA||MAGNESIO||METIONINA||POTASIO||PROLINA||SERINA||"
                         "SODIO||TREONINA||TRIGLICERIDOS DE CADENA MEDIA||TRIPTOFANO||VALINA||ZINC",
                         {"ACIDOS GRASOS OMEGA 3": "ACIDOS GRASOS OMEGA-3"})

    # -- C. DHA -> ACIDO DOCOSAHEXAENOICO (INN completo, con reorden conc) -----------
    print("\n=== C. id=1905: DHA -> ACIDO DOCOSAHEXAENOICO + fix conc ===")
    # Old order: ACIDO ASCORBICO(1=70mg) ACIDO FOLICO(2=0.6mg) CALCIO(3=125mg)
    #   CIANOCOBALAMINA(4=400UI) COLECALCIFEROL(5=150mg) DHA(6=30mg) HIERRO(7=17mg)
    #   NICOTINAMIDA(8=4mg) PIRIDOXINA(9=2.664mg) RETINOL(10=3.4mg) RIBOFLAVINA(11=3mg)
    #   TIAMINA(12=10mg) TOCOFEROL(13=0.0022mg) ZINC(14=15mg)
    # New order: ACIDO ASCORBICO(1) ACIDO DOCOSAHEXAENOICO(2) ACIDO FOLICO(3)
    #   CALCIO(4) CIANOCOBALAMINA(5) COLECALCIFEROL(6) HIERRO(7)...ZINC(14)
    n['C'] += rename_dci(con, 1905,
                         "ACIDO ASCORBICO||ACIDO DOCOSAHEXAENOICO||ACIDO FOLICO||CALCIO||"
                         "CIANOCOBALAMINA||COLECALCIFEROL||HIERRO||NICOTINAMIDA||PIRIDOXINA||"
                         "RETINOL||RIBOFLAVINA||TIAMINA||TOCOFEROL||ZINC",
                         {"DHA": "ACIDO DOCOSAHEXAENOICO"})
    fix_conc(cur, 1905,
             "70 mg + 30 mg + 0.6 mg + 125 mg + 400 UI + 150 mg + 17 mg + 4 mg + "
             "2.664 mg + 3.4 mg + 3 mg + 10 mg + 0.0022 mg + 15 mg")

    # -- D. DALTEPARINA SODICA -> DALTEPARINA ----------------------------------------
    print("\n=== D. DALTEPARINA SODICA -> DALTEPARINA ===")
    dal_map = {"DALTEPARINA SODICA": "DALTEPARINA"}
    n['D'] += rename_dci(con, 3041, "DALTEPARINA", dal_map)
    # auto-merge: 3041 (2500 UI, n=2) -> 3047 (DALTEPARINA 2500 UI, n=4) -> total=6
    n['D'] += rename_dci(con, 3039, "DALTEPARINA", dal_map)
    # 3039 (5000 UI, n=6) stays as new DALTEPARINA 5000 UI group

    # -- E. SODIO BORATO -> BORATO DE SODIO ------------------------------------------
    print("\n=== E. id=3500: SODIO BORATO -> BORATO DE SODIO ===")
    # New dci_key sorted: BORATO DE SODIO||CALCIO||COBRE||COLECALCIFEROL||MAGNESIO||MANGANESO||ZINC
    # (B comes before C, same SIN_CONCENTRACION -> no conc reorder needed)
    n['E'] += rename_dci(con, 3500,
                         "BORATO DE SODIO||CALCIO||COBRE||COLECALCIFEROL||MAGNESIO||MANGANESO||ZINC",
                         {"SODIO BORATO": "BORATO DE SODIO"})

    # -- F. SODIO MOLIBDATO/PERTECNETATO -> forma DE estándar -----------------------
    print("\n=== F. id=3589: SODIO MOLIBDATO/PERTECNETATO -> MOLIBDATO/PERTECNETATO DE SODIO ===")
    # M<P: orden relativo no cambia, conc "43 g" no requiere reorden
    n['F'] += rename_dci(con, 3589,
                         "MOLIBDATO DE SODIO (99MO)||PERTECNETATO DE SODIO (99MTC)",
                         {"SODIO MOLIBDATO (99MO)": "MOLIBDATO DE SODIO (99MO)",
                          "SODIO PERTECNETATO (99MTC)": "PERTECNETATO DE SODIO (99MTC)"})

    # -- G. Post-fix auto-merge -------------------------------------------------------
    print("\n=== G. Post-fix auto-merge ===")
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
