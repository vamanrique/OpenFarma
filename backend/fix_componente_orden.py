"""
Fix component-order bug in grupos_equivalencia.concentracion_norm.
The ETL built concentracion_norm using CUM data component order (PARACETAMOL first)
instead of dci_key alphabetical order.

For each SOLIDO_ORAL/LIQUIDO_ORAL combination group:
  1. Get dci_key components (already alphabetical)
  2. Get a sample product's dosis_mg for each component
  3. Rebuild concentracion_norm in dci_key order
  4. Merge any resulting duplicates

Only fixes groups with multiple components and integer/decimal mg concentrations
(not mg/mL, UI, %, SIN_CONCENTRACION).
"""
import sqlite3
import json
import re

DB_PATH = "openfarma.db"

_MG_ONLY_RE = re.compile(r'^[\d\.]+ mg(?:\s*\+\s*[\d\.]+ mg)*$')


def _fmt_dose(d: float) -> str:
    return str(int(d)) if d == int(d) else str(d)


def _get_dose_map(cur, cum_ids: list[str], dci_parts: list[str]) -> dict[str, float] | None:
    """Try up to 3 sample products to build a complete dose map."""
    for cid in cum_ids[:3]:
        if '-' not in cid:
            continue
        exp, consec = cid.split('-', 1)
        cur.execute(
            "SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=? LIMIT 1",
            (exp, consec)
        )
        row = cur.fetchone()
        if not row or not row[0]:
            continue
        comps = json.loads(row[0])
        dose_map: dict[str, float] = {}
        unmatched_comps: list[tuple[str, float]] = []
        for c in comps:
            raw_dci = c.get('dci', '').upper().strip()
            dmg = c.get('dosis_mg')
            if dmg is None or dmg == 0:
                continue
            # Match against dci_parts
            matched = False
            for part in dci_parts:
                if part in raw_dci or raw_dci in part:
                    dose_map[part] = float(dmg)
                    matched = True
                    break
            if not matched:
                unmatched_comps.append((raw_dci, float(dmg)))
        # If exactly one dci_part is missing and one component is unmatched, assign it
        # (handles synonym mismatches like ACETAMINOFEN vs PARACETAMOL)
        missing = [p for p in dci_parts if p not in dose_map]
        if len(missing) == 1 and len(unmatched_comps) == 1:
            dose_map[missing[0]] = unmatched_comps[0][1]
        if len(dose_map) == len(dci_parts) and all(v > 0 for v in dose_map.values()):
            return dose_map
    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get all multi-component SOLIDO_ORAL/LIQUIDO_ORAL groups with pure mg concentrations
    cur.execute("""
        SELECT id, dci_key, concentracion_norm, n_productos, grupo_via, cum_ids
        FROM grupos_equivalencia
        WHERE grupo_via IN ('SOLIDO_ORAL', 'LIQUIDO_ORAL', 'SOLIDO_ORAL_LP', 'INYECTABLE', 'NASAL', 'VAGINAL', 'RECTAL', 'SUBLINGUAL')
        AND dci_key LIKE '%||%'
        AND concentracion_norm IS NOT NULL
        AND concentracion_norm NOT LIKE 'SIN%'
        AND concentracion_norm NOT LIKE '%ml%'
        AND concentracion_norm NOT LIKE '%mL%'
        AND concentracion_norm NOT LIKE '%ML%'
        AND concentracion_norm NOT LIKE '%UI%'
        AND concentracion_norm NOT LIKE '%ui%'
        AND concentracion_norm NOT LIKE '%!%%' ESCAPE '!'
        AND concentracion_norm LIKE '% mg%'
        ORDER BY id
    """)
    groups = cur.fetchall()
    print(f"Checking {len(groups)} multi-component mg groups...")

    fixed = 0
    skipped = 0
    errors = 0

    for gid, dci_key, conc_old, n_prods, via, cum_ids_json in groups:
        # Validate concentracion_norm is "X mg + Y mg + ..." format
        if not _MG_ONLY_RE.match(conc_old.strip()):
            skipped += 1
            continue

        dci_parts = dci_key.split('||')
        if len(dci_parts) < 2:
            skipped += 1
            continue

        # Count doses in concentracion_norm
        conc_parts = [p.strip().replace(' mg', '') for p in conc_old.split('+')]
        if len(conc_parts) != len(dci_parts):
            # Number of doses doesn't match DCIs - can't auto-fix
            skipped += 1
            continue

        cum_ids = json.loads(cum_ids_json) if cum_ids_json else []
        dose_map = _get_dose_map(cur, cum_ids, dci_parts)
        if dose_map is None:
            skipped += 1
            continue

        # Build correct concentracion_norm (dci_key order)
        new_conc = ' + '.join(
            f"{_fmt_dose(dose_map[p])} mg" for p in dci_parts
        )

        if new_conc != conc_old:
            print(f"  FIX id={gid:5d}  n={n_prods:3d}  {conc_old:30s} -> {new_conc:30s}  {dci_key[:50]}")
            cur.execute(
                "UPDATE grupos_equivalencia SET concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                (new_conc, gid)
            )
            fixed += 1

    conn.commit()
    print(f"\nFixed: {fixed}, Skipped: {skipped}, Errors: {errors}")

    # Find and merge resulting duplicates
    print("\n=== Finding new duplicates after reorder ===")
    cur.execute("""
        SELECT g1.id, g1.dci_key, g1.concentracion_norm, g1.n_productos,
               g2.id, g2.n_productos
        FROM grupos_equivalencia g1
        JOIN grupos_equivalencia g2 ON g1.dci_key=g2.dci_key AND g1.grupo_via=g2.grupo_via
             AND g1.concentracion_norm=g2.concentracion_norm AND g1.id < g2.id
        WHERE g1.dci_key LIKE '%||%'
        AND g1.grupo_via IN ('SOLIDO_ORAL', 'LIQUIDO_ORAL', 'SOLIDO_ORAL_LP', 'INYECTABLE', 'NASAL', 'VAGINAL', 'RECTAL', 'SUBLINGUAL')
        ORDER BY g1.dci_key, g1.concentracion_norm
    """)
    dupes = cur.fetchall()
    print(f"Found {len(dupes)} duplicate pairs")

    merged_count = 0
    # Process in rounds to handle chains (A=B=C: merge C->B first, then B->A)
    processed_ids: set[int] = set()
    for g1id, dci_key, conc, n1, g2id, n2 in dupes:
        if g1id in processed_ids or g2id in processed_ids:
            continue
        # Keep the larger group (by n_productos)
        if n1 >= n2:
            keep_id, drop_id, keep_n, drop_n = g1id, g2id, n1, n2
        else:
            keep_id, drop_id, keep_n, drop_n = g2id, g1id, n2, n1

        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (drop_id,))
        src_row = cur.fetchone()
        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (keep_id,))
        tgt_row = cur.fetchone()
        if not src_row or not tgt_row:
            continue

        src_ids = json.loads(src_row[0]) if src_row[0] else []
        tgt_ids = json.loads(tgt_row[0]) if tgt_row[0] else []
        merged = list(dict.fromkeys(tgt_ids + src_ids))
        added = len(merged) - len(tgt_ids)

        print(f"  Merge id={drop_id} (n={drop_n}) -> id={keep_id} (n={keep_n}) +{added}  {conc[:25]}  {dci_key[:40]}")
        cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                    (json.dumps(merged), len(merged), keep_id))
        cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))
        processed_ids.add(drop_id)
        processed_ids.add(keep_id)
        merged_count += 1

    conn.commit()
    conn.close()
    print(f"\nMerged {merged_count} duplicate pairs. Done.")


if __name__ == "__main__":
    main()
