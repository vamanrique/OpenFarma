"""
fix_auditoria_conc71.py — Septuagesimoprima ronda de auditoría.

Correcciones:

  A) TECNECIO (99MTC) PERTECNETATO -> TECNECIO (99MTC) PENTETATO
     (Technescan DTPA = kit Tc-99m DTPA; DTPA es pentetato, NO pertecnetato;
      pertecnetato = ion libre TcO4-; pentetato = DTPA quelato de Tc-99m):
     - id=3689: IN SIN_CONC (n=1) -> sin merge

  B) id=3391 (Prevenar 13): estandarizar 13 polisacáridos + proteína transportadora
     al mismo formato que id=3687 (Vaxneuvance):
     - POLISACARIDO SEROTIPO X -> POLISACARIDO DEL SEROTIPO NEUMOCOCICO X (x13)
     - PROTEINA TRANSPORTADORA CRM 197 -> CRM197
     No merge: Prevenar13 (13 serotipos) y Vaxneuvance (15 serotipos) son productos
     distintos con dci_key diferentes tras renombrado.
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"

PNEUMO_SEROTYPES = [
    "1", "3", "4", "5", "6A", "6B", "7F", "9V", "14", "18C", "19A", "19F", "23F"
]

PNEUMO_SYNC = {f"POLISACARIDO SEROTIPO {s}": f"POLISACARIDO DEL SEROTIPO NEUMOCOCICO {s}"
               for s in PNEUMO_SEROTYPES}
PNEUMO_SYNC["PROTEINA TRANSPORTADORA CRM 197"] = "CRM197"

NEW_PNEUMO_DCI = "||".join(sorted(PNEUMO_SYNC.values()))


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
    print(f"  [RENAME] id={gid}: '{old_dci[:80]}' -> '{new_dci[:80]}'")
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
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # -- A. TECNECIO (99MTC) PERTECNETATO -> TECNECIO (99MTC) PENTETATO (id=3689) ------
    print("\n=== A. TECNECIO (99MTC) PERTECNETATO -> PENTETATO (id=3689) ===")
    n['A'] += rename_dci(con, 3689, "TECNECIO (99MTC) PENTETATO",
                         {"TECNECIO (99MTC) PERTECNETATO": "TECNECIO (99MTC) PENTETATO"})

    # -- B. Prevenar 13 (id=3391): POLISACARIDO SEROTIPO X -> DEL SEROTIPO NEUMOCOCICO X
    print("\n=== B. Prevenar13 polisacaridos+CRM197 -> forma canónica (id=3391) ===")
    n['B'] += rename_dci(con, 3391, NEW_PNEUMO_DCI, PNEUMO_SYNC)

    # -- C. Post-fix auto-merge -------------------------------------------------------
    print("\n=== C. Post-fix auto-merge ===")
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

    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

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
