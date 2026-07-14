"""
fix_auditoria_conc76.py — Septuagesimasexta ronda de auditoría.

Correcciones — estandarizar cualificador VIVO ATENUADO con paréntesis:

  Convención establecida en DB: calificadores de proceso entre paréntesis
  DESPUÉS del nombre base, igual que (INACTIVADO):
  - VIRUS DE LA HEPATITIS A (INACTIVADO) — id=3134 ✓
  - VIRUS DE LA RABIA (INACTIVADO) — id=2817 ✓ (ronda 75)
  - VIRUS DE LA FIEBRE AMARILLA (VIVO ATENUADO) — id=2891 ✓ (preexistente)

  A) id=3002 (MMR triple viral): ronda 74 creó forma SIN paréntesis; corregir:
     - VIRUS DE LA PAROTIDITIS VIVO ATENUADO -> VIRUS DE LA PAROTIDITIS (VIVO ATENUADO)
     - VIRUS DE LA RUBEOLA VIVO ATENUADO -> VIRUS DE LA RUBEOLA (VIVO ATENUADO)
     - VIRUS DEL SARAMPION VIVO ATENUADO -> VIRUS DEL SARAMPION (VIVO ATENUADO)
     sin merge: composición distinta a id=3507 (ProQuad incluye varicela y cepas)

  B) id=3528 (Varivax, varicela monovalente):
     - VIRUS VARICELA VIVO ATENUADO -> VIRUS DE LA VARICELA (VIVO ATENUADO)
     (agrega artículo 'DE LA' y paréntesis; distinto a id=3507 que usa CEPA OKA/MERCK)
     sin merge: id=3507 tiene dci_key diferente (incluye CEPA OKA/MERCK)
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"

NEW_DCI_3002 = (
    "VIRUS DE LA PAROTIDITIS (VIVO ATENUADO)||"
    "VIRUS DE LA RUBEOLA (VIVO ATENUADO)||"
    "VIRUS DEL SARAMPION (VIVO ATENUADO)"
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
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # -- A. id=3002 MMR: agregar paréntesis a VIVO ATENUADO ----------------------------
    print("\n=== A. id=3002 MMR: VIVO ATENUADO -> (VIVO ATENUADO) ===")
    n['A'] += rename_dci(con, 3002, NEW_DCI_3002, {
        "VIRUS DE LA PAROTIDITIS VIVO ATENUADO": "VIRUS DE LA PAROTIDITIS (VIVO ATENUADO)",
        "VIRUS DE LA RUBEOLA VIVO ATENUADO": "VIRUS DE LA RUBEOLA (VIVO ATENUADO)",
        "VIRUS DEL SARAMPION VIVO ATENUADO": "VIRUS DEL SARAMPION (VIVO ATENUADO)",
    })

    # -- B. id=3528 Varivax: agregar artículo y paréntesis ----------------------------
    print("\n=== B. id=3528 varicela: VIRUS VARICELA -> VIRUS DE LA VARICELA (VIVO ATENUADO) ===")
    n['B'] += rename_dci(con, 3528, "VIRUS DE LA VARICELA (VIVO ATENUADO)", {
        "VIRUS VARICELA VIVO ATENUADO": "VIRUS DE LA VARICELA (VIVO ATENUADO)",
    })

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
