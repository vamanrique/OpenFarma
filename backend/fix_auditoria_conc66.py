"""
fix_auditoria_conc66.py — Sexagesimosexta ronda de auditoría.

Correcciones — vacunas gripe e Adacel:

  A) BORDETELLA PERTUSSIS HEMAGGLUTININA FILAMENTOSA -> HEMAGLUTININA (una sola G)
     (hemaglutinina = español estándar; HEMAGGLUTININA es anglicismo con doble G):
     - id=3305: Adacel Tdap IN SIN_CONC (n=3) -> sin merge

  B) INFLUENZA A VIRUS (x2) || INFLUENZA B VIRUS (x2) -> componentes diferenciados
     (Vaxigrip Tetra es cuadrivalente: A/H1N1 + A/H3N2 + B/Victoria + B/Yamagata;
      dci_key tenía componentes duplicados sin distinguir subtipos):
     - id=3610: IN SIN_CONC (n=1) -> sin merge
     Nueva forma: INFLUENZA A H1N1||INFLUENZA A H3N2||INFLUENZA B LINAJE VICTORIA||INFLUENZA B LINAJE YAMAGATA
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


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # -- A. HEMAGGLUTININA (2G) -> HEMAGLUTININA (1G) en Adacel Tdap ------------------
    print("\n=== A. HEMAGGLUTININA -> HEMAGLUTININA (id=3305 Adacel) ===")
    new_dci_3305 = (
        "BORDETELLA PERTUSSIS FIMBRIAE 2/3||"
        "BORDETELLA PERTUSSIS HEMAGLUTININA FILAMENTOSA||"
        "BORDETELLA PERTUSSIS PERTACTINA||"
        "CLOSTRIDIUM TETANI TOXOIDE||"
        "CORYNEBACTERIUM DIPHTHERIAE TOXOIDE||"
        "TOXOIDE PERTUSICO"
    )
    n['A'] += rename_dci(con, 3305, new_dci_3305,
                         {"BORDETELLA PERTUSSIS HEMAGGLUTININA FILAMENTOSA":
                          "BORDETELLA PERTUSSIS HEMAGLUTININA FILAMENTOSA"})

    # -- B. Vaxigrip Tetra: componentes duplicados -> subtipos diferenciados -----------
    print("\n=== B. INFLUENZA duplicados -> H1N1/H3N2/Victoria/Yamagata (id=3610) ===")
    new_dci_3610 = (
        "INFLUENZA A H1N1||"
        "INFLUENZA A H3N2||"
        "INFLUENZA B LINAJE VICTORIA||"
        "INFLUENZA B LINAJE YAMAGATA"
    )
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=3610")
    row = cur.fetchone()
    if row:
        old_dci = row[0]
        if old_dci != new_dci_3610:
            cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=3610", (new_dci_3610,))
            print(f"  [RENAME] id=3610: '{old_dci[:80]}' -> '{new_dci_3610[:80]}'")
            # Direct update: principios_dci can't be mapped 1:1 (source has duplicates)
            new_pdci = ["INFLUENZA A H1N1", "INFLUENZA A H3N2",
                        "INFLUENZA B LINAJE VICTORIA", "INFLUENZA B LINAJE YAMAGATA"]
            cids = safe_json(row[1])
            updated = 0
            for cid in cids:
                exp, consec = cid.split('-')
                cur.execute("UPDATE cum_normalizado SET principios_dci=? "
                            "WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(new_pdci), exp, consec))
                if cur.rowcount:
                    updated += 1
            if updated:
                print(f"    cum_normalizado: {updated} productos actualizados")
            n['B'] += 1
        else:
            print(f"  [OK ya] id=3610")

    # -- C. Post-fix auto-merge -------------------------------------------------------
    print("\n=== C. Post-fix auto-merge ===")
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
