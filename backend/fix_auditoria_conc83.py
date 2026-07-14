"""
fix_auditoria_conc83.py — Octogesimotercera ronda de auditoría.

Correcciones en radiofármacos:

  A) id=3615 (Ultra Technekow FM2.15 43 GBq, generador Mo/Tc):
     Registrado con DCI 'CLORURO DE SODIO||TECNECIO (99MTC)' — incorrecto:
     - CLORURO DE SODIO es el eluente del generador, no principio activo
     - TECNECIO (99MTC) no especifica la forma química (pertecnetato)
     Correcto: 'MOLIBDATO DE SODIO (99MO)||PERTECNETATO DE SODIO (99MTC)'
     → merge con id=3589 (mismo DCI, misma concentración 43 g)

  B) id=3443 (Technetium Tc 99M Generador, SIN_CONCENTRACION):
     DCI 'TECNECIO (99MTC)' incompleto para un generador Mo/Tc.
     El generador contiene Mo-99 (padre) → Tc-99m (hija = pertecnetato).
     Correcto: 'MOLIBDATO DE SODIO (99MO)||PERTECNETATO DE SODIO (99MTC)'
     → merge con id=3008 (mismo DCI, SIN_CONCENTRACION)

  C) id=3640 (Endolucinbeta Lu-177, 40 g/GBq):
     'LUTECIO (177LU)' → 'CLORURO DE LUTECIO (177LU)'
     Convención establecida en CLAUDE.md: CLORURO DE LUTECIO (177LU).
     id=3553 ya usa la forma canónica; id=3640 tiene concentración distinta
     (40 g vs SIN_CONCENTRACION) → no merge.
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"

MO_TC = "MOLIBDATO DE SODIO (99MO)||PERTECNETATO DE SODIO (99MTC)"


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

    # A. id=3615: NaCl||Tc → MOLIBDATO||PERTECNETATO
    print("\n=== A. id=3615 Ultra Technekow: NaCl||Tc -> Mo||Tc ===")
    n['A'] += rename_dci(con, 3615, MO_TC, {
        "CLORURO DE SODIO": "MOLIBDATO DE SODIO (99MO)",
        "TECNECIO (99MTC)": "PERTECNETATO DE SODIO (99MTC)",
    })

    # B. id=3443: TECNECIO (99MTC) → MOLIBDATO||PERTECNETATO
    print("\n=== B. id=3443 generador Tc: solo Tc -> Mo||Tc ===")
    n['B'] += rename_dci(con, 3443, MO_TC, {
        "TECNECIO (99MTC)": "MOLIBDATO DE SODIO (99MO)||PERTECNETATO DE SODIO (99MTC)",
    })

    # C. id=3640: LUTECIO (177LU) → CLORURO DE LUTECIO (177LU)
    print("\n=== C. id=3640 Lu-177: LUTECIO -> CLORURO DE LUTECIO ===")
    n['C'] += rename_dci(con, 3640, "CLORURO DE LUTECIO (177LU)", {
        "LUTECIO (177LU)": "CLORURO DE LUTECIO (177LU)",
    })

    # Post-fix auto-merge
    print("\n=== Post-fix auto-merge ===")
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
