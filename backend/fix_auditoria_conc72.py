"""
fix_auditoria_conc72.py — Septuagesimasegunda ronda de auditoría.

Correcciones — nombres de componentes vacunales inconsistentes:

  A) id=2969 (Twinrix HepA+HepB):
     - ANTIGENO HEPATITIS A -> VIRUS DE LA HEPATITIS A (INACTIVADO)
       (canónica establecida en ronda 69 y usada en id=3134)
     - ANTIGENO HEPATITIS B -> ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B
       (canónica establecida en ronda 69)
     nuevo dci_key: ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B||VIRUS DE LA HEPATITIS A (INACTIVADO)

  B) id=3510 (hexavalente Hexaxim/similar):
     - BORDETELLA PERTUSSIS HEMAGLUTININA FILAMENTOSA -> HEMAGLUTININA FILAMENTOSA
       (prefijo género incorrecto; id=3053 y id=3046 usan solo HEMAGLUTININA FILAMENTOSA)
     - BORDETELLA PERTUSSIS TOXOIDE PERTUSICO -> TOXOIDE PERTUSICO
       (mismo criterio; TOXOIDE PERTUSICO es el INN del componente)
     - HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO -> POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B
       (orden inverso y falta "CAPSULAR DE"; forma canónica de id=3053)
     sin merge: diferente composición a id=3053 (sin PERTACTINA; Hexaxim vs Infanrix Hexa)

  C) id=3107 (DTP+IPV inyectable):
     - VIRUS POLIOMIELITIS TIPO 1/2/3 -> POLIOVIRUS INACTIVADO TIPO 1/2/3
       (convención establecida en ronda 65; producto INYECTABLE → inactivado)
     sin merge: tiene toxoides DTP pero no HepB/Hib -> distinto a otros grupos hexavalentes
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"

NEW_DCI_2969 = "ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B||VIRUS DE LA HEPATITIS A (INACTIVADO)"

NEW_DCI_3510 = (
    "ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B||HEMAGLUTININA FILAMENTOSA||"
    "POLIOVIRUS INACTIVADO TIPO 1||POLIOVIRUS INACTIVADO TIPO 2||POLIOVIRUS INACTIVADO TIPO 3||"
    "POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B||"
    "TOXOIDE DIFTERICO||TOXOIDE PERTUSICO||TOXOIDE TETANICO"
)

NEW_DCI_3107 = (
    "POLIOVIRUS INACTIVADO TIPO 1||POLIOVIRUS INACTIVADO TIPO 2||POLIOVIRUS INACTIVADO TIPO 3||"
    "TOXOIDE DIFTERICO||TOXOIDE PERTUSICO||TOXOIDE TETANICO"
)


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

    # -- A. id=2969 HepA+HepB combo -> formas canónicas -----------------------------------
    print("\n=== A. ANTIGENO HEPATITIS A/B -> formas canónicas (id=2969) ===")
    n['A'] += rename_dci(con, 2969, NEW_DCI_2969, {
        "ANTIGENO HEPATITIS A": "VIRUS DE LA HEPATITIS A (INACTIVADO)",
        "ANTIGENO HEPATITIS B": "ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B",
    })

    # -- B. id=3510 hexavalente -> fix prefijos y orden componentes -----------------------
    print("\n=== B. id=3510 hexavalente: drop prefijo BP, fix Hib ===")
    n['B'] += rename_dci(con, 3510, NEW_DCI_3510, {
        "BORDETELLA PERTUSSIS HEMAGLUTININA FILAMENTOSA": "HEMAGLUTININA FILAMENTOSA",
        "BORDETELLA PERTUSSIS TOXOIDE PERTUSICO": "TOXOIDE PERTUSICO",
        "HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO": "POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B",
    })

    # -- C. id=3107 DTP+IPV: VIRUS POLIOMIELITIS -> POLIOVIRUS INACTIVADO -----------------
    print("\n=== C. VIRUS POLIOMIELITIS TIPO X -> POLIOVIRUS INACTIVADO TIPO X (id=3107) ===")
    n['C'] += rename_dci(con, 3107, NEW_DCI_3107, {
        "VIRUS POLIOMIELITIS TIPO 1": "POLIOVIRUS INACTIVADO TIPO 1",
        "VIRUS POLIOMIELITIS TIPO 2": "POLIOVIRUS INACTIVADO TIPO 2",
        "VIRUS POLIOMIELITIS TIPO 3": "POLIOVIRUS INACTIVADO TIPO 3",
    })

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
