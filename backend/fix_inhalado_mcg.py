"""
Fix INHALADO grupos_equivalencia concentracion_norm:
  - Convert sub-2mg dose values from 'X mg' format to 'X mcg/dosis' format
  - Handle combinations: 'A mcg + B mcg/dosis' in dci_key alphabetical order
  - Special case: BECLOMETASONA||FORMOTEROL||GLICOPIRRONIO (all dosis_mg=0 in DB)
  - Skip: TOBRAMICINA/COLISTINA/ACETILCISTEINA/METOXIFLURANO (real mg doses)
  - Skip: FLUTICASONA||SALMETEROL id=1933 (data error in source, review separately)
"""
import sqlite3
import json

DB_PATH = "farmavigia.db"
MCG_THRESHOLD_MG = 2.0  # doses < 2 mg → convert to mcg


def _fmt_mcg(mg_val: float) -> str:
    """Format mg value as mcg, using integer if whole number."""
    mcg = mg_val * 1000
    if mcg == int(mcg):
        return f"{int(mcg)}"
    return f"{mcg:g}"


def _build_mcg_norm(dci_key: str, comps: list[dict]) -> str | None:
    """
    Build concentracion_norm string in mcg/dosis from componentes list.
    Returns None if can't compute (missing/zero dosis_mg).
    """
    dci_parts = dci_key.split("||")  # already alphabetical

    # Build map: dci_name → dosis_mg
    dosis_map: dict[str, float] = {}
    for c in comps:
        dci = c.get("dci", "").upper().strip()
        dmg = c.get("dosis_mg") or 0
        if dci:
            dosis_map[dci] = float(dmg)

    # Match dci_key parts to componentes (partial match for safety)
    ordered_doses = []
    for part in dci_parts:
        matched = None
        for dci_name, dmg in dosis_map.items():
            if part in dci_name or dci_name in part:
                matched = dmg
                break
        if matched is None:
            return None  # can't resolve
        ordered_doses.append(matched)

    if not all(d > 0 for d in ordered_doses):
        return None  # some zeros

    mcg_parts = [_fmt_mcg(d) for d in ordered_doses]
    if len(mcg_parts) == 1:
        return f"{mcg_parts[0]} mcg/dosis"
    return " + ".join(mcg_parts) + " mcg/dosis"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get all INHALADO groups with mg-based (not per-mL, not %) concentracion_norm
    cur.execute("""
        SELECT id, dci_key, concentracion_norm, n_productos, cum_ids
        FROM grupos_equivalencia
        WHERE grupo_via='INHALADO'
        AND concentracion_norm NOT LIKE '%/%'
        AND concentracion_norm NOT LIKE '%PPM%'
        AND concentracion_norm NOT LIKE '% v/v%'
        AND concentracion_norm NOT LIKE '%V/V%'
        AND concentracion_norm NOT LIKE '%UI%'
        AND concentracion_norm NOT LIKE '%ui%'
        AND concentracion_norm != 'porcentual'
        AND concentracion_norm != 'SIN_CONCENTRACION'
        AND concentracion_norm NOT LIKE '%[0-9]%[0-9]%'
        ORDER BY id
    """)
    groups = cur.fetchall()
    print(f"Found {len(groups)} candidate INHALADO groups")

    fixed = 0
    skipped = 0
    manual = []

    for gid, dci_key, conc_old, n_prods, cum_ids_json in groups:
        cum_ids = json.loads(cum_ids_json) if cum_ids_json else []
        if not cum_ids:
            skipped += 1
            continue

        # Get a sample product's componentes
        sample_cum = cum_ids[0]
        if '-' not in sample_cum:
            skipped += 1
            continue
        exp, consec = sample_cum.split('-', 1)
        cur.execute(
            "SELECT componentes FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=? LIMIT 1",
            (exp, consec)
        )
        row = cur.fetchone()
        if not row or not row[0]:
            skipped += 1
            continue
        comps = json.loads(row[0])

        # Check max dose
        max_dose = max((c.get("dosis_mg") or 0) for c in comps)

        if max_dose <= 0:
            # All zeros: manual review needed
            manual.append((gid, dci_key, conc_old))
            continue

        if max_dose >= MCG_THRESHOLD_MG:
            # Real mg dose (tobramycin, colistin, dornase alfa, metoxiflurano)
            print(f"  SKIP id={gid:5d}  {conc_old:25s}  max_mg={max_dose:.1f}  {dci_key}")
            skipped += 1
            continue

        # Build new mcg string
        new_conc = _build_mcg_norm(dci_key, comps)
        if new_conc is None:
            manual.append((gid, dci_key, conc_old))
            continue

        print(f"  FIX id={gid:5d}  n={n_prods:3d}  {conc_old:25s} -> {new_conc:30s}  {dci_key}")
        cur.execute(
            "UPDATE grupos_equivalencia SET concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (new_conc, gid)
        )
        fixed += 1

    # Manual fix: BECLOMETASONA||FORMOTEROL||GLICOPIRRONIO id=13 (Trimbow: 100+6+12.5 mcg)
    print(f"\n=== Manual fixes ===")
    trimbow_conc = "100 mcg + 6 mcg + 12.5 mcg/dosis"
    print(f"  FIX id=13  BECLOMETASONA||FORMOTEROL||GLICOPIRRONIO -> {trimbow_conc}")
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=13",
        (trimbow_conc,)
    )

    # Report groups needing manual review
    if manual:
        print(f"\n=== Needs manual review ({len(manual)}) ===")
        for gid, dci_key, conc in manual:
            print(f"  id={gid:5d}  {conc:25s}  {dci_key}")

    conn.commit()
    conn.close()
    print(f"\nFixed: {fixed}, Skipped: {skipped}, Manual: {len(manual)}")


if __name__ == "__main__":
    main()
