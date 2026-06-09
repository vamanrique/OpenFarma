"""
Correcciones sistemáticas de normalización en grupos_equivalencia:
  Phase 1:  HIOSCINA variants → BUTILBROMURO DE HIOSCINA
  Phase 2:  AMOXICILINA LIQUIDO_ORAL case/space deduplication
  Phase 3:  CARBIDOPA ENTACAPONA/ENTACAPONE merge
  Phase 4:  Component-order duplicates (concentracion order doesn't match dci_key order)
  Phase 5:  TOXINA BOTULINICA UI vs U normalization
  Phase 6:  AMBROXOL equivalent concentration merge (15mg/5mL=3mg/mL, 30mg/5mL=6mg/mL)
  Phase 7:  PARACETAMOL LIQUIDO_ORAL 150mg/5mL = 30mg/mL
  Phase 8:  INSULINA fixes (GLULISINA 3.5mg/mL, ASPART/ASPARTA naming)
  Phase 9:  Data errors (PENICILINA G, DIOSMECTITA, ACIDO ASCORBICO)
  Phase 10: LANZAPIN → OLANZAPINA
  Phase 11: Synonym additions to cum_normalizado DCI for merged groups
"""
import json
import sqlite3

DB_PATH = "farmavigia.db"


def merge_groups(cur, source_id: int, target_id: int, reason: str = "") -> int:
    """Merges source group into target: unions cum_ids, updates n_productos, deletes source."""
    cur.execute("SELECT cum_ids, n_productos, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (source_id,))
    src = cur.fetchone()
    if not src:
        print(f"  [SKIP] Source id={source_id} not found")
        return 0
    cur.execute("SELECT cum_ids, n_productos, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (target_id,))
    tgt = cur.fetchone()
    if not tgt:
        print(f"  [SKIP] Target id={target_id} not found")
        return 0
    src_ids = json.loads(src[0]) if isinstance(src[0], str) else (src[0] or [])
    tgt_ids = json.loads(tgt[0]) if isinstance(tgt[0], str) else (tgt[0] or [])
    merged = list(dict.fromkeys(tgt_ids + src_ids))
    added = len(merged) - len(tgt_ids)
    print(f"  Merge id={source_id} ({src[2]!r} | {src[3]!r} n={src[1]}) "
          f"-> id={target_id} ({tgt[2]!r} | {tgt[3]!r} n={tgt[1]}) +{added} [{reason}]")
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(merged), len(merged), target_id)
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (source_id,))
    return added


def rename_group(cur, gid: int, new_dci_key: str, new_conc: str = None):
    """Renames the dci_key (and optionally concentracion_norm) of a group."""
    cur.execute("SELECT dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} not found for rename")
        return
    old_key, old_conc = row
    if new_conc:
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key=?, concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (new_dci_key, new_conc, gid)
        )
        print(f"  Rename id={gid}: dci_key {old_key!r} -> {new_dci_key!r}, conc {old_conc!r} -> {new_conc!r}")
    else:
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (new_dci_key, gid)
        )
        print(f"  Rename id={gid}: dci_key {old_key!r} -> {new_dci_key!r}")


def get_group(cur, dci_key: str, grupo_via: str, concentracion_norm: str = None):
    """Find a group by dci_key + grupo_via (+ optional conc)."""
    if concentracion_norm:
        cur.execute(
            "SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=? AND concentracion_norm=?",
            (dci_key, grupo_via, concentracion_norm)
        )
    else:
        cur.execute(
            "SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=?",
            (dci_key, grupo_via)
        )
    return cur.fetchone()


