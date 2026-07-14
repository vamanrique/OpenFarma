"""
fix_auditoria_conc86.py — Octogesimosexta ronda de auditoría.

Correcciones de concentracion_norm por errores de parseo en el ETL:

  A) id=3275 (DESMOPRESINA, Minirin Melt):
     concentracion_norm='0.1 mg' → '0.12 mg'
     Minirin Melt 120 μg = 0.12 mg. El ETL redondeó 0.12 a 0.1 al normalizar.
     componentes.dosis_mg = 0.12 confirma la dosis real.
     Sin merge: no existe grupo DESMOPRESINA | 0.12 mg | SOLIDO_ORAL.

  B) id=2152 (VALACICLOVIR, Valtrois):
     concentracion_norm='1 mg' → '1000 mg'
     Valtrois (Lab. Farma, Colombia) = valaciclovir 1000 mg tabletas.
     El ETL almacenó dosis_mg=1.0 en lugar de 1000.0 — error de parseo:
     "1 g" fue tratado como "1 mg" en lugar de convertirlo a "1000 mg".
     → auto-merge con id=1422 (VALACICLOVIR | 1000 mg | SOLIDO_ORAL, 68 productos)
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


def fix_conc(con, gid: int, old_conc: str, new_conc: str) -> int:
    cur = con.cursor()
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya] id={gid}: {new_conc}")
        return 0
    if row[0] != old_conc:
        print(f"  [WARN] id={gid}: esperado '{old_conc}', encontrado '{row[0]}'")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [CONC] id={gid}: '{old_conc}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # A. id=3275: DESMOPRESINA 0.1 mg → 0.12 mg
    print("\n=== A. id=3275 Minirin Melt: DESMOPRESINA 0.1 mg -> 0.12 mg ===")
    n['A'] += fix_conc(con, 3275, "0.1 mg", "0.12 mg")

    # B. id=2152: VALACICLOVIR 1 mg → 1000 mg
    print("\n=== B. id=2152 Valtrois: VALACICLOVIR 1 mg -> 1000 mg ===")
    n['B'] += fix_conc(con, 2152, "1 mg", "1000 mg")

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
