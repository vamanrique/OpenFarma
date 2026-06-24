"""
fix_auditoria_conc60.py — Sexagesima ronda de auditoría.

Correcciones — typos de letras en combos y orden incorrecto:

  A) LUMENFANTRINA -> LUMEFANTRINA (typo: N extra; artemeter+lumefantrina = antimalárico):
     - id=1339: ARTEMETERO||LUMENFANTRINA SO 20mg+120mg (n=5) -> auto-merge id=1272 (n=4->9)

  B) SITAGLIPINA -> SITAGLIPTINA (typo: falta T; sitagliptin->sitagliptina DCI español):
     - id=2325: METFORMINA||SITAGLIPINA SO 850mg+50mg (n=2) -> auto-merge id=59 (n=22->24)

  C) MALICO ACIDO -> ACIDO MALICO (orden incorrecto; convención INN: ACIDO primero):
     - id=3112: combo amino acids IN 10% (n=1) -> sin merge (conc distinta a id=2328)
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
    n = {k: 0 for k in ['A', 'B', 'C', 'merge']}

    # -- A. LUMENFANTRINA -> LUMEFANTRINA (typo: N extra) ------------------------------
    print("\n=== A. LUMENFANTRINA -> LUMEFANTRINA ===")
    n['A'] += rename_dci(con, 1339, "ARTEMETERO||LUMEFANTRINA",
                         {"LUMENFANTRINA": "LUMEFANTRINA"})

    # -- B. SITAGLIPINA -> SITAGLIPTINA (typo: falta T) --------------------------------
    print("\n=== B. SITAGLIPINA -> SITAGLIPTINA ===")
    n['B'] += rename_dci(con, 2325, "METFORMINA||SITAGLIPTINA",
                         {"SITAGLIPINA": "SITAGLIPTINA"})

    # -- C. MALICO ACIDO -> ACIDO MALICO (orden incorrecto) ----------------------------
    print("\n=== C. MALICO ACIDO -> ACIDO MALICO ===")
    new_dci_3112 = ("ACIDO MALICO||ALANINA||ARGININA||CISTEINA||FENILALANINA||GLICINA||"
                    "HISTIDINA||ISOLEUCINA||LEUCINA||LISINA||METIONINA||PROLINA||SERINA||"
                    "TAURINA||TIROSINA||TREONINA||TRIPTOFANO||VALINA")
    n['C'] += rename_dci(con, 3112, new_dci_3112, {"MALICO ACIDO": "ACIDO MALICO"})

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
