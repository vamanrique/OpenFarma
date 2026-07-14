"""
fix_auditoria_conc58.py — Quincuagesimoctava ronda de auditoría.

Correcciones — typos y componentes inglés en combos de vacunas:

  A) VIDAGLIPTINA -> VILDAGLIPTINA (typo: falta L; DCI correcta = vildagliptina):
     - id=2399: METFORMINA||VIDAGLIPTINA SO 850mg+50mg (n=2) -> auto-merge id=66 (n=33->35)

  B) CEFTAZIDIME -> CEFTAZIDIMA (inglés->español; DCI español = ceftazidima):
     - id=2171: AVIBACTAM||CEFTAZIDIME IN 500mg+2000mg (n=1) -> sin merge

  C) FLUOCINOLONA ACETONIDO -> FLUOCINOLONA ACETONIDA (acetonide->acetonida; DCI español):
     - id=2628: CIPROFLOXACINO||FLUOCINOLONA ACETONIDO OT 3+0.25 mg/mL (n=2) -> sin merge

  D) TOXOIDE PERTUSSIS -> TOXOIDE PERTUSICO (inglés PERTUSSIS->español PERTUSICO):
     - id=3046: HEMAGLUTININA FILAMENTOSA||PERTACTINA||TOXOIDE DIFTERICO||TOXOIDE PERTUSSIS||
                TOXOIDE TETANICO IN SIN_CONC (n=2) -> sin merge

  E) Componentes inglés en vacuna pentavalente -> español:
     - id=3117: ...HAEMOPHILUS INFLUENZAE TYPE B POLYSACCHARIDE||POLIOVIRUS TYPE 1 INACTIVATED...
                -> HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO / POLIOVIRUS INACTIVADO TIPO x
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. VIDAGLIPTINA -> VILDAGLIPTINA (typo) ---------------------------------------
    print("\n=== A. VIDAGLIPTINA -> VILDAGLIPTINA ===")
    n['A'] += rename_dci(con, 2399, "METFORMINA||VILDAGLIPTINA",
                         {"VIDAGLIPTINA": "VILDAGLIPTINA"})

    # -- B. CEFTAZIDIME -> CEFTAZIDIMA (inglés->español) --------------------------------
    print("\n=== B. AVIBACTAM||CEFTAZIDIME -> AVIBACTAM||CEFTAZIDIMA ===")
    n['B'] += rename_dci(con, 2171, "AVIBACTAM||CEFTAZIDIMA",
                         {"CEFTAZIDIME": "CEFTAZIDIMA"})

    # -- C. FLUOCINOLONA ACETONIDO -> FLUOCINOLONA ACETONIDA ---------------------------
    print("\n=== C. FLUOCINOLONA ACETONIDO -> FLUOCINOLONA ACETONIDA ===")
    n['C'] += rename_dci(con, 2628, "CIPROFLOXACINO||FLUOCINOLONA ACETONIDA",
                         {"FLUOCINOLONA ACETONIDO": "FLUOCINOLONA ACETONIDA"})

    # -- D. TOXOIDE PERTUSSIS -> TOXOIDE PERTUSICO -------------------------------------
    print("\n=== D. TOXOIDE PERTUSSIS -> TOXOIDE PERTUSICO ===")
    n['D'] += rename_dci(con, 3046,
                         "HEMAGLUTININA FILAMENTOSA||PERTACTINA||TOXOIDE DIFTERICO||TOXOIDE PERTUSICO||TOXOIDE TETANICO",
                         {"TOXOIDE PERTUSSIS": "TOXOIDE PERTUSICO"})

    # -- E. Componentes inglés en vacuna pentavalente -> español -----------------------
    print("\n=== E. Vacuna pentavalente: componentes inglés -> español ===")
    penta_map = {
        "HAEMOPHILUS INFLUENZAE TYPE B POLYSACCHARIDE": "HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO",
        "POLIOVIRUS TYPE 1 INACTIVATED": "POLIOVIRUS INACTIVADO TIPO 1",
        "POLIOVIRUS TYPE 2 INACTIVATED": "POLIOVIRUS INACTIVADO TIPO 2",
        "POLIOVIRUS TYPE 3 INACTIVATED": "POLIOVIRUS INACTIVADO TIPO 3",
    }
    new_dci_3117 = ("BORDETELLA PERTUSSIS TOXOIDE||CLOSTRIDIUM TETANI TOXOIDE||"
                    "CORYNEBACTERIUM DIPHTHERIAE TOXOIDE||HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO||"
                    "POLIOVIRUS INACTIVADO TIPO 1||POLIOVIRUS INACTIVADO TIPO 2||POLIOVIRUS INACTIVADO TIPO 3")
    n['E'] += rename_dci(con, 3117, new_dci_3117, penta_map)

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