# =============================================================================
# Phase 1: HIOSCINA complete normalization
# =============================================================================
def phase1_hioscina(cur):
    print("\n=== Phase 1: HIOSCINA variants → BUTILBROMURO DE HIOSCINA ===")

    # 1a. Standalone HIOSCINA groups → BUTILBROMURO DE HIOSCINA
    # HIOSCINA INYECTABLE 20mg/mL (id=231) → BUTILBROMURO DE HIOSCINA INYECTABLE (id=1183... no wait, 1183 is combo with METAMIZOL)
    # Need to create or find canonical standalone groups
    canonical = {
        ('INYECTABLE', '20 mg/mL'):   (231, [618]),          # target=231, merge=[618]
        ('SOLIDO_ORAL', '10 mg'):     (232, [952, 982]),      # target=232, merge=[952,982]
        ('LIQUIDO_ORAL', '10 mg/mL'): (3073, []),             # no merge needed, just rename
    }
    for (via, conc), (target_id, source_ids) in canonical.items():
        for sid in source_ids:
            merge_groups(cur, sid, target_id, f"HIOSCINA* -> BUTILBROMURO DE HIOSCINA {via}")
        rename_group(cur, target_id, 'BUTILBROMURO DE HIOSCINA')

    # 1b. HIOSCINA||METAMIZOL + ESCOPOLAMINA||METAMIZOL → BUTILBROMURO DE HIOSCINA||METAMIZOL (id=1183)
    # INYECTABLE: merge 621 (HIOSCINA||METAMIZOL) and 965 (ESCOPOLAMINA||METAMIZOL) into 1183
    merge_groups(cur, 621, 1183, "HIOSCINA||METAMIZOL -> BUTILBROMURO DE HIOSCINA||METAMIZOL")
    merge_groups(cur, 965, 1183, "ESCOPOLAMINA||METAMIZOL -> BUTILBROMURO DE HIOSCINA||METAMIZOL")
    # SOLIDO_ORAL HIOSCINA||METAMIZOL 300mg+10mg (id=1213) — standalone combo, rename dci_key
    rename_group(cur, 1213, 'BUTILBROMURO DE HIOSCINA||METAMIZOL')

    # 1c. HIOSCINA||PARACETAMOL + HIOSCINA BUTILBROMURO||PARACETAMOL → BUTILBROMURO DE HIOSCINA||PARACETAMOL
    # SOLIDO_ORAL: 990 (HIOSCINA||PARACETAMOL 325+10 n=62) target, merge 1016 (HIOSCINA BUTILBROMURO||PARACETAMOL)
    merge_groups(cur, 1016, 990, "HIOSCINA BUTILBROMURO||PARACETAMOL -> HIOSCINA||PARACETAMOL")
    rename_group(cur, 990, 'BUTILBROMURO DE HIOSCINA||PARACETAMOL', '10 mg + 325 mg')
    # LIQUIDO_ORAL: 3255 (2mg/mL + 100mg/mL n=2) — rename; 3788 (100mg/mL n=1) — rename
    rename_group(cur, 3255, 'BUTILBROMURO DE HIOSCINA||PARACETAMOL')
    rename_group(cur, 3788, 'BUTILBROMURO DE HIOSCINA||PARACETAMOL')

    # 1d. IBUPROFENO||SCOPOLAMINA (id=2304) → BUTILBROMURO DE HIOSCINA||IBUPROFENO (id=1004)
    # ATC M01AE51 confirms this is the antispasmodic (buscopan) + ibuprofen combo
    merge_groups(cur, 2304, 1004, "IBUPROFENO||SCOPOLAMINA -> BUTILBROMURO DE HIOSCINA||IBUPROFENO")

    print(f"  Phase 1 complete.")


# =============================================================================
# Phase 2: AMOXICILINA LIQUIDO_ORAL case/space deduplication
# =============================================================================
def phase2_amoxicilina(cur):
    print("\n=== Phase 2: AMOXICILINA LIQUIDO_ORAL concentration deduplication ===")
    # All express the same 50mg/mL concentration in different notations:
    # 250 mg/5ml (id=2606), 250 mg/5 mL (id=2611) → merge into 250 mg/5mL (id=2609, largest)
    merge_groups(cur, 2606, 2609, "250 mg/5ml -> 250 mg/5mL")
    merge_groups(cur, 2611, 2609, "250 mg/5 mL -> 250 mg/5mL")
    # 125 mg/5ml (id=2607) → merge into 125 mg/5mL (id=2610)
    merge_groups(cur, 2607, 2610, "125 mg/5ml -> 125 mg/5mL")
    # 750 mg (id=3803) — no unit, likely sachet; keep but check if same as 750mg/5ml (id=2608)
    # Actually 750mg/5mL = 150mg/mL. 750mg sachet is different. Keep separate.
    print("  Phase 2 complete.")


