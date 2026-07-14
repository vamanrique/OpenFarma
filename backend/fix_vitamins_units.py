"""
Fix two vitamin unit/classification bugs:

1. ACIDO ASCORBICO id=975 (50000 UI) — 4 products "Vitamina A Capsulas"
   are actually RETINOL (Vitamin A), not Vitamin C.
   Fix: update principios_dci/componentes, move to id=976 (RETINOL 50000 UI), delete id=975.

2. TOCOFEROL id=583 (400 mg) and id=2282 (800 mg) — CUM stores UI as numeric mg.
   Products named "Aquasol E400 U.I", "Vitamina E 800 Ui" confirm these are IU.
   Fix: update concentracion_norm, merge into id=2874 (400 UI) and id=2873 (800 UI).
"""
import sqlite3
import json

DB_PATH = "openfarma.db"


def merge_into(cur, drop_id: int, keep_id: int):
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (drop_id,))
    src = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    tgt = cur.fetchone()
    if not src or not tgt:
        print(f"  SKIP: drop_id={drop_id} or keep_id={keep_id} not found")
        return

    src_ids = json.loads(src[0]) if src[0] else []
    tgt_ids = json.loads(tgt[0]) if tgt[0] else []
    union = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(union) - len(tgt_ids)
    print(f"  Merge id={drop_id} (n={src[1]}) -> id={keep_id} (n={tgt[1]}) +{added} products")

    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(union), len(union), keep_id)
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── Fix 1: ACIDO ASCORBICO id=975 → RETINOL id=976 ──────────────────────
    print("=== Fix 1: ACIDO ASCORBICO 50000 UI (id=975) -> RETINOL (id=976) ===")

    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=975")
    row = cur.fetchone()
    if not row:
        print("  id=975 not found, skipping")
    else:
        cum_ids_975 = json.loads(row[0]) if row[0] else []
        print(f"  Products to move: {cum_ids_975}")

        for cid in cum_ids_975:
            if '-' not in cid:
                continue
            exp, consec = cid.split('-', 1)

            # Fix principios_dci
            cur.execute(
                "SELECT principios_dci, componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                (exp, consec)
            )
            prod = cur.fetchone()
            if not prod:
                print(f"  WARNING: {cid} not found in cum_normalizado")
                continue

            old_dci = prod[0]
            old_comps = prod[1]

            new_dci = json.dumps(["RETINOL"], ensure_ascii=False)

            # Fix componentes: replace ACIDO ASCORBICO → RETINOL
            new_comps = old_comps
            if old_comps:
                try:
                    comps = json.loads(old_comps)
                    for c in comps:
                        if c.get('dci', '').upper() == 'ACIDO ASCORBICO':
                            c['dci'] = 'RETINOL'
                    new_comps = json.dumps(comps, ensure_ascii=False)
                except Exception:
                    pass

            print(f"  {cid}: dci {old_dci} -> {new_dci}")
            cur.execute(
                "UPDATE cum_normalizado SET principios_dci=?, componentes=? WHERE expediente_cum=? AND consecutivo_cum=?",
                (new_dci, new_comps, exp, consec)
            )

        # Merge id=975 into id=976
        merge_into(cur, drop_id=975, keep_id=976)

    conn.commit()

    # ── Fix 2a: TOCOFEROL id=583 (400 mg) → 400 UI → merge into id=2874 ─────
    print("\n=== Fix 2a: TOCOFEROL id=583 (400 mg) -> 400 UI -> merge id=2874 ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='400 UI', actualizado_en=CURRENT_TIMESTAMP WHERE id=583"
    )
    print("  Updated concentracion_norm: '400 mg' -> '400 UI'")
    merge_into(cur, drop_id=583, keep_id=2874)
    conn.commit()

    # ── Fix 2b: TOCOFEROL id=2282 (800 mg) → 800 UI → merge into id=2873 ────
    print("\n=== Fix 2b: TOCOFEROL id=2282 (800 mg) -> 800 UI -> merge id=2873 ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='800 UI', actualizado_en=CURRENT_TIMESTAMP WHERE id=2282"
    )
    print("  Updated concentracion_norm: '800 mg' -> '800 UI'")
    merge_into(cur, drop_id=2282, keep_id=2873)
    conn.commit()

    # ── Final state ───────────────────────────────────────────────────────────
    print("\n=== Final RETINOL groups ===")
    cur.execute(
        "SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='RETINOL' ORDER BY concentracion_norm"
    )
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[1]:15s}  n={r[2]}")

    print("\n=== Final TOCOFEROL groups ===")
    cur.execute(
        "SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='TOCOFEROL' ORDER BY concentracion_norm"
    )
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[1]:15s}  n={r[2]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
