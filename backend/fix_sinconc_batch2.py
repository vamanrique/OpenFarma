"""
Second batch of SIN_CONCENTRACION and format fixes:

1.  id=3793 METRONIDAZOL||NIFUROXAZIDA SIN_CONC -> id=22 '600 mg + 200 mg'
2.  id=2990 CARBOXIMETILCELULOSA SODICA OFTALMICO SIN_CONC -> id=2993 '5 mg/mL'
3.  id=3166 ENOXAPARINA INYECTABLE SIN_CONC -> id=306 '100 mg/mL'
4.  id=2619 AMOXICILINA||SULBACTAM LIQUIDO_ORAL SIN_CONC -> id=3867 '200 mg/5 mL'
5.  id=3348 CLINDAMICINA||CLOTRIMAZOL VAGINAL SIN_CONC -> id=1264 '100 mg + 200 mg' (Vagylin)
6.  id=3798 ACIDO CLAVULANICO||AMOXICILINA '500 mg' -> id=33 '125 mg + 500 mg' (Clavulin 500)
7.  id=3835 CEFALEXINA SOLIDO_ORAL SIN_CONC -> id=120 '500 mg' (Cimotar)
8.  id=3828 AMPICILINA LIQUIDO_ORAL '250 mg/5 mL' -> id=2662 '50 mg/mL' (equiv conc)
9.  id=3605 fix concentracion_norm format -> '1 mg + 75 mg + 20 mg + 50 mg + 100 mg'
10. id=3529 DIMETICONA||MAGALDRATO SIN_CONC -> '80 mg + 800 mg' (Riopan Gel confirmed)
"""
import sqlite3
import json

DB_PATH = "openfarma.db"


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


