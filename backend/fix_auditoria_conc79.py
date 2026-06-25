"""
fix_auditoria_conc79.py — Septuagesimanona ronda de auditoría.

Correcciones:

  A) id=3539 (Gardasil 9, nonavalente VPH):
     Inconsistencia de formato vs id=3238 (Gardasil 4 tetravalente).
     id=3238 usa 'PROTEINA L1 VPH TIPO X' (con espacio y TIPO);
     id=3539 usa 'PROTEINA L1VPH X' (sin espacio, sin TIPO). Unificar:
     - PROTEINA L1VPH 6  -> PROTEINA L1 VPH TIPO 6
     - PROTEINA L1VPH 11 -> PROTEINA L1 VPH TIPO 11
     - PROTEINA L1VPH 16 -> PROTEINA L1 VPH TIPO 16
     - PROTEINA L1VPH 18 -> PROTEINA L1 VPH TIPO 18
     - PROTEINA L1VPH 31 -> PROTEINA L1 VPH TIPO 31
     - PROTEINA L1VPH 33 -> PROTEINA L1 VPH TIPO 33
     - PROTEINA L1VPH 45 -> PROTEINA L1 VPH TIPO 45
     - PROTEINA L1VPH 52 -> PROTEINA L1 VPH TIPO 52
     - PROTEINA L1VPH 58 -> PROTEINA L1 VPH TIPO 58
     sin merge: 9 tipos vs 4 tipos de Gardasil 4 (distintos grupos legítimos).

  B) id=3053 (Infanrix Hexa, hexavalente):
     'ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B RECOMBINANTE'
     -> 'ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B'
     RECOMBINANTE no es parte del INN OMS; toda HBsAg vacunal es recombinante.
     id=3510 (Hexaxim) y id=3513 (monovalente) ya usan la forma sin RECOMBINANTE.
     sin merge: id=3053 tiene PERTACTINA que id=3510 no tiene.
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"

_HPV9_TYPES = [6, 11, 16, 18, 31, 33, 45, 52, 58]

NEW_DCI_3539 = "||".join(sorted(
    f"PROTEINA L1 VPH TIPO {t}" for t in _HPV9_TYPES
))

SYNC_3539 = {f"PROTEINA L1VPH {t}": f"PROTEINA L1 VPH TIPO {t}" for t in _HPV9_TYPES}

NEW_DCI_3053 = (
    "ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B||"
    "HEMAGLUTININA FILAMENTOSA||PERTACTINA||"
    "POLIOVIRUS INACTIVADO TIPO 1||POLIOVIRUS INACTIVADO TIPO 2||POLIOVIRUS INACTIVADO TIPO 3||"
    "POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B||"
    "TOXOIDE DIFTERICO||TOXOIDE PERTUSICO||TOXOIDE TETANICO"
)

SYNC_3053 = {
    "ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B RECOMBINANTE":
    "ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B",
}


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

    # -- A. id=3539 Gardasil 9: L1VPH -> L1 VPH TIPO ---------------------------------
    print("\n=== A. id=3539 Gardasil 9: PROTEINA L1VPH -> PROTEINA L1 VPH TIPO ===")
    n['A'] += rename_dci(con, 3539, NEW_DCI_3539, SYNC_3539)

    # -- B. id=3053 Infanrix Hexa: drop RECOMBINANTE de HBsAg -------------------------
    print("\n=== B. id=3053 Infanrix Hexa: HBsAg sin RECOMBINANTE ===")
    n['B'] += rename_dci(con, 3053, NEW_DCI_3053, SYNC_3053)

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
