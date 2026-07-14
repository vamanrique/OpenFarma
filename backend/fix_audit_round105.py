"""
Comprehensive audit fix script - Round 105
Fixes normalization issues found in grupos_equivalencia table.
"""
import sqlite3
import json

DB_PATH = 'openfarma.db'

def run_fixes():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("=== OpenFarma AUDIT FIX ROUND 105 ===")
    print()

    fixes_applied = 0

    # Fix 1: ID 3256 - TRIGLICERIDOS DE CADENA MEDIANA -> TRIGLICERIDOS DE CADENA MEDIA
    # 'MEDIANA' is wrong; WHO INN is 'medium-chain triglycerides' = TRIGLICERIDOS DE CADENA MEDIA
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia WHERE id=3256")
    row = cur.fetchone()
    if row:
        old_dci = row[1]
        new_dci = old_dci.replace('TRIGLICERIDOS DE CADENA MEDIANA', 'TRIGLICERIDOS DE CADENA MEDIA')
        if old_dci != new_dci:
            # Check for potential duplicate
            cur.execute("SELECT id FROM grupos_equivalencia WHERE dci_key=? AND id!=3256", (new_dci,))
            dup = cur.fetchone()
            if dup:
                print(f"SKIP ID 3256: would create duplicate with ID {dup[0]}")
            else:
                cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=3256", (new_dci,))
                print(f"FIX ID 3256: dci_key TRIGLICERIDOS DE CADENA MEDIANA -> TRIGLICERIDOS DE CADENA MEDIA")
                print(f"  Old: {old_dci}")
                print(f"  New: {new_dci}")
                fixes_applied += 1
        else:
            print("ID 3256: already correct (no MEDIANA found)")
    else:
        print("ID 3256: not found")

    print()

    # Fix 2: ID 3432 - GELATINA SUCCILINADA -> GELATINA SUCCINILADA
    # Correct spelling: succinylated gelatin = GELATINA SUCCINILADA
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia WHERE id=3432")
    row = cur.fetchone()
    if row:
        old_dci = row[1]
        new_dci = old_dci.replace('GELATINA SUCCILINADA', 'GELATINA SUCCINILADA')
        if old_dci != new_dci:
            cur.execute("SELECT id FROM grupos_equivalencia WHERE dci_key=? AND id!=3432", (new_dci,))
            dup = cur.fetchone()
            if dup:
                print(f"SKIP ID 3432: would create duplicate with ID {dup[0]}")
            else:
                cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=3432", (new_dci,))
                print(f"FIX ID 3432: GELATINA SUCCILINADA -> GELATINA SUCCINILADA")
                print(f"  Old: {old_dci}")
                print(f"  New: {new_dci}")
                fixes_applied += 1
        else:
            print("ID 3432: already correct (no SUCCILINADA found)")
    else:
        print("ID 3432: not found")

    print()

    # Fix 3: ID 3685 - SULFATO DE SODIO ANHIDRO -> SULFATO DE SODIO
    # ANHIDRO (anhydrous) is a physical form descriptor, not part of the INN
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia WHERE id=3685")
    row = cur.fetchone()
    if row:
        old_dci = row[1]
        new_dci = old_dci.replace('SULFATO DE SODIO ANHIDRO', 'SULFATO DE SODIO')
        if old_dci != new_dci:
            cur.execute(
                "SELECT id FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=(SELECT grupo_via FROM grupos_equivalencia WHERE id=3685) AND concentracion_norm=(SELECT concentracion_norm FROM grupos_equivalencia WHERE id=3685) AND id!=3685",
                (new_dci,))
            dup = cur.fetchone()
            if dup:
                print(f"SKIP ID 3685: would create duplicate with ID {dup[0]}")
            else:
                cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=3685", (new_dci,))
                print(f"FIX ID 3685: SULFATO DE SODIO ANHIDRO -> SULFATO DE SODIO")
                print(f"  Old: {old_dci}")
                print(f"  New: {new_dci}")
                fixes_applied += 1
        else:
            print("ID 3685: already correct (no ANHIDRO found)")
    else:
        print("ID 3685: not found")

    print()

    # Fix 4: ID 3708 - SULFATO DE SODIO ANHIDRO -> SULFATO DE SODIO
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia WHERE id=3708")
    row = cur.fetchone()
    if row:
        old_dci = row[1]
        new_dci = old_dci.replace('SULFATO DE SODIO ANHIDRO', 'SULFATO DE SODIO')
        if old_dci != new_dci:
            cur.execute(
                "SELECT id FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=(SELECT grupo_via FROM grupos_equivalencia WHERE id=3708) AND concentracion_norm=(SELECT concentracion_norm FROM grupos_equivalencia WHERE id=3708) AND id!=3708",
                (new_dci,))
            dup = cur.fetchone()
            if dup:
                print(f"SKIP ID 3708: would create duplicate with ID {dup[0]}")
            else:
                cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=3708", (new_dci,))
                print(f"FIX ID 3708: SULFATO DE SODIO ANHIDRO -> SULFATO DE SODIO")
                print(f"  Old: {old_dci}")
                print(f"  New: {new_dci}")
                fixes_applied += 1
        else:
            print("ID 3708: already correct")
    else:
        print("ID 3708: not found")

    print()

    # Fix 5: ID 2995 - concentracion_norm '3000 mg/sobre' -> '3000 mg'
    # '/sobre' is non-standard unit; 'sobre' = sachet in Spanish
    # Standard concentration should be just '3000 mg'
    cur.execute("SELECT id, concentracion_norm FROM grupos_equivalencia WHERE id=2995")
    row = cur.fetchone()
    if row:
        old_conc = row[1]
        new_conc = '3000 mg'
        if old_conc == '3000 mg/sobre':
            # Check for potential duplicate
            cur.execute(
                "SELECT id FROM grupos_equivalencia WHERE dci_key='DIOSMECTITA' AND grupo_via='LIQUIDO_ORAL' AND concentracion_norm='3000 mg' AND id!=2995")
            dup = cur.fetchone()
            if dup:
                print(f"SKIP ID 2995: would create duplicate with ID {dup[0]}")
            else:
                cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=2995", (new_conc,))
                print(f"FIX ID 2995: concentracion_norm '3000 mg/sobre' -> '3000 mg'")
                fixes_applied += 1
        else:
            print(f"ID 2995: concentration is '{old_conc}', not '3000 mg/sobre' - skipping")
    else:
        print("ID 2995: not found")

    print()

    conn.commit()
    print(f"=== COMMITTED {fixes_applied} fixes ===")
    print()

    # Verify the fixes
    print("=== VERIFICATION ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id IN (3256, 3432, 3685, 3708, 2995) ORDER BY id")
    for row in cur.fetchall():
        print(f"  ID {row[0]}: dci=[{row[1][:60]}...] conc={row[2]}")

    # Run WAL checkpoint
    print()
    print("Running WAL checkpoint...")
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    result = cur.fetchone()
    print(f"Checkpoint result: {result}")

    conn.close()
    print()
    print("Done.")


if __name__ == '__main__':
    run_fixes()
