"""
fix_auditoria_conc10.py — Décima ronda de auditoría.

Correcciones:
  A) ROTIGOTINA TRANSDERMICO: delivery rate -> contenido total del parche
     - id=1406: "4 mg" (tasa entrega) -> "9 mg" (total) -> merge id=1408 (Neupro 4mg/24h)
     - id=1404: "8 mg" (tasa entrega) -> "18 mg" (total) -> merge id=1403 (Neupro 8mg/24h)
     - id=1405: "6 mg" (tasa entrega) -> "13.5 mg" (total, Neupro 6mg/24h = 30cm²)
  B) ACETILCOLINA id=244: grupo_via OTICO -> OFTALMICO
     (Miochol-E es solución intraocular, ETL normalizó intraocular como OTICO incorrectamente)
  C) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # -- A. ROTIGOTINA: tasa -> contenido total ----------------------------------
    print("\n=== A. ROTIGOTINA delivery rate -> total patch content ===")
    # id=1406 "4 mg" = Neupro 4mg/24h delivery rate -> "9 mg" total (20cm^2 patch)
    n['A'] += fix_conc(cur, 1406, "9 mg", "A_rotigotina_4->9")
    n['merge'] += merge_into(con, 1408, 1406)

    # id=1404 "8 mg" = Neupro 8mg/24h delivery rate -> "18 mg" total (40cm^2 patch)
    n['A'] += fix_conc(cur, 1404, "18 mg", "A_rotigotina_8->18")
    n['merge'] += merge_into(con, 1403, 1404)

    # id=1405 "6 mg" = Neupro 6mg/24h delivery rate -> "13.5 mg" total (30cm^2 patch)
    n['A'] += fix_conc(cur, 1405, "13.5 mg", "A_rotigotina_6->13.5")

    # -- B. ACETILCOLINA id=244: OTICO -> OFTALMICO ------------------------------
    print("\n=== B. ACETILCOLINA via OTICO -> OFTALMICO ===")
    cur.execute("SELECT grupo_via FROM grupos_equivalencia WHERE id=244")
    row = cur.fetchone()
    if row and row[0] != 'OFTALMICO':
        cur.execute("UPDATE grupos_equivalencia SET grupo_via='OFTALMICO' WHERE id=244")
        print(f"  [B] id=244: via '{row[0]}' -> 'OFTALMICO'")
        n['B'] += 1

    # -- C. Post-fix auto-merge --------------------------------------------------
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
