"""
Fix incorrect salt/compound word order in dci_key:
- CALCIO GLUCONATO -> GLUCONATO DE CALCIO
- CALCIO LEVULINATO -> LEVULINATO DE CALCIO
- ALUMINIO ACETATO -> ACETATO DE ALUMINIO
- ALUMINIO SUBACETATO -> SUBACETATO DE ALUMINIO
- BARIO SULFATO -> SULFATO DE BARIO
- CLORHEXIDINA GLUCONATO -> CLORHEXIDINA (gluconate is a salt suffix)
- SODIO ACETATO -> ACETATO DE SODIO

Note: CONDROITINA SULFATO, GLUCOSAMINA SULFATO are correct INN forms (no change).
"""
import sqlite3
import json

DB_PATH = "farmavigia.db"

# Substitution map: old_fragment -> new_fragment
RENAMES = {
    "CALCIO GLUCONATO": "GLUCONATO DE CALCIO",
    "CALCIO LEVULINATO": "LEVULINATO DE CALCIO",
    "ALUMINIO ACETATO": "ACETATO DE ALUMINIO",
    "ALUMINIO SUBACETATO": "SUBACETATO DE ALUMINIO",
    "BARIO SULFATO": "SULFATO DE BARIO",
    "CLORHEXIDINA GLUCONATO": "CLORHEXIDINA",
    "SODIO ACETATO": "ACETATO DE SODIO",
}


def rebuild_key(old_key: str) -> str:
    parts = old_key.split("||")
    new_parts = []
    for p in parts:
        new_p = RENAMES.get(p, p)
        new_parts.append(new_p)
    return "||".join(sorted(new_parts))


def update_cum_dci(cur, cum_ids: list, new_key: str):
    parts = new_key.split("||")
    for cid in cum_ids:
        if "-" not in cid:
            continue
        exp, consec = cid.split("-", 1)
        cur.execute(
            "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
            (json.dumps(parts, ensure_ascii=False), exp, consec),
        )


def merge_into(cur, drop_id: int, keep_id: int):
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (drop_id,))
    src = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    tgt = cur.fetchone()
    if not src or not tgt:
        return
    src_ids = json.loads(src[0] or "[]")
    tgt_ids = json.loads(tgt[0] or "[]")
    union = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(union) - len(tgt_ids)
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(union), len(union), keep_id),
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))
    print(f"  Merged id={drop_id} (n={src[1]}) -> id={keep_id} (n={tgt[1]}) +{added}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Find all groups containing any of the old fragments
    cur.execute("SELECT id, dci_key, grupo_via, concentracion_norm, n_productos, cum_ids FROM grupos_equivalencia")
    rows = cur.fetchall()

    fixed = 0
    for gid, old_key, via, conc, n_prods, cum_ids_json in rows:
        needs_fix = any(old in old_key for old in RENAMES)
        if not needs_fix:
            continue

        new_key = rebuild_key(old_key)
        if new_key == old_key:
            continue

        cum_ids = json.loads(cum_ids_json or "[]")
        update_cum_dci(cur, cum_ids, new_key)
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (new_key, gid),
        )
        print(f"  id={gid:5d}  {old_key[:50]!r}")
        print(f"         -> {new_key[:50]!r}")
        fixed += 1

    conn.commit()
    print(f"\nRenamed {fixed} groups")

    # Find resulting duplicates
    print("\n=== Finding duplicates after rename ===")
    cur.execute("""
        SELECT g1.id, g1.dci_key, g1.concentracion_norm, g1.n_productos,
               g2.id, g2.n_productos
        FROM grupos_equivalencia g1
        JOIN grupos_equivalencia g2
          ON g1.dci_key = g2.dci_key
         AND g1.grupo_via = g2.grupo_via
         AND g1.concentracion_norm = g2.concentracion_norm
         AND g1.id < g2.id
        ORDER BY g1.dci_key
    """)
    dupes = cur.fetchall()
    print(f"Found {len(dupes)} duplicate pairs")

    merged = 0
    processed: set = set()
    for g1id, dci_key, conc, n1, g2id, n2 in dupes:
        if g1id in processed or g2id in processed:
            continue
        keep_id, drop_id = (g1id, g2id) if n1 >= n2 else (g2id, g1id)
        print(f"  Merging dupe: {dci_key!r} {conc!r}")
        merge_into(cur, drop_id, keep_id)
        processed.add(g1id)
        processed.add(g2id)
        merged += 1

    conn.commit()
    print(f"Merged {merged} duplicates")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
