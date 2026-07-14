"""
fix_auditoria_conc88.py — Octogesimoctava ronda de auditoría.

Correcciones INN de radiofármacos y antiretrovirales:

  A) id=2230 (Rotop-MDP, kit óseo):
     'ACIDO METILENDIFOSFONICO' → 'ACIDO MEDRONICO'
     El ácido metilendifosfonico (MDP = methylene diphosphonate) es el nombre
     sistemático IUPAC. INN OMS: medronic acid = ACIDO MEDRONICO (español).
     id=696 ya usa ACIDO MEDRONICO (10 mg), concentración distinta → sin merge.

  B) ids=1306, 1672, 1691, 1702, 1900, 2182
     'TENOFOVIR' → 'TENOFOVIR DISOPROXILO'
     Todos los productos bajo dci_key=TENOFOVIR (300 mg o 245 mg VO) son
     tenofovir disoproxil fumarate (TDF): Truvada, Stribild, Trustiva/Atripla,
     Delstrigo, Didivir, Tendifu. TENOFOVIR (ácido libre) no está aprobado VO.
     INN OMS: tenofovir disoproxil = TENOFOVIR DISOPROXILO.
     → id=1306 (EMTRICITABINA||TENOFOVIR 200+300mg) → tras rename duplica
       id=1683 (EMTRICITABINA||TENOFOVIR DISOPROXILO 200+300mg) → auto-merge.
     → resto sin merge (concentraciones únicas).
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

    # A. id=2230: ACIDO METILENDIFOSFONICO → ACIDO MEDRONICO
    print("\n=== A. id=2230 Rotop-MDP: ACIDO METILENDIFOSFONICO -> ACIDO MEDRONICO ===")
    n['A'] += rename_dci(con, 2230, "ACIDO MEDRONICO", {
        "ACIDO METILENDIFOSFONICO": "ACIDO MEDRONICO",
    })

    # B. ids=1306,1672,1691,1702,1900,2182: TENOFOVIR → TENOFOVIR DISOPROXILO
    print("\n=== B. TENOFOVIR -> TENOFOVIR DISOPROXILO (6 grupos TDF) ===")
    tdf_map = {"TENOFOVIR": "TENOFOVIR DISOPROXILO"}
    for gid, label in [
        (1702, "TENOFOVIR mono 300mg"),
        (1306, "EMTRICITABINA||TENOFOVIR 200+300mg (Truvada)"),
        (1900, "EMTRICITABINA||TENOFOVIR 200+245mg"),
        (1691, "EFAVIRENZ||EMTRICITABINA||TENOFOVIR 600+200+300mg"),
        (1672, "COBICISTAT||ELVITEGRAVIR||EMTRICITABINA||TENOFOVIR"),
        (2182, "DORAVIRINA||LAMIVUDINA||TENOFOVIR (Delstrigo)"),
    ]:
        # Compute new dci_key: replace TENOFOVIR component in the sorted list
        cur.execute("SELECT dci_key FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if not row:
            print(f"  [SKIP] id={gid} ({label}) no existe")
            continue
        parts = row[0].split("||")
        new_parts = ["TENOFOVIR DISOPROXILO" if p == "TENOFOVIR" else p for p in parts]
        new_dci = "||".join(sorted(new_parts))
        print(f"  [{label}]")
        n['B'] += rename_dci(con, gid, new_dci, tdf_map)

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
