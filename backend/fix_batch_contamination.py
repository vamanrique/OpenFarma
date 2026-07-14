"""
Fix batch DCI contamination in groups with ids ~3789-3912.
These groups have wrong dci_key (brand names or wrong INNs).
Strategy:
  1. For each contaminated group, determine true DCI from componentes
  2. Update principios_dci in cum_normalizado
  3. Find matching existing group and merge, or fix in place
"""
import sqlite3
import json
from collections import Counter

DB_PATH = "openfarma.db"

# Groups confirmed to have correct dci_key (legitimate new LP/specialty groups)
SKIP_IDS = {
    3750, 3751, 3752, 3753, 3754, 3755, 3756, 3757, 3758, 3759, 3760,
    3761, 3762, 3763, 3764, 3765, 3766, 3767, 3768, 3769, 3770,
    3771, 3772, 3773, 3774, 3775, 3776, 3777, 3778, 3779, 3780,
    3781, 3782, 3783, 3784, 3785, 3786, 3787, 3788,
    3797, 3798, 3799, 3800, 3801, 3802, 3803, 3804,
    3807, 3808,
    3812,
    3814, 3815,
    3817,
    3822, 3825, 3827, 3828, 3833,
    # Already fixed by previous scripts
    3913, 3914, 3915,
    # Valid INN names that are correct
    3822,  # TRAMADOL inyectable
    3853, 3854, 3855,  # unknown, check
    3873,  # PENICILINA V
    3894,  # DICLOXACILINA
    3901,  # LINEZOLIDA
    3904,  # EMTRICITABINA||TENOFOVIR
}


def get_true_dci(cur, cum_ids: list) -> tuple[str, str] | None:
    """
    From a list of cum_ids, determine the true DCI by reading componentes.
    Returns (sorted_dci_key, conc_norm_sample) or None.
    """
    dci_vote: Counter = Counter()
    conc_samples: list[str] = []

    for cid in cum_ids:
        if "-" not in cid:
            continue
        exp, consec = cid.split("-", 1)
        cur.execute(
            "SELECT componentes, forma_normalizada, via_normalizada FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
            (exp, consec),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            continue
        try:
            comps = json.loads(row[0])
        except Exception:
            continue

        dcis = sorted({c.get("dci", "").upper().strip() for c in comps if c.get("dci")})
        if dcis:
            dci_vote["||".join(dcis)] += 1

    if not dci_vote:
        return None

    best_key = dci_vote.most_common(1)[0][0]
    return best_key


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


def merge_into(cur, drop_id: int, keep_id: int) -> int:
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (drop_id,))
    src = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    tgt = cur.fetchone()
    if not src or not tgt:
        return 0
    src_ids = json.loads(src[0] or "[]")
    tgt_ids = json.loads(tgt[0] or "[]")
    union = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(union) - len(tgt_ids)
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(union), len(union), keep_id),
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))
    return added


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, dci_key, grupo_via, concentracion_norm, n_productos, cum_ids FROM grupos_equivalencia WHERE id >= 3789 ORDER BY id"
    )
    rows = cur.fetchall()

    fixed = 0
    merged = 0
    skipped = 0

    for gid, old_key, via, conc, n, cum_ids_json in rows:
        if gid in SKIP_IDS:
            skipped += 1
            continue

        cum_ids = json.loads(cum_ids_json or "[]")
        if not cum_ids:
            skipped += 1
            continue

        # Determine true DCI
        true_key = get_true_dci(cur, cum_ids)
        if not true_key:
            print(f"  SKIP id={gid}: could not determine true DCI")
            skipped += 1
            continue

        # If key is already correct, skip
        if true_key == old_key:
            skipped += 1
            continue

        print(f"  id={gid:5d}  n={n:3d}  '{old_key[:30]}'")
        print(f"          -> '{true_key[:30]}'")

        # Update principios_dci in cum_normalizado
        update_cum_dci(cur, cum_ids, true_key)

        # Look for existing matching group
        cur.execute(
            "SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=? AND concentracion_norm=? AND id!=?",
            (true_key, via, conc, gid),
        )
        existing = cur.fetchone()

        if existing:
            keep_id = existing[0]
            added = merge_into(cur, gid, keep_id)
            print(f"          Merged into id={keep_id} +{added}")
            merged += 1
        else:
            # Just update the dci_key in place
            cur.execute(
                "UPDATE grupos_equivalencia SET dci_key=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                (true_key, gid),
            )
            print(f"          Renamed in place (no existing match)")
            fixed += 1

    conn.commit()
    print(f"\nFixed in place: {fixed}, Merged: {merged}, Skipped: {skipped}")

    # Check remaining groups with high IDs that might still be wrong
    print("\n=== Remaining groups id>=3789 with possible issues ===")
    cur.execute("SELECT id, dci_key, grupo_via, concentracion_norm, n_productos FROM grupos_equivalencia WHERE id >= 3789 ORDER BY id")
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  n={r[4]:3d}  dci={r[1][:40]!r}  via={r[2]}  conc={r[3]!r}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos_equivalencia: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
