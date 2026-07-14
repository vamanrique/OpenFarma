"""
fix_auditoria_conc25.py — Vigesimoquinta ronda de auditoría.

Correcciones — Normalización de nombres de sal (forma adjectiva -> "DE + sustantivo"):
  A) MAGNESIO SULFATO -> SULFATO DE MAGNESIO (5 grupos):
     - id=283  INYECTABLE 200 mg/mL (MgSO4 solo)
     - id=3556 MAGNESIO SULFATO||POTASIO SULFATO||SODIO SULFATO (bowel prep)
       -> SULFATO DE MAGNESIO||SULFATO DE POTASIO||SULFATO DE SODIO
     - id=3158 MAGNESIO SULFATO||RUIBARBO||SEN SOLIDO_ORAL -> RUIBARBO||SEN||SULFATO DE MAGNESIO
     - id=3159 mismo combo LIQUIDO_ORAL
     - id=3885 BOLDO||CASCARA SAGRADA||MAGNESIO SULFATO||RUIBARBO
       -> BOLDO||CASCARA SAGRADA||RUIBARBO||SULFATO DE MAGNESIO
  B) CALCIO CARBONATO -> CARBONATO DE CALCIO (4 grupos):
     - id=248  CARBONATO DE CALCIO 600 mg SOLIDO_ORAL
     - id=1276 CARBONATO DE CALCIO||COLECALCIFEROL 1498 mg + 200 UI
     - id=1549 CARBONATO DE CALCIO||COLECALCIFEROL 600 mg + 200 UI
     - id=2454 ALGINATO DE SODIO||BICARBONATO DE SODIO||CARBONATO DE CALCIO SOLIDO_ORAL
  C) id=2920: FLUORURO SODICO -> FLUORURO DE SODIO (Tracutil trace elements, n=1)
  D) id=1660: FUMARATO FERROSO -> HIERRO (Ferrimed Plus n=30)
     -> merge en id=1666 (ACIDO ASCORBICO||ACIDO FOLICO||CIANOCOBALAMINA||HIERRO, n=18 -> n=48)
  E) id=3673 y id=3675: OliClinomel – quitar prefijo L- de aminoácidos
     -> auto-merge (misma dci+via+SIN_CONCENTRACION tras normalización, n=4+6=10)
  F) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. MAGNESIO SULFATO -> SULFATO DE MAGNESIO ----------------------------------
    print("\n=== A. MAGNESIO SULFATO -> SULFATO DE MAGNESIO ===")
    mg_map = {
        "MAGNESIO SULFATO": "SULFATO DE MAGNESIO",
        "POTASIO SULFATO": "SULFATO DE POTASIO",
        "SODIO SULFATO": "SULFATO DE SODIO",
    }
    # id=283: MAGNESIO SULFATO solo, INYECTABLE 200 mg/mL
    n['A'] += rename_dci(con, 283, "SULFATO DE MAGNESIO", mg_map)
    # id=3556: bowel prep triple sulfate
    n['A'] += rename_dci(con, 3556,
                         "SULFATO DE MAGNESIO||SULFATO DE POTASIO||SULFATO DE SODIO", mg_map)
    # id=3158: laxante herbal SOLIDO_ORAL SIN_CONCENTRACION
    n['A'] += rename_dci(con, 3158, "RUIBARBO||SEN||SULFATO DE MAGNESIO", mg_map)
    # id=3159: mismo LIQUIDO_ORAL SIN_CONCENTRACION
    n['A'] += rename_dci(con, 3159, "RUIBARBO||SEN||SULFATO DE MAGNESIO", mg_map)
    # id=3885: laxante herbal BOLDO SOLIDO_ORAL SIN_CONCENTRACION
    n['A'] += rename_dci(con, 3885,
                         "BOLDO||CASCARA SAGRADA||RUIBARBO||SULFATO DE MAGNESIO", mg_map)

    # -- B. CALCIO CARBONATO -> CARBONATO DE CALCIO ----------------------------------
    print("\n=== B. CALCIO CARBONATO -> CARBONATO DE CALCIO ===")
    ca_map = {"CALCIO CARBONATO": "CARBONATO DE CALCIO"}
    # id=248: CARBONATO DE CALCIO 600 mg SOLIDO_ORAL
    n['B'] += rename_dci(con, 248, "CARBONATO DE CALCIO", ca_map)
    # id=1276: +COLECALCIFEROL 1498+200UI
    n['B'] += rename_dci(con, 1276, "CARBONATO DE CALCIO||COLECALCIFEROL", ca_map)
    # id=1549: +COLECALCIFEROL 600+200UI
    n['B'] += rename_dci(con, 1549, "CARBONATO DE CALCIO||COLECALCIFEROL", ca_map)
    # id=2454: ALGINATO DE SODIO||BICARBONATO DE SODIO||CARBONATO DE CALCIO SOLIDO_ORAL
    n['B'] += rename_dci(con, 2454,
                         "ALGINATO DE SODIO||BICARBONATO DE SODIO||CARBONATO DE CALCIO", ca_map)

    # -- C. id=2920: FLUORURO SODICO -> FLUORURO DE SODIO (Tracutil) -----------------
    print("\n=== C. id=2920 Tracutil: FLUORURO SODICO -> FLUORURO DE SODIO ===")
    n['C'] += rename_dci(con, 2920,
                         "COBRE||CROMO||FLUORURO DE SODIO||HIERRO||MANGANESO||MOLIBDATO DE SODIO||SELENITO DE SODIO||YODURO DE POTASIO||ZINC",
                         {"FLUORURO SODICO": "FLUORURO DE SODIO"})

    # -- D. id=1660: FUMARATO FERROSO -> HIERRO (Ferrimed Plus) ----------------------
    print("\n=== D. id=1660 Ferrimed Plus: FUMARATO FERROSO -> HIERRO ===")
    n['D'] += rename_dci(con, 1660,
                         "ACIDO ASCORBICO||ACIDO FOLICO||CIANOCOBALAMINA||HIERRO",
                         {"FUMARATO FERROSO": "HIERRO"})
    # auto-merge: id=1660 (n=30) -> id=1666 (n=18) -> total=48

    # -- E. id=3673, 3675: OliClinomel – quitar prefijo L- de aminoácidos -----------
    print("\n=== E. id=3673, id=3675: OliClinomel L-aminoacidos normalizacion ===")
    l_map = {
        "L-ALANINA": "ALANINA", "L-ARGININA": "ARGININA", "L-FENILALANINA": "FENILALANINA",
        "L-HISTIDINA": "HISTIDINA", "L-ISOLEUCINA": "ISOLEUCINA", "L-LEUCINA": "LEUCINA",
        "L-LISINA": "LISINA", "L-METIONINA": "METIONINA", "L-PROLINA": "PROLINA",
        "L-SERINA": "SERINA", "L-TIROSINA": "TIROSINA", "L-TREONINA": "TREONINA",
        "L-TRIPTOFANO": "TRIPTOFANO", "L-VALINA": "VALINA",
    }
    oliclinomel_dci = ("ACEITE DE OLIVA REFINADO||ACEITE DE PESCADO RICO EN ACIDOS OMEGA-3||"
                       "ACEITE DE SOYA REFINADA||ALANINA||ARGININA||DEXTROSA||FENILALANINA||"
                       "HISTIDINA||ISOLEUCINA||LEUCINA||LISINA||METIONINA||PROLINA||SERINA||"
                       "TAURINA||TIROSINA||TREONINA||TRIGLICERIDOS DE CADENA MEDIA||TRIPTOFANO||VALINA")
    n['E'] += rename_dci(con, 3673, oliclinomel_dci, l_map)
    n['E'] += rename_dci(con, 3675, oliclinomel_dci, l_map)
    # auto-merge: 3673 (n=4) y 3675 (n=6) -> misma dci+INYECTABLE+SIN_CONCENTRACION -> total=10

    # -- F. Post-fix auto-merge -------------------------------------------------------
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