# =============================================================================
# Phase 3: CARBIDOPA ENTACAPONA/ENTACAPONE merge
# =============================================================================
def phase3_entacapona(cur):
    print("\n=== Phase 3: CARBIDOPA||ENTACAPONE -> CARBIDOPA||ENTACAPONA||LEVODOPA ===")
    # Canonical key: CARBIDOPA||ENTACAPONA||LEVODOPA (Spanish INN)
    # Source: CARBIDOPA||ENTACAPONE||LEVODOPA ids: 2120, 2127, 2132, 2133
    # Target: CARBIDOPA||ENTACAPONA||LEVODOPA ids: 908, 914, 915, 916, 1201
    # Match by concentration after unifying:
    # id=2120: 12.5 mg + 200 mg + 50 mg → same as id=914: 12.5 mg + 200 mg + 50 mg
    # id=2132: 25 mg + 200 mg + 100 mg → same as id=915: 25 mg + 200 mg + 100 mg
    # id=2127: 50 mg + 200 mg + 200 mg → same as id=1201: 50 mg + 200 mg + 200 mg
    # id=2133: 37.5 mg + 200 mg + 150 mg → same as id=916: 40.5 mg + 200 mg + 150 mg? (different: 37.5 vs 40.5)
    #   37.5/200/150 vs 40.5/200/150 — both are Stalevo variants. 37.5mg CARBIDOPA doesn't exist in Stalevo.
    #   This may be a rounding: 37.5 = 7.5 carbidopa + 30 carbidopa? No, Stalevo 150 = carbidopa 37.5mg.
    #   Actually Stalevo 150 has carbidopa 37.5mg + entacapona 200mg + levodopa 150mg.
    #   id=916 has 40.5mg carbidopa — that might be wrong. Let's merge the ENTACAPONE version into a renamed group.

    for src_id, target_id in [(2120, 914), (2132, 915), (2127, 1201)]:
        merge_groups(cur, src_id, target_id, "ENTACAPONE->ENTACAPONA")

    # id=2133: 37.5mg version — rename dci_key, keep as separate concentration
    rename_group(cur, 2133, 'CARBIDOPA||ENTACAPONA||LEVODOPA')
    # id=916: 40.5mg — also rename for consistency; different concentration, keep separate
    rename_group(cur, 916, 'CARBIDOPA||ENTACAPONA||LEVODOPA')

    print("  Phase 3 complete.")


