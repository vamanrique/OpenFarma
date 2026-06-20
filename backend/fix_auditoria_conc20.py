"""
fix_auditoria_conc20.py — Vigésima ronda de auditoría.

Correcciones — Factores de coagulación: normalización DCI y fusiones:
  A) FEIBA misclasificado en FACTOR VIII 250 UI:
     - cum_id 226747-4 (Feiba 500 U/20 Ml) estaba en id=2988 (FACTOR VIII 250 UI)
     - Mover a id=3602 (FACTOR VIII INHIBIDOR BYPASS ACTIVITY)
  B) FEIBA DCI normalización:
     - id=3379 "FACTOR VIII INHIBIDOR ACTIVADO POR BYPASS" -> "FACTOR VIII INHIBIDOR BYPASS ACTIVITY"
     -> merge en id=3602
  C) PCC (Prothrombin Complex Concentrate) DCI normalización:
     - id=3308 "FACTOR II DE COAGULACION||...||FACTOR X DE COAGULACION||PROTEINA C||PROTEINA S"
     -> "FACTOR II||FACTOR IX||FACTOR VII||FACTOR X||PROTEINA C||PROTEINA S"
     -> merge en id=3656 (Hyfacta, n=4->6)
  D) FACTOR VIII||FACTOR VON WILLEBRAND DCI normalización (6 grupos):
     - id=2818,2819: "FACTOR VIII DE COAGULACION||FACTOR VON WILLEBRAND" -> "FACTOR VIII||FACTOR VON WILLEBRAND"
     - id=3483: "FACTOR VIII DE COAGULACION HUMANA||FACTOR VON WILLEBRAND" -> mismo
     - id=3504: "FACTOR VIII DE COAGULACION HUMANA||FACTOR VON WILLEBRAND HUMANO" -> mismo
     - id=2944: "FACTOR DE VON WILLEBRAND||FACTOR VIII ANTIHEMOFILICO" -> mismo (reorden: VIII antes VW)
     -> auto-merges: 3504+2944->3118(500UI), 2819->nueva 1000UI, 2818+3483->nueva SIN_CONC
  E) FACTOR VIII single-component DCI normalización:
     - id=3303,3302,3304: "FACTOR VIII DE COAGULACION" -> "FACTOR VIII"
     - id=3004: "FACTOR VIII DE COAGULACION HUMANO" -> "FACTOR VIII"
     - id=2935: "FACTOR ANTIHEMOFILICO HUMANO" -> "FACTOR VIII"
     - id=3581: "FACTOR VIII RECOMBINANTE (RFVIII)" -> "FACTOR VIII RECOMBINANTE"
     -> auto-merges: 3303->2988(250UI), 3302+3004+2935->nuevo(500UI), 3304->nueva(1000UI)
  F) FACTOR IX DCI normalización:
     - id=3017,3018: "FACTOR IX DE COAGULACION" -> "FACTOR IX"
     - id=3071,3072: "FACTOR IX HUMANO" -> "FACTOR IX"
  G) Sync cum_normalizado principios_dci para todos los grupos renombrados
  H) Post-fix auto-merge duplicados
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


def rename_dci(con, gid: int, new_dci: str, sync_map: dict) -> int:
    """Rename dci_key of group and sync principios_dci in cum_normalizado."""
    cur = con.cursor()
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_dci = row[0]
    if old_dci == new_dci:
        print(f"  [OK ya] id={gid}: dci ya es correcto")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_dci, gid))
    print(f"  [RENAME] id={gid}: '{old_dci}' -> '{new_dci}'")
    # Sync cum_normalizado
    cids = safe_json(row[1])
    updated = 0
    for cid in cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
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

    # -- A. FEIBA misclasificado: mover 226747-4 de id=2988 a id=3602 ----------------
    print("\n=== A. FEIBA misclasificado en FACTOR VIII 250 UI ===")
    feiba_cid = "226747-4"
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=2988")
    row2988 = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=3602")
    row3602 = cur.fetchone()
    if row2988 and row3602:
        ids_2988 = safe_json(row2988[0])
        ids_3602 = safe_json(row3602[0])
        if feiba_cid in ids_2988:
            ids_2988.remove(feiba_cid)
            if feiba_cid not in ids_3602:
                ids_3602.append(feiba_cid)
            cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=2988",
                        (json.dumps(ids_2988), len(ids_2988)))
            cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=3602",
                        (json.dumps(ids_3602), len(ids_3602)))
            print(f"  [A] Feiba 500U/20mL movida: id=2988 n={len(ids_2988)}, id=3602 n={len(ids_3602)}")
            n['A'] += 1
        else:
            print(f"  [OK ya] {feiba_cid} no estaba en id=2988")

    # -- B. FEIBA DCI normalización: id=3379 -> id=3602 --------------------------
    print("\n=== B. FEIBA DCI normalización ===")
    n['B'] += rename_dci(con, 3379, "FACTOR VIII INHIBIDOR BYPASS ACTIVITY",
                         {"FACTOR VIII INHIBIDOR ACTIVADO POR BYPASS": "FACTOR VIII INHIBIDOR BYPASS ACTIVITY"})
    n['merge'] += merge_into(con, 3602, 3379)

    # -- C. PCC: id=3308 -> id=3656 ------------------------------------------------
    print("\n=== C. PCC (Prothrombin Complex) normalización ===")
    pcc_norm = "FACTOR II||FACTOR IX||FACTOR VII||FACTOR X||PROTEINA C||PROTEINA S"
    pcc_map = {
        "FACTOR II DE COAGULACION": "FACTOR II",
        "FACTOR VII DE COAGULACION": "FACTOR VII",
        "FACTOR IX DE COAGULACION": "FACTOR IX",
        "FACTOR X DE COAGULACION": "FACTOR X",
    }
    n['C'] += rename_dci(con, 3308, pcc_norm, pcc_map)
    n['merge'] += merge_into(con, 3656, 3308)

    # -- D. FACTOR VIII||FACTOR VON WILLEBRAND combinations -----------------------
    print("\n=== D. FACTOR VIII||FACTOR VON WILLEBRAND normalización ===")
    fviii_vwf_norm = "FACTOR VIII||FACTOR VON WILLEBRAND"
    for gid, old_map in [
        (2818, {"FACTOR VIII DE COAGULACION": "FACTOR VIII"}),
        (2819, {"FACTOR VIII DE COAGULACION": "FACTOR VIII"}),
        (3483, {"FACTOR VIII DE COAGULACION HUMANA": "FACTOR VIII"}),
        (3504, {"FACTOR VIII DE COAGULACION HUMANA": "FACTOR VIII",
                "FACTOR VON WILLEBRAND HUMANO": "FACTOR VON WILLEBRAND"}),
        (2944, {"FACTOR DE VON WILLEBRAND": "FACTOR VON WILLEBRAND",
                "FACTOR VIII ANTIHEMOFILICO": "FACTOR VIII"}),
    ]:
        n['D'] += rename_dci(con, gid, fviii_vwf_norm, old_map)
    # auto-merge via H step

    # -- E. FACTOR VIII single-component normalization ----------------------------
    print("\n=== E. FACTOR VIII single-component normalización ===")
    fviii_norm = "FACTOR VIII"
    for gid, old_map in [
        (3303, {"FACTOR VIII DE COAGULACION": "FACTOR VIII"}),
        (3302, {"FACTOR VIII DE COAGULACION": "FACTOR VIII"}),
        (3304, {"FACTOR VIII DE COAGULACION": "FACTOR VIII"}),
        (3004, {"FACTOR VIII DE COAGULACION HUMANO": "FACTOR VIII"}),
        (2935, {"FACTOR ANTIHEMOFILICO HUMANO": "FACTOR VIII"}),
    ]:
        n['E'] += rename_dci(con, gid, fviii_norm, old_map)
    # FACTOR VIII RECOMBINANTE (RFVIII) -> FACTOR VIII RECOMBINANTE
    n['E'] += rename_dci(con, 3581, "FACTOR VIII RECOMBINANTE",
                         {"FACTOR VIII RECOMBINANTE (RFVIII)": "FACTOR VIII RECOMBINANTE"})
    # auto-merge via H step

    # -- F. FACTOR IX normalization -----------------------------------------------
    print("\n=== F. FACTOR IX normalización ===")
    fix_norm = "FACTOR IX"
    for gid, old_map in [
        (3017, {"FACTOR IX DE COAGULACION": "FACTOR IX"}),
        (3018, {"FACTOR IX DE COAGULACION": "FACTOR IX"}),
        (3071, {"FACTOR IX HUMANO": "FACTOR IX"}),
        (3072, {"FACTOR IX HUMANO": "FACTOR IX"}),
    ]:
        n['F'] += rename_dci(con, gid, fix_norm, old_map)
    # auto-merge: id=3071 (600 UI) and id=3072 (1000 UI) have different conc -> no merge
    # id=3017 (500 UI) with id=3018 (2000 UI) -> different conc -> no merge

    # -- H. Post-fix auto-merge --------------------------------------------------
    print("\n=== H. Post-fix auto-merge ===")
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
