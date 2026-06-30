"""
Rename English INN drug names to Spanish INN and merge into existing Spanish groups.
Also fix AVANTIUM brand-name misclassification -> DEFLAZACORT.

Merges:
- FINASTERIDE id=1682 (5mg) -> FINASTERIDA id=1052 (5mg)
- LEVOSULPIRIDE||PANCREATINA||SIMETICONA id=1443 -> LEVOSULPIRIDA||PANCREATINA||SIMETICONA id=1448
- LOMITAPIDE id=2584 (10mg) -> LOMITAPIDA id=2387
- LOMITAPIDE id=1753 (20mg) -> LOMITAPIDA id=2386
- LOMITAPIDE id=1896 (5mg) -> LOMITAPIDA id=2388
- LUBIPROSTONE id=1453 (0mg) -> LUBIPROSTONA id=1621 (0mg)
- MEPIVACAINE id=783 (30mg/mL) -> MEPIVACAINA id=781 (30mg/mL)
- NAFAZOLINE id=3438 (0.001mg/mL) -> NAFAZOLINA (rename only, different conc from id=3060)
- POVIDONE IODINE id=782 (0.8%) -> POVIDONA YODADA id=268 (0.8%)
- SUCRALFATE id=316 (1000mg) -> SUCRALFATO id=185 (1000mg)
- AVANTIUM id=3893 (brand=DEFLAZACORT 30mg) -> DEFLAZACORT id=800 (30mg)
"""
import sqlite3
import json

DB_PATH = "farmavigia.db"

MERGES = [
    # (drop_id, keep_id, new_key_for_drop_products)
    (1682, 1052, "FINASTERIDA"),
    (1443, 1448, "LEVOSULPIRIDA||PANCREATINA||SIMETICONA"),
    (2584, 2387, "LOMITAPIDA"),
    (1753, 2386, "LOMITAPIDA"),
    (1896, 2388, "LOMITAPIDA"),
    (1453, 1621, "LUBIPROSTONA"),
    (783,  781,  "MEPIVACAINA"),
    (782,  268,  "POVIDONA YODADA"),
    (316,  185,  "SUCRALFATO"),
    (3893, 800,  "DEFLAZACORT"),
]

RENAME_ONLY = [
    # (gid, new_key)
    (3438, "NAFAZOLINA"),
]


def fix_cum_dci(cur, cum_ids: list, new_key: str):
    parts = new_key.split("||")
    for cid in cum_ids:
        if "-" not in cid:
            continue
        exp, consec = cid.split("-", 1)
        cur.execute(
            "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
            (json.dumps(parts, ensure_ascii=False), exp, consec),
        )


def merge_into(cur, drop_id: int, keep_id: int, new_key: str):
    cur.execute("SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (drop_id,))
    src = cur.fetchone()
    cur.execute("SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    tgt = cur.fetchone()
    if not src:
        print(f"  SKIP: id={drop_id} not found")
        return
    if not tgt:
        print(f"  SKIP: id={keep_id} not found")
        return

    src_ids = json.loads(src[1] or "[]")
    tgt_ids = json.loads(tgt[1] or "[]")
    fix_cum_dci(cur, src_ids, new_key)
    union = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(union) - len(tgt_ids)
    print(f"  Merge id={drop_id} '{src[0]}' (n={src[2]}) -> id={keep_id} '{tgt[0]}' (n={tgt[2]}) +{added}")
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(union), len(union), keep_id),
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for drop_id, keep_id, new_key in MERGES:
        merge_into(cur, drop_id, keep_id, new_key)

    conn.commit()

    for gid, new_key in RENAME_ONLY:
        cur.execute("SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if not row:
            print(f"  SKIP rename: id={gid} not found")
            continue
        old_key, cum_ids_json, n = row
        cum_ids = json.loads(cum_ids_json or "[]")
        fix_cum_dci(cur, cum_ids, new_key)
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (new_key, gid),
        )
        print(f"  Renamed id={gid}: '{old_key}' -> '{new_key}'")

    conn.commit()

    print()
    print("=== Final state of renamed drugs ===")
    for key in ["FINASTERIDA", "LEVOSULPIRIDA||PANCREATINA||SIMETICONA",
                "LOMITAPIDA", "LUBIPROSTONA", "MEPIVACAINA",
                "NAFAZOLINA", "POVIDONA YODADA", "SUCRALFATO", "DEFLAZACORT"]:
        cur.execute(
            "SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key=? ORDER BY concentracion_norm",
            (key,),
        )
        rows = cur.fetchall()
        if rows:
            print(f"  {key}: {[(r[0], r[1], r[2]) for r in rows]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
