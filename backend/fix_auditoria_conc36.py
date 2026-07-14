"""
fix_auditoria_conc36.py — Trigesimosexta ronda de auditoría.

Correcciones — INN ORS/laxantes e hidratación estándar:
  A) MACROGOL 3350 -> POLIETILENGLICOL 3350 (INN alternativo; POLIETILENGLICOL es conv. DB):
     - id=3685: ACIDO ASCORBICO||ASCORBATO DE SODIO||...||MACROGOL 3350||SULFATO DE SODIO ANHIDRO
       SOLIDO_ORAL SIN_CONC (n=1, Plenvu) -> sin merge existente
  B) id=2547: CLORURO DE POTASIO||CLORURO DE SODIO||HIDROGENOCARBONATO DE SODIO||MACROGOL
     LIQUIDO_ORAL SIN_CONC (n=2, Calmivur):
     - HIDROGENOCARBONATO DE SODIO -> BICARBONATO DE SODIO (INN estándar español)
     - MACROGOL -> POLIETILENGLICOL 3350 (conv. DB; BICARBONATO<CLORURO PO<CLORURO SO<PEG)
     - auto-merge -> id=2910 (BICARBONATO DE SODIO||CLP||CLS||PEG3350 LO SIN_CONC, n=11 -> n=13)
  C) id=3511: CITRATO DE SODIO DIHIDRATADO -> CITRATO DE SODIO (INN sin especificar hidratación):
     - CITRATO DE SODIO DIHIDRATADO||CLORURO DE POTASIO||CLORURO DE SODIO||DEXTROSA||GLUCONATO DE ZINC
       LIQUIDO_ORAL SIN_CONC (n=13, Pediasol 75 Meq Con Zinc)
     - auto-merge -> id=3449 (CITRATO DE SODIO||CLP||CLS||DEXTROSA||GL.ZINC LO SIN_CONC, n=167 -> n=180)
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

    # -- A. MACROGOL 3350 -> POLIETILENGLICOL 3350 (id=3685, Plenvu) -----------------
    print("\n=== A. id=3685: MACROGOL 3350 -> POLIETILENGLICOL 3350 ===")
    n['A'] += rename_dci(
        con, 3685,
        "ACIDO ASCORBICO||ASCORBATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO"
        "||POLIETILENGLICOL 3350||SULFATO DE SODIO ANHIDRO",
        {"MACROGOL 3350": "POLIETILENGLICOL 3350"}
    )

    # -- B. id=2547: HIDROGENOCARBONATO + MACROGOL -> BICARBONATO + POLIETILENGLICOL -
    print("\n=== B. id=2547: HIDROGENOCARBONATO DE SODIO + MACROGOL -> BICARBONATO DE SODIO + POLIETILENGLICOL 3350 ===")
    n['B'] += rename_dci(
        con, 2547,
        "BICARBONATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO||POLIETILENGLICOL 3350",
        {"HIDROGENOCARBONATO DE SODIO": "BICARBONATO DE SODIO",
         "MACROGOL": "POLIETILENGLICOL 3350"}
    )
    # auto-merge 2547 (n=2) -> 2910 (n=11) -> total=13

    # -- C. id=3511: CITRATO DE SODIO DIHIDRATADO -> CITRATO DE SODIO ----------------
    print("\n=== C. id=3511: CITRATO DE SODIO DIHIDRATADO -> CITRATO DE SODIO ===")
    n['C'] += rename_dci(
        con, 3511,
        "CITRATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO||DEXTROSA||GLUCONATO DE ZINC",
        {"CITRATO DE SODIO DIHIDRATADO": "CITRATO DE SODIO"}
    )
    # auto-merge 3511 (n=13) -> 3449 (n=167) -> total=180

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
