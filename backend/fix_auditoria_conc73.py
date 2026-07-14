"""
fix_auditoria_conc73.py — Septuagesimatercera ronda de auditoría.

Correcciones — prefijos de género bacteriano en vacunas acelulares DTPa:

  Convención establecida: los antígenos pertussis usan nombre corto del componente
  sin el prefijo de género (igual que en id=3053/id=3046/id=3510 ya corregidos):
  - HEMAGLUTININA FILAMENTOSA (no BORDETELLA PERTUSSIS HEMAGLUTININA FILAMENTOSA)
  - PERTACTINA (no BORDETELLA PERTUSSIS PERTACTINA)
  - TOXOIDE PERTUSICO (no BORDETELLA PERTUSSIS TOXOIDE)
  - FIMBRIAE 2/3 (no BORDETELLA PERTUSSIS FIMBRIAE 2/3)
  Los toxoides de tétanos y difteria usan el nombre de la toxina, no del género:
  - TOXOIDE TETANICO (no CLOSTRIDIUM TETANI TOXOIDE)
  - TOXOIDE DIFTERICO (no CORYNEBACTERIUM DIPHTHERIAE TOXOIDE)

  A) id=3305 (Adacel, DTPa5):
     - BORDETELLA PERTUSSIS FIMBRIAE 2/3 -> FIMBRIAE 2/3
     - BORDETELLA PERTUSSIS HEMAGLUTININA FILAMENTOSA -> HEMAGLUTININA FILAMENTOSA
     - BORDETELLA PERTUSSIS PERTACTINA -> PERTACTINA
     - CLOSTRIDIUM TETANI TOXOIDE -> TOXOIDE TETANICO
     - CORYNEBACTERIUM DIPHTHERIAE TOXOIDE -> TOXOIDE DIFTERICO
     sin merge: Adacel tiene 5 antigenos pertussis (incluyendo FIMBRIAE 2/3), distinto
     al id=3046 (Boostrix, 3 antigenos, sin fimbriae)

  B) id=3117 (pentavalente DTaP-Hib-IPV):
     - BORDETELLA PERTUSSIS TOXOIDE -> TOXOIDE PERTUSICO
     - CLOSTRIDIUM TETANI TOXOIDE -> TOXOIDE TETANICO
     - CORYNEBACTERIUM DIPHTHERIAE TOXOIDE -> TOXOIDE DIFTERICO
     - HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO -> POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B
     sin merge: composicion diferente a id=3510 (id=3117 sin HepB, id=3510 con HepB)
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"

NEW_DCI_3305 = (
    "FIMBRIAE 2/3||HEMAGLUTININA FILAMENTOSA||PERTACTINA||"
    "TOXOIDE DIFTERICO||TOXOIDE PERTUSICO||TOXOIDE TETANICO"
)

NEW_DCI_3117 = (
    "POLIOVIRUS INACTIVADO TIPO 1||POLIOVIRUS INACTIVADO TIPO 2||POLIOVIRUS INACTIVADO TIPO 3||"
    "POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B||"
    "TOXOIDE DIFTERICO||TOXOIDE PERTUSICO||TOXOIDE TETANICO"
)


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

    # -- A. id=3305 Adacel (DTPa5): drop prefijos bacterianos, corregir toxoides --------
    print("\n=== A. id=3305 Adacel: prefijos BP/CT/CD -> nombres canónicos ===")
    n['A'] += rename_dci(con, 3305, NEW_DCI_3305, {
        "BORDETELLA PERTUSSIS FIMBRIAE 2/3": "FIMBRIAE 2/3",
        "BORDETELLA PERTUSSIS HEMAGLUTININA FILAMENTOSA": "HEMAGLUTININA FILAMENTOSA",
        "BORDETELLA PERTUSSIS PERTACTINA": "PERTACTINA",
        "CLOSTRIDIUM TETANI TOXOIDE": "TOXOIDE TETANICO",
        "CORYNEBACTERIUM DIPHTHERIAE TOXOIDE": "TOXOIDE DIFTERICO",
    })

    # -- B. id=3117 pentavalente DTaP-Hib-IPV: mismos prefijos + fix Hib ---------------
    print("\n=== B. id=3117 pentavalente: prefijos BP/CT/CD + Hib -> canónicos ===")
    n['B'] += rename_dci(con, 3117, NEW_DCI_3117, {
        "BORDETELLA PERTUSSIS TOXOIDE": "TOXOIDE PERTUSICO",
        "CLOSTRIDIUM TETANI TOXOIDE": "TOXOIDE TETANICO",
        "CORYNEBACTERIUM DIPHTHERIAE TOXOIDE": "TOXOIDE DIFTERICO",
        "HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO": "POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B",
    })

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