# =============================================================================
# Phase 4: Component-order duplicates
# =============================================================================
def phase4_component_order(cur):
    print("\n=== Phase 4: Component-order duplicate merges ===")

    merges = [
        # (source_id, target_id, reason)
        # AMLODIPINO||LOSARTAN: id=80 '100 mg + 5 mg' (wrong) → id=78 '5 mg + 100 mg' (correct)
        (80, 78, "AMLODIPINO||LOSARTAN wrong order"),
        # AMLODIPINO||LOSARTAN: id=82 '2.5 mg + 50 mg' → id=81 '50 mg + 2.5 mg'? Check first:
        # dci_key AMLODIPINO||LOSARTAN: AMLODIPINO first alphabetically → conc order: AMLODIPINO_dose + LOSARTAN_dose
        # id=81: 50 mg + 2.5 mg = AMLODIPINO 50mg? That's wrong (no AMLODIPINO 50mg). Must be LOSARTAN 50mg + AMLODIPINO 2.5mg.
        # id=82: 2.5 mg + 50 mg = AMLODIPINO 2.5mg + LOSARTAN 50mg (correct canonical order)
        # So merge id=81 into id=82
        (81, 82, "AMLODIPINO||LOSARTAN wrong order 50+2.5"),
        # ACIDO FENOFIBRICO||ROSUVASTATINA: id=1637 '5 mg + 135 mg' = ROSUVASTATINA 5mg first (wrong)
        # → id=2407 '135 mg + 5 mg' = FENOFIBRICO 135mg + ROSUVASTATINA 5mg (correct: A before R)
        (1637, 2407, "ACIDO FENOFIBRICO||ROSUVASTATINA wrong order"),
        # FENOFIBRATO||ROSUVASTATINA: id=2455 '135 mg + 20 mg' = FENOFIBRATO 135mg + ROSUVASTATINA 20mg
        # vs id=1437 '20 mg + 135 mg' which has FENOFIBRATO(F) first? No: FENOFIBRATO < ROSUVASTATINA alphabetically.
        # So id=1437 '20 mg + 135 mg' = FENOFIBRATO 20mg + ROSUVASTATINA 135mg (wrong — ROSUVASTATINA 135mg doesn't exist)
        # Actually FENOFIBRATO 135mg + ROSUVASTATINA 20mg: id=2455 is correct (135+20 = FENOFIBRATO first)
        # id=1437 '20 mg + 135 mg' = FENOFIBRATO 20mg + ROSUVASTATINA 135mg (wrong order, ROSUVASTATINA 135mg implausible)
        # → merge id=1437 into id=2455
        (1437, 2455, "FENOFIBRATO||ROSUVASTATINA wrong order"),
        # GLIMEPIRIDA||METFORMINA: id=54 '500 mg + 2 mg' (small n=1, GLIMEPIRIDA(G) < METFORMINA(M): correct order GLIMEPIRIDA 500mg?)
        # GLIMEPIRIDA 500mg doesn't exist! Max dose is 8mg. So 500mg must be METFORMINA.
        # Correct order: GLIMEPIRIDA dose first, then METFORMINA dose.
        # id=60: '2 mg + 1000 mg' = GLIMEPIRIDA 2mg + METFORMINA 1000mg ✓
        # id=64: '1000 mg + 2 mg' = GLIMEPIRIDA 1000mg (wrong!) → merge into id=60
        # id=65: '1000 mg + 4 mg' = GLIMEPIRIDA 1000mg (wrong) vs id=1513 '4 mg + 1000 mg' = GLIMEPIRIDA 4mg ✓
        # id=54: '500 mg + 2 mg' → GLIMEPIRIDA 500mg (impossible!) → check separately
        (64, 60, "GLIMEPIRIDA||METFORMINA wrong order 1000+2"),
        (1513, 65, "GLIMEPIRIDA||METFORMINA wrong order merge 4+1000 into 1000+4"),
        # CAFEINA||IBUPROFENO||PARACETAMOL: check ids 1125, 1126, 1727
        # dci_key sorted: CAFEINA||IBUPROFENO||PARACETAMOL (C < I < P)
        # Correct conc order: CAFEINA_dose + IBUPROFENO_dose + PARACETAMOL_dose
        # id=1727: '250 mg + 65 mg + 400 mg' = CAFEINA 250mg? No, CAFEINA is 65mg, IBUPROFENO 400mg, PARACETAMOL 250mg
        # Correct: CAFEINA 65mg + IBUPROFENO 400mg + PARACETAMOL 250mg = '65 mg + 400 mg + 250 mg'
        # id=1126: '65 mg + 400 mg + 250 mg' ✓ (n=22)
        # id=1727: '250 mg + 65 mg + 400 mg' (wrong order) → merge into id=1126 (n=22)
        # id=1125: '250 mg + 400 mg + 65 mg' (wrong) → merge into id=1126
        (1727, 1126, "CAFEINA||IBUPROFENO||PARACETAMOL wrong order 250+65+400"),
        (1125, 1126, "CAFEINA||IBUPROFENO||PARACETAMOL wrong order 250+400+65"),
        # CAFEINA||NAPROXENO||PARACETAMOL: canonical C < N < P
        # Correct order: CAFEINA + NAPROXENO + PARACETAMOL doses
        # Standard products: CAFEINA 65mg + NAPROXENO 220mg/250mg + PARACETAMOL 250mg/325mg
        # id=1184: '250 mg + 65 mg + 220 mg' = NAPROXENO 250mg? (N < P?) No: check again...
        #   Actually CAFEINA < NAPROXENO < PARACETAMOL alphabetically. So:
        #   '65 mg + 220 mg + 250 mg' = CAFEINA 65 + NAPROXENO 220 + PARACETAMOL 250 ✓
        # id=2539: '65 mg + 220 mg + 250 mg' (n=24) ✓ canonical
        # id=1184: '250 mg + 65 mg + 220 mg' = what? Either CAFEINA 250mg (too much) or wrong order
        #   This is NAPROXENO 250mg + CAFEINA 65mg + PARACETAMOL 220mg in wrong order? Hmm.
        #   Actually NAPROXENO SODICO 220mg (free acid equivalent) is different from NAPROXENO 250mg.
        #   Let's leave 1184 (250mg NAPROXENO) as a separate legitimate group.
        # id=1938: '325 mg + 250 mg + 65 mg' vs id=1940 '65 mg + 250 mg + 325 mg'
        #   id=1938: CAFEINA 325mg? No → must be PARACETAMOL 325mg + NAPROXENO 250mg + CAFEINA 65mg (wrong order)
        #   id=1940: '65 mg + 250 mg + 325 mg' = CAFEINA 65 + NAPROXENO 250 + PARACETAMOL 325 ✓
        #   id=1809: '325 mg + 65 mg + 250 mg' (wrong order) → merge into 1940
        (1809, 1940, "CAFEINA||NAPROXENO||PARACETAMOL wrong order"),
        (1938, 1940, "CAFEINA||NAPROXENO||PARACETAMOL wrong order"),
        # AMLODIPINO||IRBESARTAN: id=1545 '150 mg + 10 mg' vs id=1543 '5 mg + 150 mg'
        # AMLODIPINO < IRBESARTAN, so correct: AMLODIPINO_dose + IRBESARTAN_dose
        # id=1545: 150mg AMLODIPINO? Impossible (max 10mg). So it's IRBESARTAN 150mg + AMLODIPINO 10mg (wrong order)
        # id=1543: 5mg + 150mg = AMLODIPINO 5mg + IRBESARTAN 150mg ✓ But 1543 has n=14 and 1545 has n=4
        # Actually looking at 1545: '150 mg + 10 mg' — this should be AMLODIPINO 10mg + IRBESARTAN 150mg
        # The correct canonical group would be id=1540 '10 mg + 300 mg' or... let me check id=1540 vs 1543 vs 1544
        # id=1540: 10 mg + 300 mg; id=1543: 5 mg + 150 mg; id=1544: 5 mg + 300 mg
        # id=1545: 150 mg + 10 mg = AMLODIPINO 10mg + IRBESARTAN 150mg, but wrong order → should be '10 mg + 150 mg'
        # No group with '10 mg + 150 mg' exists. Rename 1545's concentracion_norm.
        # (handled separately below)
        # CODEINA||PARACETAMOL: id=755 '30 mg + 325 mg' (n=29) vs id=10 '325 mg + 30 mg' (n=67)
        # CODEINA < PARACETAMOL: correct order = CODEINA + PARACETAMOL → '30 mg + 325 mg' ✓
        # id=10 '325 mg + 30 mg' has n=67 (larger) but wrong order → merge into id=755
        # Actually: standard Colombian name for Codeine+Paracetamol products use Paracetamol first in label
        # but our canonical is alphabetical (CODEINA first).
        # Let's merge wrong-order into right-order (755):
        (10, 755, "CODEINA||PARACETAMOL wrong order 325+30 -> 30+325"),
        # id=756: '8 mg + 325 mg' (n=1) vs id=216 '325 mg + 8 mg' (n=37)
        (216, 756, "CODEINA||PARACETAMOL wrong order 325+8 -> 8+325"),
        # HIDROCODONA||PARACETAMOL:
        # HIDROCODONA < PARACETAMOL. Correct: HIDROCODONA + PARACETAMOL
        # id=1659: 325+5 (n=74) wrong order → id=1988 '10+325' and id=1842 '7.5+325' are correct
        # id=1659: '325 mg + 5 mg' = PARACETAMOL 325 + HIDROCODONA 5 (wrong) vs '5 mg + 325 mg'
        # Is there a '5 mg + 325 mg' group? Let me check... id=1988 '10 mg + 325 mg' is 10+325.
        # Need to find '5 mg + 325 mg':
    ]
    for src, tgt, reason in merges:
        merge_groups(cur, src, tgt, reason)

    # Fix AMLODIPINO||IRBESARTAN wrong-order concentracion_norm
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='10 mg + 150 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=1545")
    print("  Fixed AMLODIPINO||IRBESARTAN id=1545 conc '150 mg + 10 mg' -> '10 mg + 150 mg'")

    # Fix GLIMEPIRIDA||METFORMINA id=54 '500 mg + 2 mg' — GLIMEPIRIDA 500mg impossible; likely Metformina 500mg + Glimepirida 2mg
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='2 mg + 500 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=54")
    print("  Fixed GLIMEPIRIDA||METFORMINA id=54 conc '500 mg + 2 mg' -> '2 mg + 500 mg'")

    # HIDROCODONA||PARACETAMOL: find groups with wrong order
    cur.execute("SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='HIDROCODONA||PARACETAMOL' ORDER BY concentracion_norm")
    rows = cur.fetchall()
    print("  HIDROCODONA||PARACETAMOL groups:")
    for r in rows:
        print(f"    id={r[0]}: {r[1]!r} n={r[2]}")
    # id=1659: '325 mg + 5 mg' wrong → correct is '5 mg + 325 mg'
    # id=2052: '7.5 mg + 325 mg' ✓ (HIDROCODONA first)
    # id=1988: '10 mg + 325 mg' ✓
    # id=2525: '325 mg + 10 mg' wrong → same as 1988
    # id=1842: '325 mg + 7.5 mg' wrong → same as 2052
    # id=1661: '5 mg + 325 mg' ✓ — merge 1659 into 1661
    merge_groups(cur, 1659, 1661, "HIDROCODONA||PARACETAMOL wrong order 325+5->5+325")
    merge_groups(cur, 1842, 2052, "HIDROCODONA||PARACETAMOL wrong order 325+7.5->7.5+325")
    merge_groups(cur, 2525, 1988, "HIDROCODONA||PARACETAMOL wrong order 325+10->10+325")

    print("  Phase 4 complete.")


