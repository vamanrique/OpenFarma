"""
fix_auditoria_conc47.py — Cuadragesimoseptima ronda de auditoría.

Correcciones — BACILLUS->BACILO (Spanish), nombres inconsistentes:

  A) BACILLUS -> BACILO (forma española del género bacteriano):
     - id=1475: BACILLUS CALMETTE-GUERIN INYECTABLE 40mg (n=3, BCG) -> BACILO CALMETTE-GUERIN (sin merge)
     - id=3176: BACILLUS CLAUSII LIQUIDO_ORAL SIN_CONC (n=20) -> BACILO CLAUSII (sin merge)
     - id=3178: BACILLUS CLAUSII SOLIDO_ORAL SIN_CONC (n=1) -> BACILO CLAUSII (sin merge)

  B) BENZIDAMINA -> BENCIDAMINA (typo: Z->C, DCI español estándar):
     - id=3225: BENZIDAMINA LIQUIDO_ORAL 1.5mg/mL (n=2)
       auto-merge -> id=2861 (BENCIDAMINA LO 1.5mg/mL, n=34 -> n=36)

  C) BENZILPENICILINA -> BENCILPENICILINA (BZ->BC, DCI español estándar):
     - id=3485: BENZILPENICILINA INYECTABLE 1200000 UI (n=5) -> sin merge
     - id=3486: BENZILPENICILINA INYECTABLE 2400000 UI (n=2)
       auto-merge -> id=2971 (BENCILPENICILINA IN 2400000 UI, n=4 -> n=6)

  D) CEFRADILO -> CEFRADINA (INN correcto: cefradina, no cefradilo):
     - id=3626: CEFRADILO LIQUIDO_ORAL 50mg/mL (n=2)
       auto-merge -> id=3314 (CEFRADINA LO 50mg/mL, n=14 -> n=16)

  E) BENZILO BENZOATO -> BENZOATO DE BENCILO (orden INN español: [sal] de [base]):
     - id=956: BENZILO BENZOATO TOPICO 30% (n=2)
       auto-merge -> id=376 (BENZOATO DE BENCILO TOP 30%, n=2 -> n=4)
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. BACILLUS -> BACILO --------------------------------------------------------
    print("\n=== A. BACILLUS -> BACILO ===")
    n['A'] += rename_dci(con, 1475, "BACILO CALMETTE-GUERIN",
                         {"BACILLUS CALMETTE-GUERIN": "BACILO CALMETTE-GUERIN"})
    n['A'] += rename_dci(con, 3176, "BACILO CLAUSII", {"BACILLUS CLAUSII": "BACILO CLAUSII"})
    n['A'] += rename_dci(con, 3178, "BACILO CLAUSII", {"BACILLUS CLAUSII": "BACILO CLAUSII"})

    # -- B. BENZIDAMINA -> BENCIDAMINA ------------------------------------------------
    print("\n=== B. BENZIDAMINA -> BENCIDAMINA ===")
    n['B'] += rename_dci(con, 3225, "BENCIDAMINA", {"BENZIDAMINA": "BENCIDAMINA"})

    # -- C. BENZILPENICILINA -> BENCILPENICILINA --------------------------------------
    print("\n=== C. BENZILPENICILINA -> BENCILPENICILINA ===")
    n['C'] += rename_dci(con, 3485, "BENCILPENICILINA", {"BENZILPENICILINA": "BENCILPENICILINA"})
    n['C'] += rename_dci(con, 3486, "BENCILPENICILINA", {"BENZILPENICILINA": "BENCILPENICILINA"})

    # -- D. CEFRADILO -> CEFRADINA ----------------------------------------------------
    print("\n=== D. CEFRADILO -> CEFRADINA ===")
    n['D'] += rename_dci(con, 3626, "CEFRADINA", {"CEFRADILO": "CEFRADINA"})

    # -- E. BENZILO BENZOATO -> BENZOATO DE BENCILO -----------------------------------
    print("\n=== E. BENZILO BENZOATO -> BENZOATO DE BENCILO ===")
    n['E'] += rename_dci(con, 956, "BENZOATO DE BENCILO", {"BENZILO BENZOATO": "BENZOATO DE BENCILO"})

    # -- F. Post-fix auto-merge -------------------------------------------------------
    print("\n=== F. Post-fix auto-merge ===")
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
