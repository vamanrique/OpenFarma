"""
fix_auditoria_conc84.py — Octogesimocuarta ronda de auditoría.

Correcciones INN para factores de coagulación recombinantes:

  A) id=2973 (BENCILPENICILINA PROCAINA, 800 UI):
     concentracion_norm='800 UI' → '800000 UI'
     Los productos contienen "800.000 Ui" = 800,000 UI. Error de parseo.
     → auto-merge con id=2972 (BENCILPENICILINA PROCAINA, 800000 UI)

  B) ids=3572, 3573, 3574 (Adynovate, Factor VIII pegilado):
     'FACTOR ANTIHEMOFILICO RECOMBINANTE PEGILADO' → 'RURIOCTOCOG ALFA PEGOL'
     INN OMS para rurioctocog alfa pegol (Adynovate, Takeda/Shire).
     id=3575 ya usa la forma canónica (RURIOCTOCOG ALFA PEGOL, 250 UI);
     los 3 grupos tienen concentraciones distintas → no hay merge entre ellos.

  C) ids=3541, 3581 (Kovaltry):
     'FACTOR VIII RECOMBINANTE' → 'OCTOCOG ALFA'
     Kovaltry (BAY 81-8973, Bayer) = octocog alfa. INN OMS = octocog alfa.
     id=3323 ya usa OCTOCOG ALFA (1000 UI, Advate).
     → id=3581 (1000 UI) auto-merge con id=3323 tras rename.
     → id=3541 (250 UI) queda solo (sin grupo 250 UI previo).

  D) id=3018 (Rixubis):
     'FACTOR IX' → 'NONACOG GAMMA'
     Rixubis (BAY 86-6150, Bayer) = nonacog gamma. INN OMS = nonacog gamma.
     ids=3042-3045 son NONACOG ALFA (BeneFIX, Pfizer) — INN diferente, sin merge.
     Plasma-derived FIX (Aimafix, Immunine, Octanine) permanecen como FACTOR IX.
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
    print(f"  [RENAME] id={gid}: '{old_dci[:80]}' -> '{new_dci[:80]}'")
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


def fix_conc(con, gid: int, old_conc: str, new_conc: str) -> int:
    cur = con.cursor()
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP conc] id={gid} no existe")
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya conc] id={gid}: {new_conc}")
        return 0
    if row[0] != old_conc:
        print(f"  [WARN conc] id={gid}: esperado '{old_conc}', encontrado '{row[0]}'")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [CONC] id={gid}: '{old_conc}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # A. id=2973: concentracion_norm 800 UI → 800000 UI
    print("\n=== A. id=2973 BENCILPENICILINA PROCAINA: conc 800 UI -> 800000 UI ===")
    n['A'] += fix_conc(con, 2973, "800 UI", "800000 UI")

    # B. ids=3572-3574: FACTOR ANTIHEMOFILICO RECOMBINANTE PEGILADO → RURIOCTOCOG ALFA PEGOL
    print("\n=== B. ids=3572-3574 Adynovate: FACTOR ANTIHEMOFILICO -> RURIOCTOCOG ALFA PEGOL ===")
    for gid in [3572, 3573, 3574]:
        n['B'] += rename_dci(con, gid, "RURIOCTOCOG ALFA PEGOL", {
            "FACTOR ANTIHEMOFILICO RECOMBINANTE PEGILADO": "RURIOCTOCOG ALFA PEGOL",
        })

    # C. ids=3541, 3581: FACTOR VIII RECOMBINANTE → OCTOCOG ALFA
    print("\n=== C. ids=3541,3581 Kovaltry: FACTOR VIII RECOMBINANTE -> OCTOCOG ALFA ===")
    for gid in [3541, 3581]:
        n['C'] += rename_dci(con, gid, "OCTOCOG ALFA", {
            "FACTOR VIII RECOMBINANTE": "OCTOCOG ALFA",
        })

    # D. id=3018: FACTOR IX → NONACOG GAMMA
    print("\n=== D. id=3018 Rixubis: FACTOR IX -> NONACOG GAMMA ===")
    n['D'] += rename_dci(con, 3018, "NONACOG GAMMA", {
        "FACTOR IX": "NONACOG GAMMA",
    })

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