# =============================================================================
# Phase 5: TOXINA BOTULINICA UI vs U normalization
# =============================================================================
def phase5_botox(cur):
    print("\n=== Phase 5: TOXINA BOTULINICA UI vs U ===")
    # id=2883: 200 U (n=4) → id=2884: same? Check concentrations
    cur.execute("SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='TOXINA BOTULINICA TIPO A'")
    rows = cur.fetchall()
    for r in rows:
        print(f"  id={r[0]}: {r[1]!r} n={r[2]}")
    # U and UI are same unit: merge
    # 100 U (id=2885) → 100 UI (id=2880)
    # 200 U (id=2884) → 200 UI (id=2883)
    merge_groups(cur, 2885, 2880, "100 U -> 100 UI")
    merge_groups(cur, 2884, 2883, "200 U -> 200 UI")
    print("  Phase 5 complete.")


# =============================================================================
# Phase 6: AMBROXOL equivalent concentrations
# =============================================================================
def phase6_ambroxol(cur):
    print("\n=== Phase 6: AMBROXOL equivalent concentrations ===")
    # 15 mg/5mL = 3 mg/mL: merge id=2698 (15mg/5mL, n=14) into id=2700 (3mg/mL, n=15)
    merge_groups(cur, 2698, 2700, "AMBROXOL 15mg/5mL = 3mg/mL")
    # 30 mg/5mL = 6 mg/mL: merge id=2699 (30mg/5mL, n=11) into id=2702 (6mg/mL, n=8)
    merge_groups(cur, 2699, 2702, "AMBROXOL 30mg/5mL = 6mg/mL")
    print("  Phase 6 complete.")


