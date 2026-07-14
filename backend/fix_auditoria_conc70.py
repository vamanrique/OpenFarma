"""
fix_auditoria_conc70.py — Septuagésima ronda de auditoría.

Correcciones:

  A) IOBENGUANO (I-131) -> IOBENGUANO (131I)
     (convención isótopo establecida: número+símbolo sin guion, ej. (99MTC), (131I);
      la ronda 58 eliminó el espacio pero quedó el guion y el orden invertido):
     - id=3007: IN SIN_CONC (n=2) -> sin merge

  B,C,D) 3 variantes Inhibidor Alfa-1 Proteinasa -> forma canónica AEMPS
     Canónica: INHIBIDOR DE ALFA-1 PROTEINASA (HUMANO)
     (AEMPS: "inhibidor de alfa-1 proteinasa (humano)"; Prolastin C + Ventia):
     - id=1442: INHIBIDOR ALFA 1 PROTEINASA (HUMANA) -> canónica (1000mg)
     - id=2464: INHIBIDOR DE ALFA 1-PROTEINASA HUMANO -> canónica (50mg/mL)
     - id=1569: ALFA-1 ANTITRIPSINA -> canónica (20mg/mL)
     -> sin merge entre ellos (concentraciones distintas)
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"
TARGET_A1PI = "INHIBIDOR DE ALFA-1 PROTEINASA (HUMANO)"


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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. IOBENGUANO (I-131) -> IOBENGUANO (131I) ------------------------------------
    print("\n=== A. IOBENGUANO (I-131) -> IOBENGUANO (131I) (id=3007) ===")
    n['A'] += rename_dci(con, 3007, "IOBENGUANO (131I)",
                         {"IOBENGUANO (I-131)": "IOBENGUANO (131I)"})

    # -- B. INHIBIDOR ALFA 1 PROTEINASA (HUMANA) -> canónica (id=1442) -----------------
    print("\n=== B. INHIBIDOR ALFA 1 PROTEINASA (HUMANA) -> canónica (id=1442) ===")
    n['B'] += rename_dci(con, 1442, TARGET_A1PI,
                         {"INHIBIDOR ALFA 1 PROTEINASA (HUMANA)": TARGET_A1PI})

    # -- C. INHIBIDOR DE ALFA 1-PROTEINASA HUMANO -> canónica (id=2464) ----------------
    print("\n=== C. INHIBIDOR DE ALFA 1-PROTEINASA HUMANO -> canónica (id=2464) ===")
    n['C'] += rename_dci(con, 2464, TARGET_A1PI,
                         {"INHIBIDOR DE ALFA 1-PROTEINASA HUMANO": TARGET_A1PI})

    # -- D. ALFA-1 ANTITRIPSINA -> canónica (id=1569) ----------------------------------
    print("\n=== D. ALFA-1 ANTITRIPSINA -> canónica (id=1569) ===")
    n['D'] += rename_dci(con, 1569, TARGET_A1PI,
                         {"ALFA-1 ANTITRIPSINA": TARGET_A1PI})

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
