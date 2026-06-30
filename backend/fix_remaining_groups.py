"""
Fix remaining problematic grupos_equivalencia:

1. id=3789 PARACETAMOL||TRAMADOL SIN_CONC -> merge into id=147 "325 mg + 37.5 mg"
2. id=3805 mixed group -> split:
   - Amoxidal Duo (875mg, clav missing in componentes) -> id=34 (875+125)
   - Clavutec 500+125 -> id=33
   - Clavutec 875+125 -> id=34
   - Trifamox IBL Duo (SULBACTAM!) -> fix DCI -> id=36 AMOXICILINA||SULBACTAM 875+125
3. id=3826 PANTOPRAZOL SOLID SIN_CONC -> id=121 "40 mg"
4. id=3839 PANTOPRAZOL INY SIN_CONC -> id=145 "40 mg"
5. id=3840 FENTANILO "50 mg/mL" -> "0.05 mg/mL" -> id=129
6. id=3858 DIFENHIDRAMINA||PARACETAMOL SIN_CONC -> update to "25 mg + 500 mg"
7. id=3863 SECNIDAZOL SIN_CONC: 12 Seamib -> id=325; Varcor (VALSARTAN!) -> id=736
8. id=3877 DESLORATADINA SIN_CONC -> id=692 "5 mg"
9. id=3904 EMTRICITABINA||TENOFOVIR "200 mg / 300 mg" -> id=1306 "200 mg + 300 mg"
10. id=3906 MELOXICAM SIN_CONC -> id=632 "15 mg"
11. id=3912 GLUCOSAMINA "0.4 mg/dosis" -> "1500 mg" -> id=3129
"""
import sqlite3
import json

DB_PATH = "farmavigia.db"


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


def merge_into(cur, drop_id: int, keep_id: int, new_dci_for_dropped: str = None):
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
    if new_dci_for_dropped:
        fix_cum_dci(cur, src_ids, new_dci_for_dropped)
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