def merge_into(cur, drop_id: int, keep_id: int, new_dci: str = None):
    cur.execute(
        "SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?",
        (drop_id,),
    )
    src = cur.fetchone()
    cur.execute(
        "SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?",
        (keep_id,),
    )
    tgt = cur.fetchone()
    if not src:
        print(f"  SKIP: id={drop_id} not found")
        return
    if not tgt:
        print(f"  SKIP: id={keep_id} not found")
        return
    src_ids = json.loads(src[1] or "[]")
    tgt_ids = json.loads(tgt[1] or "[]")
    if new_dci:
        fix_cum_dci(cur, src_ids, new_dci)
    union = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(union) - len(tgt_ids)
    print(
        f"  Merge id={drop_id} '{src[0]}' (n={src[2]}) -> id={keep_id} '{tgt[0]}' (n={tgt[2]}) +{added}"
    )
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(union), len(union), keep_id),
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. METRONIDAZOL||NIFUROXAZIDA SIN_CONC -> id=22 '600 mg + 200 mg'
    print("=== 1. METRONIDAZOL||NIFUROXAZIDA id=3793 -> id=22 '600 mg + 200 mg' ===")
    merge_into(cur, 3793, 22)
    conn.commit()

    # 2. CARBOXIMETILCELULOSA SODICA OFTALMICO SIN_CONC -> id=2993 '5 mg/mL'
    print("\n=== 2. CARBOXIMETILCELULOSA SODICA OFTALMICO id=2990 -> id=2993 '5 mg/mL' ===")
    merge_into(cur, 2990, 2993)
    conn.commit()

    # 3. ENOXAPARINA INYECTABLE SIN_CONC -> id=306 '100 mg/mL'
    print("\n=== 3. ENOXAPARINA INYECTABLE id=3166 -> id=306 '100 mg/mL' ===")
    merge_into(cur, 3166, 306)
    conn.commit()

    # 4. AMOXICILINA||SULBACTAM LIQUIDO_ORAL SIN_CONC -> id=3867 '200 mg/5 mL'
    print("\n=== 4. AMOXICILINA||SULBACTAM LIQUIDO_ORAL id=2619 -> id=3867 '200 mg/5 mL' ===")
    merge_into(cur, 2619, 3867)
    conn.commit()

    # 5. CLINDAMICINA||CLOTRIMAZOL VAGINAL SIN_CONC -> id=1264 '100 mg + 200 mg'
    print("\n=== 5. CLINDAMICINA||CLOTRIMAZOL VAGINAL id=3348 -> id=1264 '100 mg + 200 mg' (Vagylin) ===")
    merge_into(cur, 3348, 1264)
    conn.commit()

    # 6. ACIDO CLAVULANICO||AMOXICILINA '500 mg' -> id=33 '125 mg + 500 mg'
    print("\n=== 6. ACIDO CLAVULANICO||AMOXICILINA id=3798 '500 mg' -> id=33 '125 mg + 500 mg' ===")
    merge_into(cur, 3798, 33)
    conn.commit()

    # 7. CEFALEXINA SOLIDO_ORAL SIN_CONC -> id=120 '500 mg'
    print("\n=== 7. CEFALEXINA SOLIDO_ORAL id=3835 -> id=120 '500 mg' ===")
    merge_into(cur, 3835, 120)
    conn.commit()

    # 8. AMPICILINA LIQUIDO_ORAL '250 mg/5 mL' -> id=2662 '50 mg/mL' (equivalent)
    print("\n=== 8. AMPICILINA LIQUIDO_ORAL id=3828 '250 mg/5 mL' -> id=2662 '50 mg/mL' ===")
    merge_into(cur, 3828, 2662)
    conn.commit()

    # 9. id=3605 fix concentration format
    print("\n=== 9. CIANOCOBALAMINA||DICLOFENACO||LIDOCAINA||PIRIDOXINA||TIAMINA id=3605: fix format ===")
    new_conc = "1 mg + 75 mg + 20 mg + 50 mg + 100 mg"
    # Also update componentes with correct dosis_mg values
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3605")
    row = cur.fetchone()
    if row:
        cum_ids = json.loads(row[0] or "[]")
        dose_map = {
            "CIANOCOBALAMINA": 1.0,
            "DICLOFENACO": 75.0,
            "LIDOCAINA": 20.0,
            "PIRIDOXINA": 50.0,
            "TIAMINA": 100.0,
        }
        for cid in cum_ids:
            if "-" not in cid:
                continue
            exp, consec = cid.split("-", 1)
            cur.execute(
                "SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                (exp, consec),
            )
            p = cur.fetchone()
            if not p:
                continue
            try:
                comps = json.loads(p[0] or "[]")
                for c in comps:
                    dci = c.get("dci", "").upper()
                    if dci in dose_map and c.get("dosis_mg") is None:
                        c["dosis_mg"] = dose_map[dci]
                cur.execute(
                    "UPDATE cum_normalizado SET componentes=? WHERE expediente_cum=? AND consecutivo_cum=?",
                    (json.dumps(comps, ensure_ascii=False), exp, consec),
                )
            except Exception:
                pass
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=3605",
        (new_conc,),
    )
    print(f"  Updated id=3605 concentracion_norm -> '{new_conc}'")
    conn.commit()

    # 10. DIMETICONA||MAGALDRATO SIN_CONC -> '80 mg + 800 mg' (Riopan Gel confirmed by DeepSeek)
    print("\n=== 10. DIMETICONA||MAGALDRATO id=3529 SIN_CONC -> '80 mg + 800 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='80 mg + 800 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=3529"
    )
    print("  Updated id=3529 concentracion_norm -> '80 mg + 800 mg'")
    conn.commit()

    # Final state
    print("\n=== Final state ===")
    verify = [22, 2993, 306, 3867, 1264, 33, 120, 2662, 3605, 3529]
    for gid in verify:
        cur.execute(
            "SELECT id, dci_key, grupo_via, concentracion_norm, n_productos FROM grupos_equivalencia WHERE id=?",
            (gid,),
        )
        r = cur.fetchone()
        if r:
            print(f"  id={r[0]:5d}  {r[1][:35]:35s}  {r[2]:15s}  {r[3]!r}  n={r[4]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