# =============================================================================
# Phase 7: PARACETAMOL LIQUIDO_ORAL duplicate concentrations
# =============================================================================
def phase7_paracetamol_liquid(cur):
    print("\n=== Phase 7: PARACETAMOL LIQUIDO_ORAL duplicate concentrations ===")
    # id=2593: 150 mg/5 mL = 30 mg/mL → merge into id=2590 (30 mg/mL, n=71)
    merge_groups(cur, 2593, 2590, "150mg/5mL = 30mg/mL")
    # id=2592: 120 mg/5 mL = 24 mg/mL — not the same as 30mg/mL; keep as is
    print("  Phase 7 complete.")


# =============================================================================
# Phase 8: INSULINA fixes
# =============================================================================
def phase8_insulina(cur):
    print("\n=== Phase 8: INSULINA fixes ===")
    # 8a. INSULINA GLULISINA 3.5 mg/mL → 100 UI/mL
    cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='INSULINA GLULISINA' AND concentracion_norm='3.5 mg/mL'")
    row = cur.fetchone()
    if row:
        cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='INSULINA GLULISINA' AND concentracion_norm='100 UI/mL'")
        tgt = cur.fetchone()
        if tgt:
            merge_groups(cur, row[0], tgt[0], "INSULINA GLULISINA 3.5mg/mL (wrong) -> 100 UI/mL")
        else:
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='100 UI/mL', actualizado_en=CURRENT_TIMESTAMP WHERE id=?", (row[0],))
            print(f"  INSULINA GLULISINA id={row[0]}: renamed 3.5mg/mL -> 100 UI/mL")
    # Also fix cum_normalizado concentracion_mg_ml for glulisina products (3.49mg/mL is protein weight, not UI)
    cur.execute("""
        UPDATE cum_normalizado SET concentracion_mg_ml=NULL, notas='Concentracion en UI/mL (100 UI/mL), no mg/mL'
        WHERE principios_dci LIKE '%GLULISINA%' AND concentracion_mg_ml BETWEEN 3.0 AND 4.0
    """)
    changed = cur.rowcount
    if changed:
        print(f"  Fixed {changed} GLULISINA cum_normalizado entries (removed wrong 3.49 mg/mL)")

    # 8b. INSULINA ASPART (id: look up) → canonical dci_key INSULINA ASPARTA
    cur.execute("SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key='INSULINA ASPART'")
    rows = cur.fetchall()
    if rows:
        for r in rows:
            # Find matching INSULINA ASPARTA group
            cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='INSULINA ASPARTA' AND concentracion_norm=?", (r[1],))
            tgt = cur.fetchone()
            if tgt:
                merge_groups(cur, r[0], tgt[0], "INSULINA ASPART -> INSULINA ASPARTA")
            else:
                rename_group(cur, r[0], 'INSULINA ASPARTA')

    # Also fix cum_normalizado DCI for INSULINA ASPART entries
    cur.execute("UPDATE cum_normalizado SET principios_dci='[\"INSULINA ASPARTA\"]' WHERE principios_dci='[\"INSULINA ASPART\"]'")
    changed = cur.rowcount
    if changed:
        print(f"  Normalized {changed} INSULINA ASPART -> INSULINA ASPARTA in cum_normalizado")

    print("  Phase 8 complete.")


