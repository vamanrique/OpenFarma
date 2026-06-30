"""
fix_auditoria_conc103.py — Centésimotercera ronda de auditoría.

Completa la normalización de radiofármacos diagnósticos V09 con prefijo TECNECIO (99MTC).
Convención establecida en rondas 99-101: todos los kits Tc-99m usan el INN del
compuesto final marcado, no el del ligando/sal precursor.

  A) EXAMETAZIMA → TECNECIO (99MTC) EXAMETAZIMA (Ceretec, V09AA01, HMPAO brain scan):
     id=1255: EXAMETAZIMA | INYECTABLE | 0.5 mg | n=5 (Ceretec 500mcg, GE Healthcare)
     id=763 ya tiene el nombre correcto (Leuco-Scint 0.2mg). No merge (conc distintas).

  B) ACIDO MEDRONICO → TECNECIO (99MTC) MEDRONATO (V09BA02, MDP bone scan):
     "Medronic acid" → INN radiofármaco: "technetium (99mTc) medronate" → MEDRONATO.
     Análogo a ACIDO PENTETICO→PENTETATO, ACIDO DIMERCAPTOSUCCINICO→SUCCIMERO.
       id=696:  ACIDO MEDRONICO | INYECTABLE | 10 mg | n=2 (Rotop-MDP, Tc MDP Kit)
       id=2230: ACIDO MEDRONICO | INYECTABLE |  5 mg | n=1
     No merge entre sí (concentraciones distintas).

  C) MEBROFENINA → TECNECIO (99MTC) MEBROFENINA (V09DA04, hepatobiliary scan):
     Mebrofenina = ácido N-(2,4,5-trimetilfenilcarbamoilmetil)iminodiacético (TRIMIDA).
     INN OMS: mebrofenin → MEBROFENINA. El kit se etiqueta Tc-99m en el momento de uso.
       id=1450: MEBROFENINA | INYECTABLE | 20 mg | n=1 (Poltechmbrida, Institute Atomic Energy)
       id=2220: MEBROFENINA | INYECTABLE | 4.5 mg/mL | n=2 (Sun Pharma kit Mebrofenina-Tc99m)
       id=2569: MEBROFENINA | INYECTABLE | 40 mg | n=1 (Bilio-Tec, Seligde)
     No merge entre sí (concentraciones distintas).

  D) TETRAFOSMINA → TECNECIO (99MTC) TETROFOSMINA (V09GA02, myocardial perfusion):
     Myoview (GE Healthcare) = kit para Tc-99m tetrofosmin (EANM/EMA: tetrofosmin).
     La DB tenía "TETRAFOSMINA" que es typo — el INN OMS es "tetrofosmin" →
     INN-Sp: "TETROFOSMINA" (no TETRAFOSMINA; el prefijo es "tetro" de tetraétil-fosfonato).
       id=527: TETRAFOSMINA | INYECTABLE | 0.2 mg | n=4 (Myoview, GE Healthcare)

  E) PIROFOSFATO DE SODIO → TECNECIO (99MTC) PIROFOSFATO (V09GA06, bone/cardiac):
     Technescan PYP = kit para Tc-99m pyrophosphate (PYP gated cardiac/bone scan).
     SODIO es el contraión del kit — no parte del INN del radiofármaco final.
     INN: "technetium (99mTc) pyrophosphate" → TECNECIO (99MTC) PIROFOSFATO.
       id=2462: PIROFOSFATO DE SODIO | INYECTABLE | 20 mg | n=1 (Technescan PYP)
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


def safe_json(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def rename_group(con, gid: int, new_dci: str, dry_run: bool = False) -> bool:
    cur = con.cursor()
    cur.execute(
        "SELECT id, dci_key, concentracion_norm, n_productos, cum_ids FROM grupos_equivalencia WHERE id=?",
        (gid,),
    )
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} not found")
        return False

    old_dci, conc, n_prod, cum_ids_json = row[1], row[2], row[3], row[4]
    cum_ids = safe_json(cum_ids_json)
    new_parts = new_dci.split("||")
    print(f"  id={gid}: '{old_dci}' → '{new_dci}' | {conc} | n={n_prod}")

    if dry_run:
        return True

    # Update grupos_equivalencia
    cur.execute(
        "UPDATE grupos_equivalencia SET dci_key=? WHERE id=?",
        (new_dci, gid),
    )

    # Update cum_normalizado principios_dci
    updated = 0
    for cid in cum_ids:
        if "-" not in cid:
            continue
        exp, consec = cid.split("-", 1)
        cur.execute(
            "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
            (json.dumps(new_parts, ensure_ascii=False), exp, consec),
        )
        updated += cur.rowcount
    print(f"    cum_normalizado: {updated}/{len(cum_ids)} rows updated")

    # Check for duplicate dci_key+grupo_via+conc after rename
    cur.execute(
        "SELECT id FROM grupos_equivalencia WHERE dci_key=? AND grupo_via=? AND concentracion_norm=? AND id!=?",
        (new_dci, row[0], conc, gid),  # row[0] is the id
    )
    # Actually row is (id, dci_key, conc, n_prod, cum_ids_json)
    cur.execute(
        "SELECT id FROM grupos_equivalencia WHERE dci_key=? AND concentracion_norm=? AND id!=?",
        (new_dci, conc, gid),
    )
    dups = cur.fetchall()
    if dups:
        print(f"    [WARN] Posibles duplicados tras rename: ids={[d[0] for d in dups]}")

    return True


def check_group(cur, gid: int):
    cur.execute(
        "SELECT id, dci_key, grupo_via, concentracion_norm, n_productos FROM grupos_equivalencia WHERE id=?",
        (gid,),
    )
    r = cur.fetchone()
    if r:
        print(f"  id={r[0]} | {r[1]} | {r[2]} | {r[3]} | n={r[4]}")
    else:
        print(f"  id={gid}: NOT FOUND")


def main(dry_run: bool = False):
    con = sqlite3.connect(DB_PATH)
    mode = "[DRY-RUN]" if dry_run else "[APPLY]"
    print(f"\n=== Ronda 103 {mode} ===\n")

    # A) EXAMETAZIMA → TECNECIO (99MTC) EXAMETAZIMA
    print("A) EXAMETAZIMA → TECNECIO (99MTC) EXAMETAZIMA")
    rename_group(con, 1255, "TECNECIO (99MTC) EXAMETAZIMA", dry_run)
    print()

    # B) ACIDO MEDRONICO → TECNECIO (99MTC) MEDRONATO
    print("B) ACIDO MEDRONICO → TECNECIO (99MTC) MEDRONATO")
    rename_group(con, 696, "TECNECIO (99MTC) MEDRONATO", dry_run)
    rename_group(con, 2230, "TECNECIO (99MTC) MEDRONATO", dry_run)
    print()

    # C) MEBROFENINA → TECNECIO (99MTC) MEBROFENINA
    print("C) MEBROFENINA → TECNECIO (99MTC) MEBROFENINA")
    rename_group(con, 1450, "TECNECIO (99MTC) MEBROFENINA", dry_run)
    rename_group(con, 2220, "TECNECIO (99MTC) MEBROFENINA", dry_run)
    rename_group(con, 2569, "TECNECIO (99MTC) MEBROFENINA", dry_run)
    print()

    # D) TETRAFOSMINA → TECNECIO (99MTC) TETROFOSMINA
    print("D) TETRAFOSMINA → TECNECIO (99MTC) TETROFOSMINA")
    rename_group(con, 527, "TECNECIO (99MTC) TETROFOSMINA", dry_run)
    print()

    # E) PIROFOSFATO DE SODIO → TECNECIO (99MTC) PIROFOSFATO
    print("E) PIROFOSFATO DE SODIO → TECNECIO (99MTC) PIROFOSFATO")
    rename_group(con, 2462, "TECNECIO (99MTC) PIROFOSFATO", dry_run)
    print()

    if not dry_run:
        con.commit()
        print("Commit OK.\n")

    print("=== Verificación final ===")
    cur = con.cursor()
    for gid in [763, 1255, 696, 2230, 1450, 2220, 2569, 527, 2462]:
        check_group(cur, gid)

    con.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
