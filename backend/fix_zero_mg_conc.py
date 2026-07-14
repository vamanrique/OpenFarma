"""
Fix concentration display bugs for sub-mg dose drugs:

1. LEVOTIROXINA id=849 '125 mg' -> '0.125 mg' (CUM stored 125 mcg as 125 in dosis_mg)
2. LEVOTIROXINA id=737 '0 mg' -> '0.025 mg'
3. TIZANIDINA id=1349 '0 mg' -> '2 mg', merge into id=190 (products say '2 Mg')
4. LUBIPROSTONA id=1621 '0 mg' -> split into '0.008 mg' (8mcg) and '0.024 mg' (24mcg)
5. PARICALCITOL id=1127 '0 mg' -> split into '0.001 mg' and '0.002 mg'
6. CALCITRIOL id=777 '0 mg' -> '0.00025 mg'
7. ACIDO SALICILICO TRANSDERMICO id=846 '0 mg' -> '0.04 mg'
8. FLUTICASONA NASAL id=1142 '0 mg' -> '0.0275 mg'
9. DESMOPRESINA NASAL id=1800 '0 mg' -> '0.01 mg'
10. OCTREOTIDA INYECTABLE id=2395 '0 mg' -> '0.02 mg'
11. ANTIGENO HEPATITIS B id=2048 '0 mg' -> split 0.01 mg and 0.02 mg groups
"""
import sqlite3
import json

DB_PATH = "openfarma.db"


