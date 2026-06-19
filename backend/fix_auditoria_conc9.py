"""
fix_auditoria_conc9.py — Novena ronda de auditoría.

Correcciones:
  A) LEVOTIROXINA: mg -> mcg (convención universal para hormona tiroidea)
     - id=266: "0.1 mg" -> "100 mcg" (n=559)
     - id=737: "0.025 mg" -> "25 mcg" (n=98)
     - id=1466: "0.2 mg" -> "200 mcg" (n=71)
     - id=849: "0.125 mg" -> "125 mcg" (n=30)
  B) LUBIPROSTONA: mg -> mcg (Amitiza standard en mcg)
     - id=3913: "0.024 mg" -> "24 mcg"
     - id=1621: "0.008 mg" -> "8 mcg"
  C) PARICALCITOL: mg -> mcg (vitamina D activa análogo, standard mcg)
     - id=722: "0.005 mg/mL" -> "5 mcg/mL" (inyectable)
     - id=1127: "0.001 mg" -> "1 mcg"
     - id=3914: "0.002 mg" -> "2 mcg"
  D) ACIDO SALICILICO id=846: TRANSDERMICO "0.04 mg" -> TOPICO "40%"
     (Hansaplast apósito callos: salicílico 40% tópico, no sistémico)
  E) Post-fix auto-merge duplicados
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP merge] {del_id}->{keep_id}: missing")
        return 0
    merged = list(dict.fromkeys(
        json.loads(keep[0] or '[]') + json.loads(rem[0] or '[]')
    ))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}->{keep_id}: total={len(merged)}")
    return 1


def fix_conc(cur, gid: int, new_conc: str, tag: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{row[0]}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. LEVOTIROXINA: mg -> mcg -----------------------------------------------
    print("\n=== A. LEVOTIROXINA mg -> mcg ===")
    fixes = [
        (266,  "100 mcg"),
        (737,  "25 mcg"),
        (1466, "200 mcg"),
        (849,  "125 mcg"),
    ]
    for gid, new_conc in fixes:
        n['A'] += fix_conc(cur, gid, new_conc, "A_levotiroxina")

    # -- B. LUBIPROSTONA: mg -> mcg -----------------------------------------------
    print("\n=== B. LUBIPROSTONA mg -> mcg ===")
    n['B'] += fix_conc(cur, 3913, "24 mcg", "B_lubiprostona_24")
    n['B'] += fix_conc(cur, 1621, "8 mcg",  "B_lubiprostona_8")

    # -- C. PARICALCITOL: mg -> mcg -----------------------------------------------
    print("\n=== C. PARICALCITOL mg -> mcg ===")
    n['C'] += fix_conc(cur, 722,  "5 mcg/mL", "C_paricalcitol_inj")
    n['C'] += fix_conc(cur, 1127, "1 mcg",    "C_paricalcitol_1")
    n['C'] += fix_conc(cur, 3914, "2 mcg",    "C_paricalcitol_2")

    # -- D. ACIDO SALICILICO id=846: TRANSDERMICO -> TOPICO 40% ------------------
    print("\n=== D. ACIDO SALICILICO corn plasters ===")
    cur.execute("SELECT grupo_via, concentracion_norm FROM grupos_equivalencia WHERE id=846")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET grupo_via='TOPICO', concentracion_norm='40%'
            WHERE id=846
        """)
        print(f"  [D] id=846: via '{row[0]}'->'TOPICO', conc '{row[1]}'->'40%'")
        n['D'] += 1

    # -- E. Post-fix auto-merge duplicados ----------------------------------------
    print("\n=== E. Post-fix auto-merge ===")
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

    # -- Fix n_productos ----------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen ------------------------------------------------------------------
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
