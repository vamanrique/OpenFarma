"""
fix_auditoria_conc104.py — Centésimonovena ronda de auditoría.

  A) IOPRAMIDA → IOPROMIDA (WHO INN: iopromide, V08AB05):
     Ambos grupos son Ultravist (Bayer). La DB tenía typo 'IOPRAMIDA' para
     Ultravist 300 (id=1223); Ultravist 370 (id=1231) ya tenía 'IOPROMIDA'.
     No merge: concentraciones distintas (623.4 ≠ 768.9 mg/mL).
       id=1223: IOPRAMIDA | INYECTABLE | 623.4 mg/mL | n=5 → IOPROMIDA

  B) ALBUMINA SERICA HUMANA NANOCOLOIDE → TECNECIO (99MTC) ALBUMINA SERICA HUMANA NANOCOLOIDE:
     Nano-Albumon (Medi-Radiopharma, ATC V09DB01) y Rotop NanoHSA (Seligde, V09GA04)
     son kits para preparación de Tc-99m albumin nanocolloid (nanocol SPECT).
     Siguen la convención V09: el INN incluye el radionucleido.
       id=1932: ALBUMINA SERICA HUMANA NANOCOLOIDE | INYECTABLE | 1 mg   | n=1 (Nano-Albumon)
       id=1953: ALBUMINA SERICA HUMANA NANOCOLOIDE | INYECTABLE | 0.5 mg | n=4 (Rotop NanoHSA)
     No merge entre sí: concentraciones distintas y ATC distintos (V09DB01 ≠ V09GA04).
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"


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

    cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_dci, gid))

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

    # Check for duplicates after rename
    cur.execute(
        "SELECT id FROM grupos_equivalencia WHERE dci_key=? AND concentracion_norm=? AND id!=?",
        (new_dci, conc, gid),
    )
    dups = cur.fetchall()
    if dups:
        print(f"    [WARN] Posibles duplicados: ids={[d[0] for d in dups]}")

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
    print(f"\n=== Ronda 104 {mode} ===\n")

    # A) IOPRAMIDA → IOPROMIDA
    print("A) IOPRAMIDA → IOPROMIDA")
    rename_group(con, 1223, "IOPROMIDA", dry_run)
    print()

    # B) ALBUMINA SERICA HUMANA NANOCOLOIDE → TECNECIO (99MTC) ALBUMINA SERICA HUMANA NANOCOLOIDE
    print("B) ALBUMINA SERICA HUMANA NANOCOLOIDE → TECNECIO (99MTC) ALBUMINA SERICA HUMANA NANOCOLOIDE")
    rename_group(con, 1932, "TECNECIO (99MTC) ALBUMINA SERICA HUMANA NANOCOLOIDE", dry_run)
    rename_group(con, 1953, "TECNECIO (99MTC) ALBUMINA SERICA HUMANA NANOCOLOIDE", dry_run)
    print()

    if not dry_run:
        con.commit()
        print("Commit OK.\n")

    print("=== Verificación final ===")
    cur = con.cursor()
    for gid in [1223, 1231, 1932, 1953]:
        check_group(cur, gid)

    con.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
