"""
Fix COLECALCIFEROL unit inconsistency in combination groups.
CUM stores COLECALCIFEROL dosis_mg as UI value (e.g. 200, 800) for some products,
while others store actual mg (e.g. 0.02 mg = 800 UI).
This results in fragmented groups that represent the same drug+dose.

Strategy:
  - For COLECALCIFEROL dosis_mg > 2: treat as UI (convert label from "X mg" to "X UI")
  - For COLECALCIFEROL dosis_mg <= 2 and > 0: treat as mg, convert to UI (× 40,000)
  - Rebuild concentracion_norm and merge resulting duplicates
"""
import sqlite3
import json
import re

DB_PATH = "farmavigia.db"


def fmt_ui(ui: float) -> str:
    return str(int(ui)) if ui == int(ui) else f"{ui:g}"


def fmt_mg(mg: float) -> str:
    return str(int(mg)) if mg == int(mg) else str(mg)


def colecalciferol_ui_from_mg(mg_val: float) -> float:
    """Convert mg → UI for COLECALCIFEROL (1 IU = 0.000025 mg)."""
    return mg_val / 0.000025


def get_colecalciferol_dose(cur, cum_ids: list[str]) -> float | None:
    """Get COLECALCIFEROL dosis_mg from sample product."""
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
        for c in comps:
            dci = c.get('dci', '').upper()
            if 'COLECALCIFEROL' in dci:
                dmg = c.get('dosis_mg')
                if dmg is not None and float(dmg) > 0:
                    return float(dmg)
    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Find all groups that contain COLECALCIFEROL as a component (multi-drug)
    # and have non-UI concentracion_norm (no "UI" in it)
    cur.execute("""
        SELECT id, dci_key, grupo_via, concentracion_norm, n_productos, cum_ids
        FROM grupos_equivalencia
        WHERE dci_key LIKE '%COLECALCIFEROL%'
        AND dci_key LIKE '%||%'
        AND concentracion_norm NOT LIKE '%UI%'
        AND concentracion_norm NOT LIKE '%ui%'
        AND concentracion_norm NOT LIKE 'SIN%'
        AND concentracion_norm NOT LIKE '%/%'
        AND concentracion_norm NOT LIKE '%g/5 ml%'
        ORDER BY dci_key, concentracion_norm
    """)
    groups = cur.fetchall()
    print(f"Found {len(groups)} combination COLECALCIFEROL groups without UI unit")

    fixed = 0
    skipped = 0

    for gid, dci_key, via, conc_old, n_prods, cum_ids_json in groups:
        dci_parts = dci_key.split('||')
        if 'COLECALCIFEROL' not in dci_parts:
            skipped += 1
            continue

        colec_idx = dci_parts.index('COLECALCIFEROL')

        # Parse current concentracion_norm components
        conc_parts = [p.strip() for p in conc_old.split('+')]
        if len(conc_parts) != len(dci_parts):
            # Mismatch — might be partial conc (e.g. only CALCIO dose)
            skipped += 1
            continue

        cum_ids = json.loads(cum_ids_json) if cum_ids_json else []
        colec_raw = get_colecalciferol_dose(cur, cum_ids)

        if colec_raw is None:
            skipped += 1
            continue

        # Determine UI value
        if colec_raw > 2:
            # Already stored as UI in dosis_mg
            colec_ui = colec_raw
        else:
            # Stored as mg, convert to UI
            colec_ui = colecalciferol_ui_from_mg(colec_raw)

        # Rebuild concentracion_norm: replace COLECALCIFEROL position
        new_parts = list(conc_parts)
        # The current part at colec_idx: extract mg value to verify
        part_str = conc_parts[colec_idx]
        mg_match = re.match(r'^([\d\.]+)\s*mg$', part_str)
        if not mg_match:
            # Already has correct unit or different format
            skipped += 1
            continue

        stored_mg_val = float(mg_match.group(1))
        # Verify consistency: stored value should match dosis_mg
        # (allow 1% tolerance for float rounding)
        expected = colec_raw if colec_raw > 2 else round(colec_raw, 10)
        if abs(stored_mg_val - colec_raw) / max(colec_raw, 1e-10) > 0.02:
            # Mismatch — data inconsistency, skip
            print(f"  MISMATCH id={gid} conc_part={stored_mg_val} dosis_mg={colec_raw} {dci_key}")
            skipped += 1
            continue

        new_parts[colec_idx] = f"{fmt_ui(colec_ui)} UI"
        new_conc = ' + '.join(new_parts)

        if new_conc == conc_old:
            skipped += 1
            continue

        print(f"  FIX id={gid:5d}  n={n_prods:3d}  {conc_old:40s} -> {new_conc}")
        cur.execute(
            "UPDATE grupos_equivalencia SET concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (new_conc, gid)
        )
        fixed += 1

    conn.commit()
    print(f"\nFixed: {fixed}, Skipped: {skipped}")

    # Find and merge resulting duplicates
    print("\n=== Finding duplicates after unit fix ===")
    cur.execute("""
        SELECT g1.id, g1.dci_key, g1.concentracion_norm, g1.n_productos,
               g2.id, g2.n_productos
        FROM grupos_equivalencia g1
        JOIN grupos_equivalencia g2
          ON g1.dci_key=g2.dci_key
         AND g1.grupo_via=g2.grupo_via
         AND g1.concentracion_norm=g2.concentracion_norm
         AND g1.id < g2.id
        WHERE g1.dci_key LIKE '%COLECALCIFEROL%'
        ORDER BY g1.dci_key, g1.concentracion_norm
    """)
    dupes = cur.fetchall()
    print(f"Found {len(dupes)} duplicate pairs")

    merged = 0
    processed: set[int] = set()
    for g1id, dci_key, conc, n1, g2id, n2 in dupes:
        if g1id in processed or g2id in processed:
            continue
        keep_id, drop_id = (g1id, g2id) if n1 >= n2 else (g2id, g1id)

        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (drop_id,))
        s = cur.fetchone()
        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (keep_id,))
        t = cur.fetchone()
        if not s or not t:
            continue

        src_ids = json.loads(s[0]) if s[0] else []
        tgt_ids = json.loads(t[0]) if t[0] else []
        union = list(dict.fromkeys(tgt_ids + src_ids))
        added = len(union) - len(tgt_ids)

        print(f"  Merge id={drop_id} (n={n1 if drop_id==g1id else n2}) -> id={keep_id} (n={n2 if keep_id==g2id else n1}) +{added}  {conc[:30]}  {dci_key[:40]}")
        cur.execute(
            "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(union), len(union), keep_id)
        )
        cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))
        processed.add(g1id)
        processed.add(g2id)
        merged += 1

    conn.commit()

    # Also need to fix fractional mg groups that should become UI and match existing UI groups
    # Fractional mg groups: COLECALCIFEROL dosis_mg <= 2 (stored in mg)
    # These are already handled above if they had mg-format concentracion_norm
    print(f"\nMerged {merged} pairs")

    # Final state
    cur.execute("""
        SELECT id, concentracion_norm, n_productos
        FROM grupos_equivalencia
        WHERE dci_key='CALCIO||COLECALCIFEROL'
        ORDER BY concentracion_norm
    """)
    print("\n=== Final CALCIO||COLECALCIFEROL groups ===")
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[1]:40s}  n={r[2]}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"\nTotal grupos: {cur.fetchone()[0]}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
