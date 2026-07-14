"""
Batch 3 fixes:

1.  id=3787 IBUPROFENO||PARACETAMOL SIN_CONC -> '400 mg + 500 mg' (Algimide F confirmed)
2.  id=3790 CLOTRIMAZOL||METRONIDAZOL VAGINAL SIN_CONC -> split:
      tablet (Gynoflor Tab) -> id=18 '100 mg + 500 mg'
      cream (Gynoflor Crema) -> update to '20 mg/g + 100 mg/g'
3.  id=3804 AMOXICILINA SIN_CONC -> route by actual dose:
      Amoxidal Duo 875mg (actually combo) -> fix dci -> id=34 AMOXICILINA||CLAVULANICO 875+125
      Neogram 875mg -> id=35 AMOXICILINA 875mg
      Adbiotin/Eumoxina 500mg -> id=32 AMOXICILINA 500mg
4.  id=3817 DEXAMETASONA INYECTABLE SIN_CONC -> id=99 '16 mg + 4 mg' (Duo-Decadron)
5.  id=3320 BRIMONIDINA||DORZOLAMIDA||TIMOLOL SIN_CONC -> id=3319 '2 mg/mL + 20 mg/mL + 5 mg/mL'
6.  id=3436 DEXAMETASONA||MOXIFLOXACINO SIN_CONC -> id=3435 '1 mg/mL + 5 mg/mL'
7.  id=2644 DEXAMETASONA||NEOMICINA||POLIMIXINA B SIN_CONC -> route:
      Products with Dexa 1.3 mg (dosis_mg) -> id=2647
      All others -> id=2646 '1 mg/mL + 3.5 mg/mL + 6000 UI/mL'
8.  id=3631 MENTOL||METILO SALICILATO -> rename + merge into id=3625 MENTOL||SALICILATO DE METILO
9.  id=3396 MENTOL||METIL SALICILATO -> rename + merge into id=3625
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


def add_to_group(cur, cum_ids: list, keep_id: int, new_dci: str = None):
    cur.execute(
        "SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?",
        (keep_id,),
    )
    tgt = cur.fetchone()
    if not tgt:
        print(f"  SKIP: id={keep_id} not found")
        return
    if new_dci:
        fix_cum_dci(cur, cum_ids, new_dci)
    tgt_ids = json.loads(tgt[1] or "[]")
    union = list(dict.fromkeys(tgt_ids + cum_ids))
    added = len(union) - len(tgt_ids)
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(union), len(union), keep_id),
    )
    print(f"    -> id={keep_id} '{tgt[0]}' n={tgt[2]} +{added}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- 1. id=3787 IBUPROFENO||PARACETAMOL -> '400 mg + 500 mg' ---
    print("=== 1. IBUPROFENO||PARACETAMOL id=3787 -> '400 mg + 500 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='400 mg + 500 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=3787"
    )
    print("  Updated concentracion_norm (no existing group to merge into)")
    conn.commit()

    # --- 2. id=3790 CLOTRIMAZOL||METRONIDAZOL: split tablet vs cream ---
    print("\n=== 2. CLOTRIMAZOL||METRONIDAZOL VAGINAL id=3790: split tablet/cream ===")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3790")
    row = cur.fetchone()
    if row:
        all_ids = json.loads(row[0] or "[]")
        tablet_ids = []
        cream_ids = []
        for cid in all_ids:
            if "-" not in cid:
                continue
            exp, consec = cid.split("-", 1)
            cur.execute(
                "SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                (exp, consec),
            )
            p = cur.fetchone()
            if not p:
                cream_ids.append(cid)
                continue
            try:
                comps = json.loads(p[0] or "[]")
                # Tablets have dosis_mg set; creams have concentracion_mg_ml set
                has_dosis_mg = any(c.get("dosis_mg") is not None for c in comps)
                has_conc_mg_ml = any(c.get("concentracion_mg_ml") is not None for c in comps)
            except Exception:
                has_dosis_mg = False
                has_conc_mg_ml = False

            if has_dosis_mg and not has_conc_mg_ml:
                tablet_ids.append(cid)
            else:
                cream_ids.append(cid)

        print(f"  Tablets: {len(tablet_ids)}, Creams: {len(cream_ids)}")

        if tablet_ids:
            print(f"  Tablet -> id=18 '100 mg + 500 mg'")
            add_to_group(cur, tablet_ids, 18)

        if cream_ids:
            cur.execute(
                "UPDATE grupos_equivalencia SET concentracion_norm='20 mg/g + 100 mg/g', cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=3790",
                (json.dumps(cream_ids), len(cream_ids)),
            )
            print(f"  Updated id=3790: cream products -> '20 mg/g + 100 mg/g' (n={len(cream_ids)})")
        elif not cream_ids:
            cur.execute("DELETE FROM grupos_equivalencia WHERE id=3790")
            print("  Deleted id=3790 (empty)")

    conn.commit()

    # --- 3. id=3804 AMOXICILINA SIN_CONC: route by dose ---
    print("\n=== 3. AMOXICILINA id=3804 SIN_CONC: route by actual dose/product ===")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3804")
    row = cur.fetchone()
    if row:
        all_ids = json.loads(row[0] or "[]")
        amox_875_ids = []
        amox_500_ids = []
        combo_ids = []  # Amoxidal Duo (actually AMOX+CLAV)

        for cid in all_ids:
            if "-" not in cid:
                continue
            exp, consec = cid.split("-", 1)
            cur.execute(
                "SELECT nombre_comercial_norm, componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                (exp, consec),
            )
            p = cur.fetchone()
            if not p:
                continue
            try:
                comps = json.loads(p[1] or "[]")
                amox_dose = next(
                    (c.get("dosis_mg") for c in comps if "AMOXICILINA" in c.get("dci", "").upper()),
                    None,
                )
            except Exception:
                amox_dose = None

            name = (p[0] or "").upper()
            if "AMOXIDAL DUO" in name:
                combo_ids.append(cid)
            elif amox_dose is not None and amox_dose >= 800:
                amox_875_ids.append(cid)
            else:
                amox_500_ids.append(cid)

        print(f"  Combo (Amoxidal Duo): {len(combo_ids)}, 875mg: {len(amox_875_ids)}, 500mg: {len(amox_500_ids)}")

        if combo_ids:
            print(f"  Amoxidal Duo -> fix dci -> id=34 AMOXICILINA||CLAVULANICO 875+125")
            add_to_group(cur, combo_ids, 34, "ACIDO CLAVULANICO||AMOXICILINA")

        if amox_875_ids:
            print(f"  875mg AMOXICILINA -> id=35")
            add_to_group(cur, amox_875_ids, 35)

        if amox_500_ids:
            print(f"  500mg AMOXICILINA -> id=32")
            add_to_group(cur, amox_500_ids, 32)

        cur.execute("DELETE FROM grupos_equivalencia WHERE id=3804")
        print("  Deleted id=3804")

    conn.commit()

    # --- 4. id=3817 DEXAMETASONA INYECTABLE -> id=99 '16 mg + 4 mg' ---
    print("\n=== 4. DEXAMETASONA INYECTABLE id=3817 SIN_CONC -> id=99 '16 mg + 4 mg' ===")
    merge_into(cur, 3817, 99)
    conn.commit()

    # --- 5. id=3320 BRIMONIDINA||DORZOLAMIDA||TIMOLOL -> id=3319 ---
    print("\n=== 5. BRIMONIDINA||DORZOLAMIDA||TIMOLOL id=3320 -> id=3319 '2+20+5 mg/mL' ===")
    merge_into(cur, 3320, 3319)
    conn.commit()

    # --- 6. id=3436 DEXAMETASONA||MOXIFLOXACINO -> id=3435 ---
    print("\n=== 6. DEXAMETASONA||MOXIFLOXACINO id=3436 -> id=3435 '1 mg/mL + 5 mg/mL' ===")
    merge_into(cur, 3436, 3435)
    conn.commit()

    # --- 7. id=2644 DEXAMETASONA||NEOMICINA||POLIMIXINA B: route by Dexa dose ---
    print("\n=== 7. DEXAMETASONA||NEOMICINA||POLIMIXINA B id=2644: route by Dexa conc ===")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=2644")
    row = cur.fetchone()
    if row:
        all_ids = json.loads(row[0] or "[]")
        standard_ids = []  # -> id=2646 (1 mg/mL)
        high_dexa_ids = []  # -> id=2647 (1.3 mg/mL)

        for cid in all_ids:
            if "-" not in cid:
                continue
            exp, consec = cid.split("-", 1)
            cur.execute(
                "SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                (exp, consec),
            )
            p = cur.fetchone()
            if not p:
                standard_ids.append(cid)
                continue
            try:
                comps = json.loads(p[0] or "[]")
                dexa_dose = next(
                    (c.get("dosis_mg") for c in comps if "DEXAMETASONA" in c.get("dci", "").upper()),
                    None,
                )
            except Exception:
                dexa_dose = None

            if dexa_dose is not None and dexa_dose >= 1.3:
                high_dexa_ids.append(cid)
            else:
                standard_ids.append(cid)

        print(f"  Standard (1mg/mL): {len(standard_ids)}, High-dexa (1.3mg/mL): {len(high_dexa_ids)}")

        if standard_ids:
            add_to_group(cur, standard_ids, 2646)
        if high_dexa_ids:
            add_to_group(cur, high_dexa_ids, 2647)

        cur.execute("DELETE FROM grupos_equivalencia WHERE id=2644")
        print("  Deleted id=2644")

    conn.commit()

    # --- 8. id=3631 MENTOL||METILO SALICILATO -> rename + merge into id=3625 ---
    print("\n=== 8. MENTOL||METILO SALICILATO id=3631 -> MENTOL||SALICILATO DE METILO -> id=3625 ===")
    merge_into(cur, 3631, 3625, "MENTOL||SALICILATO DE METILO")
    conn.commit()

    # --- 9. id=3396 MENTOL||METIL SALICILATO -> rename + merge into id=3625 ---
    print("\n=== 9. MENTOL||METIL SALICILATO id=3396 -> MENTOL||SALICILATO DE METILO -> id=3625 ===")
    merge_into(cur, 3396, 3625, "MENTOL||SALICILATO DE METILO")
    conn.commit()

    # Final verification
    print("\n=== Final state ===")
    check_ids = [3787, 18, 3790, 34, 35, 32, 99, 3319, 3435, 2646, 2647, 3625]
    for gid in check_ids:
        cur.execute(
            "SELECT id, dci_key, grupo_via, concentracion_norm, n_productos FROM grupos_equivalencia WHERE id=?",
            (gid,),
        )
        r = cur.fetchone()
        if r:
            print(f"  id={r[0]:5d}  {r[1][:32]:32s}  {r[2]:15s}  {r[3]!r:30s}  n={r[4]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
