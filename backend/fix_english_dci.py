"""
Fix English DCI names that should be Spanish INN:
- ZINC OXIDE -> OXIDO DE ZINC (merge with existing groups)
- SODIUM IODIDE I-131 -> YODURO DE SODIO (131I)
- PRAMOXINA||ZINC ACETATE/ZINC ACETATO -> ACETATO DE ZINC||PRAMOXINA
"""
import sqlite3
import json

DB_PATH = "farmavigia.db"


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


def merge_into(cur, drop_id: int, keep_id: int, new_key: str = None):
    cur.execute("SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (drop_id,))
    src = cur.fetchone()
    cur.execute("SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    tgt = cur.fetchone()
    if not src or not tgt:
        print(f"  SKIP: missing id={drop_id} or id={keep_id}")
        return
    src_ids = json.loads(src[1] or "[]")
    tgt_ids = json.loads(tgt[1] or "[]")
    union = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(union) - len(tgt_ids)
    if new_key:
        update_cum_dci(cur, src_ids, new_key)
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(union), len(union), keep_id),
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))
    print(f"  Merged id={drop_id} (n={src[2]}) into id={keep_id} (n={tgt[2]}) +{added}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. ZINC OXIDE -> OXIDO DE ZINC
    print("=== ZINC OXIDE -> OXIDO DE ZINC ===")

    # id=946 (10%) merge into id=945 (OXIDO DE ZINC TOPICO 10%)
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=946")
    row = cur.fetchone()
    if row:
        ids946 = json.loads(row[0] or "[]")
        update_cum_dci(cur, ids946, "OXIDO DE ZINC")
        merge_into(cur, 946, 945, "OXIDO DE ZINC")

    # id=1470 (25%) merge into id=1473 (OXIDO DE ZINC TOPICO 25%)
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=1470")
    row = cur.fetchone()
    if row:
        ids1470 = json.loads(row[0] or "[]")
        update_cum_dci(cur, ids1470, "OXIDO DE ZINC")
        merge_into(cur, 1470, 1473, "OXIDO DE ZINC")

    # id=2041 (40%) — no existing OXIDO DE ZINC 40% group, just rename
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=2041")
    row = cur.fetchone()
    if row:
        ids2041 = json.loads(row[0] or "[]")
        update_cum_dci(cur, ids2041, "OXIDO DE ZINC")
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key='OXIDO DE ZINC', actualizado_en=CURRENT_TIMESTAMP WHERE id=2041"
        )
        print("  Renamed id=2041 ZINC OXIDE -> OXIDO DE ZINC (no duplicate)")

    conn.commit()

    # 2. SODIUM IODIDE I-131 INYECTABLE -> YODURO DE SODIO (131I)
    print("\n=== SODIUM IODIDE I-131 INYECTABLE -> YODURO DE SODIO (131I) ===")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3598")
    row = cur.fetchone()
    if row:
        ids3598 = json.loads(row[0] or "[]")
        update_cum_dci(cur, ids3598, "YODURO DE SODIO (131I)")
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key='YODURO DE SODIO (131I)', actualizado_en=CURRENT_TIMESTAMP WHERE id=3598"
        )
        print("  Renamed id=3598 SODIUM IODIDE I-131 -> YODURO DE SODIO (131I)")
    conn.commit()

    # 3. PRAMOXINA + ZINC normalization -> ACETATO DE ZINC||PRAMOXINA
    print("\n=== PRAMOXINA + ZINC normalization ===")

    # id=3313: PRAMOXINA||ZINC, conc='1% + 0.1%' -> rename + fix conc order
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3313")
    row = cur.fetchone()
    if row:
        update_cum_dci(cur, json.loads(row[0] or "[]"), "ACETATO DE ZINC||PRAMOXINA")
    cur.execute(
        "UPDATE grupos_equivalencia SET dci_key='ACETATO DE ZINC||PRAMOXINA', concentracion_norm='0.1% + 1%', actualizado_en=CURRENT_TIMESTAMP WHERE id=3313"
    )
    print("  id=3313: PRAMOXINA||ZINC -> ACETATO DE ZINC||PRAMOXINA, conc '1%+0.1%' -> '0.1%+1%'")

    # id=3648: PRAMOXINA||ZINC ACETATE, conc='1% + 0.1%' -> rename + merge into 3313
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3648")
    row = cur.fetchone()
    if row:
        ids3648 = json.loads(row[0] or "[]")
        update_cum_dci(cur, ids3648, "ACETATO DE ZINC||PRAMOXINA")
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key='ACETATO DE ZINC||PRAMOXINA', concentracion_norm='0.1% + 1%', actualizado_en=CURRENT_TIMESTAMP WHERE id=3648"
        )
        merge_into(cur, 3648, 3313)

    # id=1640: PRAMOXINA||ZINC ACETATO, conc='0.1%' -> rename + fix conc
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=1640")
    row = cur.fetchone()
    if row:
        update_cum_dci(cur, json.loads(row[0] or "[]"), "ACETATO DE ZINC||PRAMOXINA")
    cur.execute(
        "UPDATE grupos_equivalencia SET dci_key='ACETATO DE ZINC||PRAMOXINA', concentracion_norm='0.1% + 1%', actualizado_en=CURRENT_TIMESTAMP WHERE id=1640"
    )
    print("  id=1640: PRAMOXINA||ZINC ACETATO -> ACETATO DE ZINC||PRAMOXINA, conc fixed to '0.1%+1%'")

    # Check if id=1640 is now duplicate with id=3313
    cur.execute("SELECT dci_key, grupo_via, concentracion_norm FROM grupos_equivalencia WHERE id=1640")
    r = cur.fetchone()
    if r:
        cur.execute(
            "SELECT id FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=? AND concentracion_norm=? AND id!=1640",
            (r[0], "TOPICO", r[2]),
        )
        dup = cur.fetchone()
        if dup:
            print(f"  id=1640 is now duplicate with id={dup[0]}, merging...")
            merge_into(cur, 1640, dup[0])

    conn.commit()

    # Final state
    print("\n=== Final OXIDO DE ZINC groups ===")
    cur.execute(
        "SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='OXIDO DE ZINC' ORDER BY concentracion_norm"
    )
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[1]:15s}  n={r[2]}")

    print("\n=== Final ACETATO DE ZINC||PRAMOXINA groups ===")
    cur.execute(
        "SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='ACETATO DE ZINC||PRAMOXINA'"
    )
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[1]:15s}  n={r[2]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
