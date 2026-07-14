"""
fix_auditoria_conc96.py — Nonagésimosexta ronda de auditoría.

  A) HEPARINA | INYECTABLE | '25 UI' (id=2670) → SIN_CONCENTRACION:
     Error de parseo ETL: '25.000 Ui' (veinticinco mil) parseado como '25'
     (el separador de miles '.' interpretado como decimal). El grupo contiene
     mezcla de presentaciones: 25.000 UI vial total, 5.000 UI/mL ampolla, etc.
     → SIN_CONCENTRACION → auto-merge con id=2672 (HEPARINA|INYECT|SIN_CONC, 2 prod).

  B) Normalización CLONIXINA — INN OMS: clonixin → CLONIXINA (no sal):
     Las siguientes presentaciones deben usar el INN base 'CLONIXINA',
     no las formas de sal 'CLONIXINATO' ni 'CLONIXINATO DE LISINA':

     Grupos solo-clonixin:
       id=2271: CLONIXINATO DE LISINA | SOLIDO_ORAL | 125mg | n=2
       → CLONIXINA → auto-merge con id=2269 (CLONIXINA|SOLIDO_ORAL|125mg, 1 prod)

     Ciclobenzaprina combos (5mg+125mg, mismo grupo tras merge):
       id=660:  CICLOBENZAPRINA||CLONIXINATO DE LISINA → CICLOBENZAPRINA||CLONIXINA
       id=2273: CICLOBENZAPRINA||CLONIXINATO → CICLOBENZAPRINA||CLONIXINA
       → auto-merge ambos con id=656 (CICLOBENZAPRINA||CLONIXINA, 13 prod)

     Otras combinaciones (no hacen auto-merge entre sí por vías/INNs distintos):
       id=529:  CLONIXINATO DE LISINA||PROPIONAZINA → CLONIXINA||PROPIONAZINA (SOLIDO_ORAL)
       id=531:  CLONIXINATO DE LISINA||ERGOTAMINA → CLONIXINA||ERGOTAMINA
       id=535:  CLONIXINATO DE LISINA||PROPINOX → CLONIXINA||PROPINOX
       id=2267: CLONIXINATO DE LISINA||PARGEVERINA → CLONIXINA||PARGEVERINA
       id=2541: CLONIXINATO DE LISINA||PROPIONAZINA → CLONIXINA||PROPIONAZINA (INYECTABLE)
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"


def safe_json(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP merge] {del_id}->{keep_id}: missing")
        return 0
    merged = list(dict.fromkeys(safe_json(keep[0]) + safe_json(rem[0])))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}->{keep_id}: total={len(merged)}")
    return 1


def fix_concentration(con, gid: int, new_conc: str) -> int:
    cur = con.cursor()
    cur.execute("SELECT dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_conc = row[1]
    if old_conc == new_conc:
        print(f"  [OK ya] id={gid}: conc already {new_conc}")
        return 0
    if new_conc == "SIN_CONCENTRACION":
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=?, concentracion_valor=NULL, concentracion_unidad=NULL WHERE id=?",
                    (new_conc, gid))
    else:
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [FIX_CONC] id={gid} ({row[0][:40]}): '{old_conc}' -> '{new_conc}'")
    return 1


def rename_component(con, gid: int, old_component: str, new_component: str) -> int:
    """Rename one component within a (possibly multi-component) dci_key."""
    cur = con.cursor()
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_dci = row[0]
    parts = old_dci.split("||")
    if old_component not in parts:
        print(f"  [SKIP] id={gid}: '{old_component}' not in '{old_dci[:50]}'")
        return 0
    new_parts = [new_component if p == old_component else p for p in parts]
    new_dci = "||".join(sorted(new_parts))
    if new_dci == old_dci:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_dci, gid))
    print(f"  [RENAME] id={gid}: '{old_dci}' -> '{new_dci}'")
    # Sync cum_normalizado
    cids = safe_json(row[1])
    updated = 0
    for cid in cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                    (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = safe_json(p[0])
            new_pdci = [new_component if d == old_component else d for d in pdci]
            new_pdci = list(dict.fromkeys(new_pdci))
            if new_pdci != pdci:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(new_pdci), exp, consec))
                updated += 1
    if updated:
        print(f"    cum_normalizado: {updated} productos actualizados")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # A. HEPARINA 25 UI → SIN_CONCENTRACION
    print("\n=== A. HEPARINA 25 UI -> SIN_CONCENTRACION ===")
    n['A'] += fix_concentration(con, 2670, "SIN_CONCENTRACION")

    # B. CLONIXINATO/CLONIXINATO DE LISINA → CLONIXINA
    print("\n=== B. CLONIXINATO → CLONIXINA normalization ===")

    # Solo groups
    print("\n  -- Solo clonixin --")
    n['B'] += rename_component(con, 2271, "CLONIXINATO DE LISINA", "CLONIXINA")

    # Cyclobenzaprine combos
    print("\n  -- Ciclobenzaprina combos --")
    n['B'] += rename_component(con, 660, "CLONIXINATO DE LISINA", "CLONIXINA")
    n['B'] += rename_component(con, 2273, "CLONIXINATO", "CLONIXINA")

    # Other combos
    print("\n  -- Other combos --")
    n['B'] += rename_component(con, 529, "CLONIXINATO DE LISINA", "CLONIXINA")
    n['B'] += rename_component(con, 531, "CLONIXINATO DE LISINA", "CLONIXINA")
    n['B'] += rename_component(con, 535, "CLONIXINATO DE LISINA", "CLONIXINA")
    n['B'] += rename_component(con, 2267, "CLONIXINATO DE LISINA", "CLONIXINA")
    n['B'] += rename_component(con, 2541, "CLONIXINATO DE LISINA", "CLONIXINA")

    # Post-fix auto-merge
    print("\n=== Post-fix auto-merge ===")
    cur.execute("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as cnt,
               GROUP_CONCAT(id || ':' || n_productos ORDER BY n_productos DESC)
        FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING cnt > 1
    """)
    for dci, via, conc, cnt, ids_str in cur.fetchall():
        pairs = [(int(x.split(':')[0]), int(x.split(':')[1])) for x in ids_str.split(',')]
        keep_id = pairs[0][0]
        for del_id, _ in pairs[1:]:
            n['merge'] += merge_into(con, keep_id, del_id)

    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    print("\n=== RESUMEN ===")
    for k, v in n.items():
        if v:
            print(f"  {k}: {v}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_norm='SIN_CONCENTRACION'")
    sin = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm HAVING COUNT(*) > 1
    """)
    dups = len(cur.fetchall())
    print(f"\nDB: {total} grupos | {sin} SIN_CONCENTRACION | {dups} duplicados")
    con.close()


if __name__ == "__main__":
    main()