def get_product_dose(cur, cid: str, dci_key: str) -> float | None:
    if "-" not in cid:
        return None
    exp, consec = cid.split("-", 1)
    cur.execute(
        "SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
        (exp, consec),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    comps = json.loads(row[0])
    parts = dci_key.split("||")
    for c in comps:
        dci = c.get("dci", "").upper().strip()
        dm = c.get("dosis_mg")
        if dm is None:
            continue
        for p in parts:
            if p in dci or dci in p:
                return float(dm)
    # fallback: first non-zero
    for c in comps:
        dm = c.get("dosis_mg")
        if dm is not None and float(dm) > 0:
            return float(dm)
    return None


def fmt_dose(d: float) -> str:
    return str(int(d)) if d == int(d) else str(d)


def split_group(cur, gid: int, dci_key: str, via: str, conn):
    """Split a group by actual dosis_mg into sub-groups."""
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        return
    cum_ids = json.loads(row[0] or "[]")

    # Map cum_id -> actual dose
    dose_map: dict[float, list] = {}
    for cid in cum_ids:
        dm = get_product_dose(cur, cid, dci_key)
        if dm is None:
            dm = 0.0
        dose_map.setdefault(dm, []).append(cid)

    if len(dose_map) <= 1:
        # Nothing to split
        doses = list(dose_map.keys())
        if doses and doses[0] > 0:
            new_conc = f"{fmt_dose(doses[0])} mg"
            cur.execute(
                "UPDATE grupos_equivalencia SET concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                (new_conc, gid),
            )
            print(f"  id={gid}: '0 mg' -> '{new_conc}'")
        return

    print(f"  Splitting id={gid} into {len(dose_map)} groups: {list(dose_map.keys())}")
    first = True
    for dose, ids in sorted(dose_map.items()):
        new_conc = f"{fmt_dose(dose)} mg" if dose > 0 else "SIN_CONCENTRACION"
        if first:
            # Update the existing group
            cur.execute(
                "UPDATE grupos_equivalencia SET concentracion_norm=?, cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                (new_conc, json.dumps(ids), len(ids), gid),
            )
            print(f"    Updated id={gid}: '{new_conc}' n={len(ids)}")
            first = False
        else:
            # Create new group (copy the original, changing cum_ids and conc)
            cur.execute(
                "SELECT dci_key, grupo_via FROM grupos_equivalencia WHERE id=?",
                (gid,),
            )
            g = cur.fetchone()
            if g:
                cur.execute(
                    """INSERT INTO grupos_equivalencia
                       (dci_key, grupo_via, concentracion_norm, cum_ids, n_productos, revisado_ia, actualizado_en)
                       VALUES (?,?,?,?,?,0,CURRENT_TIMESTAMP)""",
                    (g[0], g[1], new_conc, json.dumps(ids), len(ids)),
                )
                new_id = cur.lastrowid
                print(f"    Created id={new_id}: '{new_conc}' n={len(ids)}")


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
    print(f"  Merged id={drop_id} (n={src[1]}) into id={keep_id} (n={tgt[1]}) +{added}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. LEVOTIROXINA id=849 '125 mg' -> '0.125 mg'
    print("=== LEVOTIROXINA id=849: '125 mg' -> '0.125 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='0.125 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=849"
    )
    print("  Done")

    # 2. LEVOTIROXINA id=737 '0 mg' -> '0.025 mg'
    print("=== LEVOTIROXINA id=737: '0 mg' -> '0.025 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='0.025 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=737"
    )
    print("  Done")

    # 3. TIZANIDINA id=1349 '0 mg' -> '2 mg', merge into id=190
    print("=== TIZANIDINA id=1349: '0 mg' -> '2 mg', merge into id=190 ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='2 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=1349"
    )
    merge_into(cur, drop_id=1349, keep_id=190)

    # 4. LUBIPROSTONA id=1621: split 0.008 mg vs 0.024 mg
    print("=== LUBIPROSTONA id=1621: split by dose ===")
    split_group(cur, 1621, "LUBIPROSTONA", "SOLIDO_ORAL", conn)

    # 5. PARICALCITOL id=1127: split 0.001 mg vs 0.002 mg
    print("=== PARICALCITOL id=1127: split by dose ===")
    split_group(cur, 1127, "PARICALCITOL", "SOLIDO_ORAL", conn)

    # 6. CALCITRIOL id=777
    print("=== CALCITRIOL id=777: '0 mg' -> '0.00025 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='0.00025 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=777"
    )
    print("  Done")

    # 7. ACIDO SALICILICO TRANSDERMICO id=846
    print("=== ACIDO SALICILICO TRANSDERMICO id=846: '0 mg' -> '0.04 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='0.04 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=846"
    )
    print("  Done")

    # 8. FLUTICASONA NASAL id=1142
    print("=== FLUTICASONA NASAL id=1142: '0 mg' -> '0.0275 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='0.0275 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=1142"
    )
    print("  Done")

    # 9. DESMOPRESINA NASAL id=1800
    print("=== DESMOPRESINA NASAL id=1800: '0 mg' -> '0.01 mg' ===")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm='0.01 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=1800"
    )
    print("  Done")

    # 10. OCTREOTIDA INYECTABLE id=2395
    print("=== OCTREOTIDA INYECTABLE id=2395: '0 mg' -> '0.02 mg' ===")
    # First check if there's an existing 0.02 mg group
    cur.execute(
        "SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='OCTREOTIDA' AND grupo_via='INYECTABLE' AND concentracion_norm='0.02 mg'"
    )
    existing = cur.fetchone()
    if existing:
        merge_into(cur, drop_id=2395, keep_id=existing[0])
    else:
        cur.execute(
            "UPDATE grupos_equivalencia SET concentracion_norm='0.02 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=2395"
        )
        print("  Done (no duplicate)")

    # 11. ANTIGENO HEPATITIS B id=2048: split by dose
    print("=== ANTIGENO HEPATITIS B id=2048: split by dose ===")
    split_group(cur, 2048, "ANTIGENO DE SUPERFICIE DEL VIRUS DE HEPATITIS B", "INYECTABLE", conn)

    conn.commit()

    # Final check
    print("\n=== Final '0 mg' groups remaining ===")
    cur.execute("SELECT id, dci_key, concentracion_norm, n_productos FROM grupos_equivalencia WHERE concentracion_norm='0 mg'")
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  {r[1][:35]:35s}  {r[2]!r}  n={r[3]}")

    print("\n=== Final LEVOTIROXINA groups ===")
    cur.execute("SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='LEVOTIROXINA' ORDER BY concentracion_norm")
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[1]!r}  n={r[2]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