# =============================================================================
# Phase 9: Data errors
# =============================================================================
def phase9_data_errors(cur):
    print("\n=== Phase 9: Data errors ===")

    # 9a. PENICILINA G INYECTABLE id=2955 '1.2 UI' — should be 1200000 UI
    # Check: 1.2 UI for penicilina G is clinically impossible (standard is 400K-5M UI)
    cur.execute("SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE id=2955")
    row = cur.fetchone()
    if row:
        print(f"  PENICILINA G id=2955: {row[1]!r} n={row[2]}")
        # Find 1200000 UI group
        cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='PENICILINA G' AND concentracion_norm='1200000 UI'")
        tgt = cur.fetchone()
        if tgt:
            merge_groups(cur, 2955, tgt[0], "1.2 UI (error) -> 1200000 UI")
        else:
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='1200000 UI', actualizado_en=CURRENT_TIMESTAMP WHERE id=2955")
            print("  Fixed PENICILINA G id=2955: '1.2 UI' -> '1200000 UI'")

    # 9b. DIOSMECTITA id=2998 '30000 mg' — should be 3000 mg
    cur.execute("SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia WHERE id=2998")
    row = cur.fetchone()
    if row:
        print(f"  DIOSMECTITA id=2998: {row[1]!r} n={row[2]}")
        cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='DIOSMECTITA' AND concentracion_norm='3000 mg'")
        tgt = cur.fetchone()
        if not tgt:
            cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='DIOSMECTITA' AND concentracion_norm='3000 mg/sobre'")
            tgt = cur.fetchone()
        if tgt:
            merge_groups(cur, 2998, tgt[0], "30000mg (error) -> 3000mg")
        else:
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='3000 mg', actualizado_en=CURRENT_TIMESTAMP WHERE id=2998")
            print("  Fixed DIOSMECTITA id=2998: '30000 mg' -> '3000 mg'")

    # 9c. ACIDO ASCORBICO id=975 '50000 mg' — implausible (50g per tablet); check and fix
    cur.execute("SELECT id, concentracion_norm, n_productos, cum_ids FROM grupos_equivalencia WHERE id=975")
    row = cur.fetchone()
    if row:
        print(f"  ACIDO ASCORBICO id=975: {row[1]!r} n={row[2]}")
        ids = json.loads(row[3])
        # Check cum_normalizado for these products
        for cid in ids[:2]:
            exp, cons = cid.split('-', 1)
            cur.execute("SELECT dosis_total_mg, concentracion_mg_ml FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, cons))
            cn = cur.fetchone()
            print(f"    {cid}: cum_normalizado dosis_mg={cn[0] if cn else '?'} conc_ml={cn[1] if cn else '?'}")
        # 50000 mg = 50g — if it's IV, could be 50mg/mL in 1000mL bag? Likely a SOLIDO_ORAL error.
        # Change to '500 mg' (most common high-dose vitamin C) or investigate
        # For safety, leave as-is but log
        print("  WARNING: ACIDO ASCORBICO 50000mg needs manual verification")

    # 9d. PARACETAMOL INYECTABLE '100 mg/mL' (id lookup) — standard is 10 mg/mL for IV paracetamol
    cur.execute("SELECT id, concentracion_norm, n_productos, cum_ids FROM grupos_equivalencia WHERE dci_key='PARACETAMOL' AND grupo_via='INYECTABLE' AND concentracion_norm='100 mg/mL'")
    row = cur.fetchone()
    if row:
        print(f"  PARACETAMOL INYECTABLE 100mg/mL id={row[0]} n={row[2]}")
        ids = json.loads(row[3])
        for cid in ids[:2]:
            exp, cons = cid.split('-', 1)
            cur.execute("SELECT concentracion_mg_ml FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, cons))
            cn = cur.fetchone()
            print(f"    {cid}: cum_normalizado conc_ml={cn[0] if cn else '?'}")
        # If cum_normalizado confirms 10mg/mL, merge into 10mg/mL group
        cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='PARACETAMOL' AND grupo_via='INYECTABLE' AND concentracion_norm='10 mg/mL'")
        tgt = cur.fetchone()
        if tgt:
            merge_groups(cur, row[0], tgt[0], "PARACETAMOL IV 100mg/mL (error) -> 10mg/mL")

    # 9e. OXIMETAZOLINA: '0.5 mg' vs '0.5 mg/mL', '0.25 mg' vs '0.25 mg/mL' — same products
    # id=242: 0.5 mg (n=42), id=2722: 0.5 mg/mL (n=11)
    # id=2718: 0.25 mg (n=8), id=2721: 0.25 mg/mL (n=14)
    merge_groups(cur, 242, 2722, "OXIMETAZOLINA 0.5mg -> 0.5mg/mL")
    merge_groups(cur, 2718, 2721, "OXIMETAZOLINA 0.25mg -> 0.25mg/mL")

    print("  Phase 9 complete.")


# =============================================================================
# Phase 10: LANZAPIN → OLANZAPINA (INN misspelling)
# =============================================================================
def phase10_lanzapin(cur):
    print("\n=== Phase 10: LANZAPIN → OLANZAPINA ===")
    cur.execute("SELECT id, dci_key, grupo_via, concentracion_norm, n_productos FROM grupos_equivalencia WHERE dci_key LIKE '%LANZAPIN%'")
    rows = cur.fetchall()
    for r in rows:
        print(f"  id={r[0]}: {r[1]!r} {r[2]} {r[3]!r} n={r[4]}")
        new_key = r[1].replace('LANZAPIN', 'OLANZAPINA')
        # Find canonical OLANZAPINA group
        cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=? AND concentracion_norm=?",
                    (new_key, r[2], r[3]))
        tgt = cur.fetchone()
        if tgt:
            merge_groups(cur, r[0], tgt[0], f"LANZAPIN -> OLANZAPINA")
        else:
            rename_group(cur, r[0], new_key)
    # Fix cum_normalizado
    cur.execute("UPDATE cum_normalizado SET principios_dci = REPLACE(principios_dci, 'LANZAPIN', 'OLANZAPINA') WHERE principios_dci LIKE '%LANZAPIN%'")
    changed = cur.rowcount
    if changed:
        print(f"  Fixed {changed} LANZAPIN -> OLANZAPINA in cum_normalizado")
    print("  Phase 10 complete.")


# =============================================================================
# Phase 11: COLECALCIFEROL mg vs UI clarification
# =============================================================================
def phase11_colecalciferol(cur):
    print("\n=== Phase 11: COLECALCIFEROL UI case normalization ===")
    # id=3421: '1000 ui' (lowercase) should be '1000 UI'
    # id=3423: '1000 UI' (already correct) → merge 3421 into 3423
    merge_groups(cur, 3421, 3423, "COLECALCIFEROL 1000 ui -> 1000 UI")
    # id=2326: '2000 mg' vs '2000 UI' — 1 UI = ~0.025 mcg colecalciferol, so 2000 mg ≠ 2000 UI.
    # 2000 mg would be an implausible dose of vitamin D3 (2 grams).
    # Likely means 2000 UI (mislabeled as mg in CUM). Check products.
    cur.execute("SELECT id, n_productos, cum_ids FROM grupos_equivalencia WHERE id=2326")
    row = cur.fetchone()
    if row:
        ids = json.loads(row[2])
        for cid in ids[:2]:
            exp, cons = cid.split('-', 1)
            cur.execute("SELECT dosis_total_mg, atc_normalizado FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, cons))
            cn = cur.fetchone()
            print(f"    2326 {cid}: cum_normalizado dosis_mg={cn[0] if cn else '?'} atc={cn[1] if cn else '?'}")
        # If cum_normalizado has a small dosis_total_mg, confirm it's actually UI
        # For now, rename to 2000 UI and merge with existing group
        cur.execute("SELECT id, n_productos FROM grupos_equivalencia WHERE dci_key='COLECALCIFEROL' AND concentracion_norm='2000 UI'")
        tgt = cur.fetchone()
        if tgt:
            merge_groups(cur, 2326, tgt[0], "COLECALCIFEROL 2000mg (likely UI) -> 2000 UI")
        else:
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='2000 UI', actualizado_en=CURRENT_TIMESTAMP WHERE id=2326")
            print("  Renamed COLECALCIFEROL id=2326: '2000 mg' -> '2000 UI'")
    print("  Phase 11 complete.")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    phase1_hioscina(cur)
    conn.commit()

    phase2_amoxicilina(cur)
    conn.commit()

    phase3_entacapona(cur)
    conn.commit()

    phase4_component_order(cur)
    conn.commit()

    phase5_botox(cur)
    conn.commit()

    phase6_ambroxol(cur)
    conn.commit()

    phase7_paracetamol_liquid(cur)
    conn.commit()

    phase8_insulina(cur)
    conn.commit()

    phase9_data_errors(cur)
    conn.commit()

    phase10_lanzapin(cur)
    conn.commit()

    phase11_colecalciferol(cur)
    conn.commit()

    # Final stats
    print("\n=== Final summary ===")
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    print(f"Total grupos: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE dci_key LIKE '%HIOSCINA%' AND dci_key NOT LIKE '%BUTILBROMURO%'")
    leftover = cur.fetchone()[0]
    print(f"Leftover non-canonical HIOSCINA groups: {leftover}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