def add_ids_to_group(cur, cum_ids: list, keep_id: int, new_dci: str = None):
    """Add a subset of cum_ids to a target group without deleting any source group."""
    cur.execute(
        "SELECT dci_key, cum_ids, n_productos FROM grupos_equivalencia WHERE id=?",
        (keep_id,),
    )
    tgt = cur.fetchone()
    if not tgt:
        print(f"  SKIP: target id={keep_id} not found")
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

    # --- 1. id=3789 PARACETAMOL||TRAMADOL SIN_CONCENTRACION -> id=147 ---
    print("=== 1. PARACETAMOL||TRAMADOL id=3789 SIN_CONC -> id=147 '325 mg + 37.5 mg' ===")
    merge_into(cur, 3789, 147)
    conn.commit()

    # --- 2. id=3805 mixed group: route by actual componentes ---
    print("\n=== 2. ACIDO CLAVULANICO||AMOXICILINA id=3805 SIN_CONC: split and route ===")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3805")
    row = cur.fetchone()
    if row:
        ids = json.loads(row[0] or "[]")
        sulbactam_ids = []
        clav_500_ids = []
        clav_875_ids = []

        for cid in ids:
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
                dcis = [c.get("dci", "").upper() for c in comps]
                doses = {c.get("dci", "").upper(): c.get("dosis_mg") for c in comps}
            except Exception:
                dcis = []
                doses = {}

            if "SULBACTAM" in dcis:
                sulbactam_ids.append(cid)
            elif "ACIDO CLAVULANICO" in dcis:
                amox_mg = doses.get("AMOXICILINA", 0) or 0
                if amox_mg >= 800:
                    clav_875_ids.append(cid)
                else:
                    clav_500_ids.append(cid)
            else:
                # Amoxidal Duo: componentes only has AMOXICILINA but it IS a combo
                clav_875_ids.append(cid)

        print(
            f"  Classified: sulbactam={len(sulbactam_ids)}, clav-875={len(clav_875_ids)}, clav-500={len(clav_500_ids)}"
        )

        # Route Sulbactam -> id=36 AMOXICILINA||SULBACTAM 875mg+125mg
        if sulbactam_ids:
            print(f"  Trifamox IBL Duo ({len(sulbactam_ids)} prods) -> id=36 AMOXICILINA||SULBACTAM 875mg+125mg")
            add_ids_to_group(cur, sulbactam_ids, 36, "AMOXICILINA||SULBACTAM")

        # Route Clavutec 500+125 -> id=33
        if clav_500_ids:
            print(f"  Clavutec 500+125 ({len(clav_500_ids)} prods) -> id=33")
            add_ids_to_group(cur, clav_500_ids, 33, "ACIDO CLAVULANICO||AMOXICILINA")

        # Route Amoxidal+Clavutec 875+125 -> id=34
        if clav_875_ids:
            print(f"  Amoxidal/Clavutec 875+125 ({len(clav_875_ids)} prods) -> id=34")
            add_ids_to_group(cur, clav_875_ids, 34, "ACIDO CLAVULANICO||AMOXICILINA")

        # Delete id=3805 (now empty)
        cur.execute("DELETE FROM grupos_equivalencia WHERE id=3805")
        print("  Deleted id=3805")

    conn.commit()

    # --- 3. id=3826 PANTOPRAZOL SOLIDO_ORAL SIN_CONC -> id=121 "40 mg" ---
    print("\n=== 3. PANTOPRAZOL SOLIDO_ORAL id=3826 SIN_CONC -> id=121 '40 mg' ===")
    merge_into(cur, 3826, 121)
    conn.commit()

    # --- 4. id=3839 PANTOPRAZOL INYECTABLE SIN_CONC -> id=145 "40 mg" ---
    print("\n=== 4. PANTOPRAZOL INYECTABLE id=3839 SIN_CONC -> id=145 '40 mg' ===")
    merge_into(cur, 3839, 145)
    conn.commit()

    # --- 5. id=3840 FENTANILO "50 mg/mL" -> "0.05 mg/mL" -> id=129 ---
    print("\n=== 5. FENTANILO INYECTABLE id=3840 '50 mg/mL' -> '0.05 mg/mL' -> id=129 ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='0.05 mg/mL', actualizado_en=CURRENT_TIMESTAMP WHERE id=3840"
    )
    merge_into(cur, 3840, 129)
    conn.commit()

    # --- 6. id=3858 DIFENHIDRAMINA||PARACETAMOL SIN_CONC -> update conc (no existing group) ---
    print("\n=== 6. DIFENHIDRAMINA||PARACETAMOL id=3858 SIN_CONC -> '25 mg + 500 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='25 mg + 500 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=3858"
    )
    cur.execute("SELECT n_productos FROM grupos_equivalencia WHERE id=3858")
    r = cur.fetchone()
    print(f"  Updated id=3858 conc to '25 mg + 500 mg' (n={r[0] if r else '?'})")
    conn.commit()

    # --- 7. id=3863 SECNIDAZOL: separate VALSARTAN, merge Seamib into id=325 ---
    print("\n=== 7. SECNIDAZOL id=3863: fix Varcor VALSARTAN contamination ===")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3863")
    row = cur.fetchone()
    if row:
        ids = json.loads(row[0] or "[]")
        secnidazol_ids = []
        valsartan_ids = []

        for cid in ids:
            if "-" not in cid:
                continue
            exp, consec = cid.split("-", 1)
            cur.execute(
                "SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                (exp, consec),
            )
            p = cur.fetchone()
            if not p:
                secnidazol_ids.append(cid)
                continue
            try:
                comps = json.loads(p[0] or "[]")
                dcis = [c.get("dci", "").upper() for c in comps]
            except Exception:
                dcis = []

            if "VALSARTAN" in dcis:
                valsartan_ids.append(cid)
                print(f"  VALSARTAN contaminant: {cid}")
            else:
                secnidazol_ids.append(cid)

        # Fix Varcor: change principios_dci and move to id=736 VALSARTAN 160mg
        if valsartan_ids:
            fix_cum_dci(cur, valsartan_ids, "VALSARTAN")
            add_ids_to_group(cur, valsartan_ids, 736, "VALSARTAN")

        # Update id=3863 to only have SECNIDAZOL products
        cur.execute(
            "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=3863",
            (json.dumps(secnidazol_ids), len(secnidazol_ids)),
        )
        print(f"  id=3863 reduced to {len(secnidazol_ids)} SECNIDAZOL products")

    # Now merge id=3863 (all SECNIDAZOL 500mg) into id=325
    print("  Merging id=3863 SECNIDAZOL 500mg -> id=325")
    merge_into(cur, 3863, 325)
    conn.commit()

    # --- 8. id=3877 DESLORATADINA SIN_CONC -> id=692 "5 mg" ---
    print("\n=== 8. DESLORATADINA id=3877 SIN_CONC -> id=692 '5 mg' ===")
    merge_into(cur, 3877, 692)
    conn.commit()

    # --- 9. id=3904 EMTRICITABINA||TENOFOVIR "200 mg / 300 mg" -> id=1306 "200 mg + 300 mg" ---
    print("\n=== 9. EMTRICITABINA||TENOFOVIR id=3904 '200 mg / 300 mg' -> id=1306 '200 mg + 300 mg' ===")
    merge_into(cur, 3904, 1306)
    conn.commit()

    # --- 10. id=3906 MELOXICAM SIN_CONC -> id=632 "15 mg" ---
    print("\n=== 10. MELOXICAM id=3906 SIN_CONC -> id=632 '15 mg' ===")
    merge_into(cur, 3906, 632)
    conn.commit()

    # --- 11. id=3912 GLUCOSAMINA "0.4 mg/dosis" -> "1500 mg" -> id=3129 ---
    print("\n=== 11. GLUCOSAMINA LIQUIDO_ORAL id=3912 '0.4 mg/dosis' -> '1500 mg' -> id=3129 ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='1500 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=3912"
    )
    merge_into(cur, 3912, 3129)
    conn.commit()

    # Final verification
    print("\n=== Final state of modified groups ===")
    check_ids = [147, 33, 34, 36, 121, 145, 129, 3858, 325, 692, 1306, 632, 3129, 736]
    for gid in check_ids:
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
