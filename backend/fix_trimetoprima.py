"""
Fix TRIMETOPRIMA → TRIMETOPRIM synonym in grupos_equivalencia and cum_normalizado.
TRIMETOPRIMA is a Spanish variant suffix; TRIMETOPRIM is the INN canonical form.
"""
import sqlite3
import json

DB_PATH = "farmavigia.db"


def rebuild_dci_key(old_key: str) -> str:
    parts = [p.replace("TRIMETOPRIMA", "TRIMETOPRIM") for p in old_key.split("||")]
    return "||".join(sorted(parts))


def merge_groups(cur, source_id: int, target_id: int):
    cur.execute("SELECT cum_ids, n_productos, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (source_id,))
    src = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (target_id,))
    tgt = cur.fetchone()
    if not src or not tgt:
        print(f"  SKIP: src={source_id} or tgt={target_id} not found")
        return 0
    src_ids = json.loads(src[0]) if src[0] else []
    tgt_ids = json.loads(tgt[0]) if tgt[0] else []
    merged = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(merged) - len(tgt_ids)
    print(f"  Merge id={source_id} (n={src[1]}, {src[3]!r}) -> id={target_id} (n={tgt[1]}, {tgt[3]!r}) +{added}")
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(merged), len(merged), target_id)
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (source_id,))
    return added


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Step 1: Rename dci_key in grupos_equivalencia
    cur.execute("""
        SELECT id, dci_key FROM grupos_equivalencia
        WHERE dci_key LIKE '%TRIMETOPRIMA%'
    """)
    rows = cur.fetchall()
    print(f"Found {len(rows)} grupos_equivalencia rows with TRIMETOPRIMA")
    renamed = 0
    for gid, old_key in rows:
        new_key = rebuild_dci_key(old_key)
        if new_key != old_key:
            print(f"  id={gid:5d}  {old_key} -> {new_key}")
            cur.execute(
                "UPDATE grupos_equivalencia SET dci_key=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                (new_key, gid)
            )
            renamed += 1
    print(f"Renamed {renamed} grupos_equivalencia rows")
    conn.commit()

    # Step 2: Fix cum_normalizado.principios_dci
    cur.execute("""
        SELECT expediente_cum, consecutivo_cum, principios_dci FROM cum_normalizado
        WHERE principios_dci LIKE '%TRIMETOPRIMA%'
    """)
    cum_rows = cur.fetchall()
    print(f"\nFound {len(cum_rows)} cum_normalizado rows with TRIMETOPRIMA")
    cum_fixed = 0
    for exp, consec, old_val in cum_rows:
        new_val = old_val.replace("TRIMETOPRIMA", "TRIMETOPRIM")
        if new_val != old_val:
            cur.execute(
                "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                (new_val, exp, consec)
            )
            cum_fixed += 1
    print(f"Fixed {cum_fixed} cum_normalizado rows")
    conn.commit()

    # Step 3: Find and merge resulting duplicates
    print("\n=== Finding duplicates after rename ===")
    cur.execute("""
        SELECT g1.id, g1.dci_key, g1.concentracion_norm, g1.n_productos,
               g2.id, g2.n_productos
        FROM grupos_equivalencia g1
        JOIN grupos_equivalencia g2
          ON g1.dci_key=g2.dci_key
         AND g1.grupo_via=g2.grupo_via
         AND g1.concentracion_norm=g2.concentracion_norm
         AND g1.id < g2.id
        ORDER BY g1.dci_key, g1.concentracion_norm
    """)
    dupes = cur.fetchall()
    print(f"Found {len(dupes)} duplicate pairs")
    merged_count = 0
    processed: set[int] = set()
    for g1id, dci_key, conc, n1, g2id, n2 in dupes:
        if g1id in processed or g2id in processed:
            continue
        if n1 >= n2:
            keep_id, drop_id = g1id, g2id
        else:
            keep_id, drop_id = g2id, g1id
        merge_groups(cur, drop_id, keep_id)
        processed.add(g1id)
        processed.add(g2id)
        merged_count += 1
    conn.commit()
    print(f"Merged {merged_count} pairs")

    # Final state
    print("\n=== Final SULFAMETOXAZOL||TRIMETOPRIM groups ===")
    cur.execute("""
        SELECT id, grupo_via, concentracion_norm, n_productos
        FROM grupos_equivalencia
        WHERE dci_key='SULFAMETOXAZOL||TRIMETOPRIM'
        ORDER BY grupo_via, concentracion_norm
    """)
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  via={r[1]:15s}  conc={r[2]:25s}  n={r[3]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    total = cur.fetchone()[0]
    print(f"\nTotal grupos_equivalencia: {total}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
