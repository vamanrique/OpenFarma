"""
fix_auditoria_conc39.py — Trigesimanovena ronda de auditoría.

Correcciones — oftálmicos: sinonimia y forma INN:
  A) DORZOLAMINA -> DORZOLAMIDA (INN estándar; -AMIDA no -AMINA):
     - id=3582: BRIMONIDINA||DORZOLAMINA||TIMOLOL OF 0.4+4+1 mg/mL (n=4, Krytantek)
       B<D<T: mismo orden, sin reorden conc; sin merge (conc distinta a id=3319)
  B) CROMOGLICICO ACIDO -> CROMOGLICATO DE SODIO (sal sódica estándar en colirios):
     - id=3202: CROMOGLICICO ACIDO OF 40 mg/mL (n=2, Oftacromax)
       auto-merge -> id=3343 (CROMOGLICATO DE SODIO OF 40mg/mL, n=11 -> n=13)
  C) CARBOXIMETILCELULOSA -> CARBOXIMETILCELULOSA SODICA (conv. DB = INN sal sódica):
     - id=3627: CARBOXIMETILCELULOSA||GLICEROL OF 5+9 mg/mL (n=3, Carmelub Plus)
       sin merge (no hay CMC-SODICA||GLICEROL 5+9 mg/mL)
  D) TETRAHIDROZOLINA -> TETRIZOLINA (INN estándar; TETRIZOLINA es conv. DB mayoritaria):
     - id=3194: TETRAHIDROZOLINA OF 0.5 mg/mL (n=2, Ecanon/Visine)
       auto-merge -> id=3586 (TETRIZOLINA OF 0.5mg/mL, n=3 -> n=5)
     - id=3896: TETRAHIDROZOLINA OF 5 mg/mL (n=1, Eyelim)
       sin merge (no hay TETRIZOLINA OF 5mg/mL)
     - id=3476: FLUOROMETOLONA||TETRAHIDROZOLINA OF 1+0.25 mg/mL (n=4, Flu-Sure T)
       F<T: mismo orden, sin reorden conc; sin merge
  E) Post-fix auto-merge duplicados
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


def rename_dci(con, gid: int, new_dci: str, sync_map: dict) -> int:
    cur = con.cursor()
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_dci = row[0]
    if old_dci == new_dci:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_dci, gid))
    print(f"  [RENAME] id={gid}: '{old_dci[:70]}' -> '{new_dci[:70]}'")
    cids = safe_json(row[1])
    updated = 0
    for cid in cids:
        exp, consec = cid.split('-')
        cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                    (exp, consec))
        p = cur.fetchone()
        if p and p[0]:
            pdci = safe_json(p[0])
            new_pdci = [sync_map.get(d, d) for d in pdci]
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. DORZOLAMINA -> DORZOLAMIDA -----------------------------------------------
    print("\n=== A. id=3582: DORZOLAMINA -> DORZOLAMIDA ===")
    n['A'] += rename_dci(con, 3582, "BRIMONIDINA||DORZOLAMIDA||TIMOLOL",
                         {"DORZOLAMINA": "DORZOLAMIDA"})

    # -- B. CROMOGLICICO ACIDO -> CROMOGLICATO DE SODIO --------------------------------
    print("\n=== B. id=3202: CROMOGLICICO ACIDO -> CROMOGLICATO DE SODIO ===")
    n['B'] += rename_dci(con, 3202, "CROMOGLICATO DE SODIO",
                         {"CROMOGLICICO ACIDO": "CROMOGLICATO DE SODIO"})
    # auto-merge 3202 (n=2) -> 3343 (CROMOGLICATO DE SODIO OF 40mg/mL, n=11) -> total=13

    # -- C. CARBOXIMETILCELULOSA -> CARBOXIMETILCELULOSA SODICA (id=3627) ---------------
    print("\n=== C. id=3627: CARBOXIMETILCELULOSA -> CARBOXIMETILCELULOSA SODICA ===")
    n['C'] += rename_dci(con, 3627, "CARBOXIMETILCELULOSA SODICA||GLICEROL",
                         {"CARBOXIMETILCELULOSA": "CARBOXIMETILCELULOSA SODICA"})

    # -- D. TETRAHIDROZOLINA -> TETRIZOLINA (ids 3194, 3896, 3476) -------------------
    print("\n=== D. TETRAHIDROZOLINA -> TETRIZOLINA ===")
    ttrz = {"TETRAHIDROZOLINA": "TETRIZOLINA"}
    n['D'] += rename_dci(con, 3194, "TETRIZOLINA", ttrz)
    # auto-merge 3194 (n=2) -> 3586 (TETRIZOLINA OF 0.5mg/mL, n=3) -> total=5
    n['D'] += rename_dci(con, 3896, "TETRIZOLINA", ttrz)
    n['D'] += rename_dci(con, 3476, "FLUOROMETOLONA||TETRIZOLINA", ttrz)

    # -- E. Post-fix auto-merge -------------------------------------------------------
    print("\n=== E. Post-fix auto-merge ===")
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

    # -- Fix n_productos -------------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen ---------------------------------------------------------------------
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
