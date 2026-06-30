"""
fix_auditoria_conc98.py — Nonagésimoctava ronda de auditoría.

  A) ISOSORBIDA DINITRATO → DINITRATO DE ISOSORBIDA (WHO INN-Sp #4749):
     El INN OMS en español para isosorbide dinitrate es "dinitrato de isosorbida"
     (no "isosorbida dinitrato" que seguiría la forma compound+modifier).
     Solo 2 grupos sin auto-merge entre sí (distinta vía/concentración):
       id=320: ISOSORBIDA DINITRATO | SUBLINGUAL | 5 mg
       id=579: ISOSORBIDA DINITRATO | SOLIDO_ORAL | 10 mg

  B) ISOPROPANOL / PROPAN-2-OL → ALCOHOL ISOPROPILICO:
     Ambos nombres son formas químicas (IUPAC / abreviado) del mismo compuesto.
     El nombre farmacéutico establecido en la DB es ALCOHOL ISOPROPILICO
     (isopropyl alcohol), usado en ids 3116, 1067, 1550, 3301, 3023.
       id=3430: CLORHEXIDINA||ISOPROPANOL → ALCOHOL ISOPROPILICO||CLORHEXIDINA
       id=3470: CLORHEXIDINA||PROPAN-2-OL → ALCOHOL ISOPROPILICO||CLORHEXIDINA
     → auto-merge: ambos tienen TOPICO | 2% + 70% → se fusionan (n=17 total).
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


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


def rename_component(con, gid: int, old_component: str, new_component: str) -> int:
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

    # A. ISOSORBIDA DINITRATO → DINITRATO DE ISOSORBIDA
    print("\n=== A. ISOSORBIDA DINITRATO → DINITRATO DE ISOSORBIDA ===")
    for gid in [320, 579]:
        n['A'] += rename_component(con, gid, "ISOSORBIDA DINITRATO", "DINITRATO DE ISOSORBIDA")

    # B. ISOPROPANOL / PROPAN-2-OL → ALCOHOL ISOPROPILICO
    print("\n=== B. ISOPROPANOL / PROPAN-2-OL → ALCOHOL ISOPROPILICO ===")
    n['B'] += rename_component(con, 3430, "ISOPROPANOL", "ALCOHOL ISOPROPILICO")
    n['B'] += rename_component(con, 3470, "PROPAN-2-OL", "ALCOHOL ISOPROPILICO")

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
