"""
fix_auditoria_conc90.py — Nonagésima ronda de auditoría.

Correcciones para surfactantes bovinos (BLES/Blesurf):

  A) id=3554 (BLES 3mL, 5mL — bovine lipid extract surfactant):
     DCI: 'FOSFOLIPIDOS||SURFACTANTE ASOCIADO CON LAS PROTEINAS B Y C' → 'BERACTANT'
     Via: LIQUIDO_ORAL → INYECTABLE
     Conc: '9 mg/mL + 58.667 mg/mL' (multi-componente) → SIN_CONCENTRACION
     BLES = beractant: extracto lipídico de pulmón bovino (=Survanta).
     INN OMS: beractant. LIQUIDO_ORAL es error de clasificación (es uso IT).
     → auto-merge con id=2878 (BERACTANT|INYECTABLE|SIN_CONCENTRACION, Survanta)

  B) id=3600 (Blesurf 4mL — bovine lipid extract surfactant):
     DCI: 'FOSFOLIPIDOS NATURALES||SURFACTANTE ASOCIADO CON LAS PROTEINAS B Y C' → 'BERACTANT'
     Via: mantiene INHALADO (clasificación original, IT vs INHALADO es ambiguo en INVIMA)
     Conc: mantiene SIN_CONCENTRACION
     → auto-merge con id=2879 (BERACTANT|INHALADO|SIN_CONCENTRACION, Survanta-5)
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


def rename_surfactant(con, gid: int, new_via: str, new_conc: str) -> int:
    """Rename multi-component DCI to BERACTANT, optionally fixing via and conc."""
    cur = con.cursor()
    cur.execute("SELECT dci_key, grupo_via, concentracion_norm, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_dci, old_via, old_conc, cum_ids_str = row
    if old_dci == "BERACTANT":
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute(
        "UPDATE grupos_equivalencia SET dci_key=?, grupo_via=?, concentracion_norm=? WHERE id=?",
        ("BERACTANT", new_via, new_conc, gid)
    )
    print(f"  [RENAME] id={gid}: '{old_dci[:70]}' -> BERACTANT")
    if old_via != new_via:
        print(f"    via: {old_via} -> {new_via}")
    if old_conc != new_conc:
        print(f"    conc: '{old_conc}' -> '{new_conc}'")
    cids = safe_json(cum_ids_str)
    updated = 0
    for cid in cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                    (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = safe_json(p[0])
            if pdci != ["BERACTANT"]:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(["BERACTANT"]), exp, consec))
                updated += 1
    if updated:
        print(f"    cum_normalizado: {updated} productos actualizados")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # A. id=3554 BLES: componentes/LIQUIDO_ORAL → BERACTANT/INYECTABLE/SIN_CONCENTRACION
    print("\n=== A. id=3554 BLES: comp/LIQUIDO_ORAL -> BERACTANT/INYECTABLE ===")
    n['A'] += rename_surfactant(con, 3554, new_via="INYECTABLE", new_conc="SIN_CONCENTRACION")

    # B. id=3600 Blesurf: componentes/INHALADO → BERACTANT/INHALADO/SIN_CONCENTRACION
    print("\n=== B. id=3600 Blesurf: comp/INHALADO -> BERACTANT/INHALADO ===")
    n['B'] += rename_surfactant(con, 3600, new_via="INHALADO", new_conc="SIN_CONCENTRACION")

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
