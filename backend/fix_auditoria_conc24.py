"""
fix_auditoria_conc24.py — Vigesimocuarta ronda de auditoría.

Correcciones — Normalización de nombres de sal (forma adjetiva -> "DE + sustantivo"):
  A) id=3637 Olimeln: CLORURO CALCICO/MAGNESICO/POTASICO + ACETATO SODICO + GLICEROFOSFATO SODICO
     -> CLORURO DE CALCIO/MAGNESIO/POTASIO + ACETATO DE SODIO + GLICEROFOSFATO DE SODIO
     -> merge en id=3440 (misma composición, n=3 -> n=9)
  B) id=937 Glycophos: "GLICEROFOSFATO SODICO" -> "GLICEROFOSFATO DE SODIO" 216 mg/mL (nuevo grupo)
  C) id=3343: "CROMOGLICATO SODICO" -> "CROMOGLICATO DE SODIO" 40mg/mL OFTALMICO
     -> merge en id=3103 (n=5 -> n=11)
  D) YODURO vs IODURO: dos formas del mismo nombre para I-131 sodio:
     - id=3448 "IODURO DE SODIO I-131" SOLIDO_ORAL -> "YODURO DE SODIO (131I)" -> merge id=3316 (n=3->6)
     - id=3590 "IODURO SODICO(131I)" LIQUIDO_ORAL -> "YODURO DE SODIO (131I)" (queda solo, distinta via)
  E) id=1949: "DOBESILATO CALCICO" -> "DOBESILATO DE CALCIO" 500mg SOLIDO_ORAL
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. id=3637: Olimeln sal adjective normalization ----------------------------
    print("\n=== A. id=3637 Olimeln: normalizacion sales adjectivas ===")
    salt_map = {
        "ACETATO SODICO": "ACETATO DE SODIO",
        "CLORURO CALCICO": "CLORURO DE CALCIO",
        "CLORURO MAGNESICO": "CLORURO DE MAGNESIO",
        "CLORURO POTASICO": "CLORURO DE POTASIO",
        "GLICEROFOSFATO SODICO": "GLICEROFOSFATO DE SODIO",
    }
    n['A'] += rename_dci(con, 3637,
                         "ACEITE DE OLIVA||ACEITE DE SOYA||ACETATO DE SODIO||ACIDO ASPARTICO||ACIDO GLUTAMICO||ALANINA||ARGININA||CLORURO DE CALCIO||CLORURO DE MAGNESIO||CLORURO DE POTASIO||DEXTROSA||FENILALANINA||GLICEROFOSFATO DE SODIO||GLICINA||HISTIDINA||ISOLEUCINA||LEUCINA||LISINA||METIONINA||PROLINA||SERINA||TIROSINA||TREONINA||TRIPTOFANO||VALINA",
                         salt_map)
    # auto-merge: 3637 -> 3440 (same dci+via+SIN_CONCENTRACION after rename)

    # -- B. id=937: GLICEROFOSFATO SODICO -> GLICEROFOSFATO DE SODIO ----------------
    print("\n=== B. id=937 Glycophos: GLICEROFOSFATO SODICO -> GLICEROFOSFATO DE SODIO ===")
    n['B'] += rename_dci(con, 937, "GLICEROFOSFATO DE SODIO",
                         {"GLICEROFOSFATO SODICO": "GLICEROFOSFATO DE SODIO"})

    # -- C. id=3343: CROMOGLICATO SODICO -> CROMOGLICATO DE SODIO ------------------
    print("\n=== C. id=3343: CROMOGLICATO SODICO -> CROMOGLICATO DE SODIO 40mg/mL ===")
    n['C'] += rename_dci(con, 3343, "CROMOGLICATO DE SODIO",
                         {"CROMOGLICATO SODICO": "CROMOGLICATO DE SODIO"})
    # auto-merge: 3343 -> 3103 (CROMOGLICATO DE SODIO OFTALMICO 40mg/mL n=5 -> n=11)

    # -- D. YODURO vs IODURO (radioactive sodium iodide I-131) ----------------------
    print("\n=== D. IODURO -> YODURO normalizacion (I-131 sodio) ===")
    ioduro_map = {
        "IODURO DE SODIO I-131": "YODURO DE SODIO (131I)",
        "IODURO SODICO(131I)": "YODURO DE SODIO (131I)",
    }
    # id=3448: IODURO DE SODIO I-131 -> YODURO DE SODIO (131I) -> merge id=3316
    n['D'] += rename_dci(con, 3448, "YODURO DE SODIO (131I)",
                         {"IODURO DE SODIO I-131": "YODURO DE SODIO (131I)"})
    # id=3590: IODURO SODICO(131I) LIQUIDO_ORAL -> YODURO DE SODIO (131I) (no merge)
    n['D'] += rename_dci(con, 3590, "YODURO DE SODIO (131I)",
                         {"IODURO SODICO(131I)": "YODURO DE SODIO (131I)"})

    # -- E. id=1949: DOBESILATO CALCICO -> DOBESILATO DE CALCIO -------------------
    print("\n=== E. id=1949: DOBESILATO CALCICO -> DOBESILATO DE CALCIO ===")
    n['E'] += rename_dci(con, 1949, "DOBESILATO DE CALCIO",
                         {"DOBESILATO CALCICO": "DOBESILATO DE CALCIO"})

    # -- F. Post-fix auto-merge ---------------------------------------------------
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

    # -- Fix n_productos ---------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen -----------------------------------------------------------------
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
