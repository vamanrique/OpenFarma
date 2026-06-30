"""
fix_auditoria_conc102.py — Centésimasegunda ronda de auditoría.

  A) RADIO RA-223 → DICLORURO DE RADIO (223RA) (WHO INN #9982):
     Xofigo = radium Ra-223 dichloride (RaCl₂). Sigue la convención establecida:
     CLORURO DE LUTECIO (177LU), CITRATO DE GALIO (67GA), MOLIBDATO DE SODIO (99MO).
     INN OMS: "radium (223Ra) dichloride" → esp. "dicloruro de radio (223Ra)".
       id=3495: RADIO RA-223 | INYECTABLE | SIN_CONCENTRACION | n=2

  B) YODO → ACEITE DE ADORMIDERA YODADO (Lipiodol, ATC V08BA02):
     Lipiodol Ultra-Fluide = aceite de adormidera yodado (ethiodized oil).
     La DCI "YODO" (yodo elemental, antiséptico) fue un error del ETL — el producto
     contiene aceite de semilla de adormidera yodado con 480 mgI/mL (no yodo puro).
     INN OMS/EMA ficha técnica español: "aceite de adormidera yodado".
       id=904: YODO | INYECTABLE | 480 mg/mL | n=6

  C) DEXTRAN 70 → DEXTRANO 70 (INN-Sp):
     Tears Naturale / Lagrifresh = solución oftálmica lubricante.
     "DEXTRAN" es la forma inglesa; INN-Sp = "dextrano". El número 70 indica fracción
     de peso molecular (dextrano 70 kDa), es parte integral del INN.
       id=2725: DEXTRAN 70||HIPROMELOSA | OFTALMICO | 1 mg/mL + 3 mg/mL | n=8

  D) HIERRO SACAROSA id=2333: "100 mg" → "20 mg/mL" → auto-merge con id=1500:
     Cheltin IV y Hierro Sacarato son presentaciones de 100 mg/5 mL = 20 mg/mL.
     El ETL parseó la dosis total por vial en lugar de la concentración por mL.
     id=1500 (HIERRO SACAROSA 20 mg/mL, n=34) es el grupo canónico.
       id=2333: HIERRO SACAROSA | INYECTABLE | 100 mg | n=2
               → fix conc a 20 mg/mL → auto-merge con id=1500
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


def fix_concentration(con, gid: int, new_conc: str) -> int:
    cur = con.cursor()
    cur.execute("SELECT dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_conc = row[1]
    if old_conc == new_conc:
        print(f"  [OK ya] id={gid}: conc already {new_conc}")
        return 0
    if new_conc == "SIN_CONCENTRACION":
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=?, concentracion_valor=NULL, concentracion_unidad=NULL WHERE id=?",
                    (new_conc, gid))
    else:
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [FIX_CONC] id={gid} ({row[0][:40]}): '{old_conc}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # A. RADIO RA-223 → DICLORURO DE RADIO (223RA)
    print("\n=== A. RADIO RA-223 → DICLORURO DE RADIO (223RA) ===")
    n['A'] += rename_component(con, 3495, "RADIO RA-223", "DICLORURO DE RADIO (223RA)")

    # B. YODO → ACEITE DE ADORMIDERA YODADO
    print("\n=== B. YODO → ACEITE DE ADORMIDERA YODADO (Lipiodol) ===")
    n['B'] += rename_component(con, 904, "YODO", "ACEITE DE ADORMIDERA YODADO")

    # C. DEXTRAN 70 → DEXTRANO 70
    print("\n=== C. DEXTRAN 70 → DEXTRANO 70 ===")
    n['C'] += rename_component(con, 2725, "DEXTRAN 70", "DEXTRANO 70")

    # D. HIERRO SACAROSA 100 mg → 20 mg/mL → auto-merge con id=1500
    print("\n=== D. HIERRO SACAROSA id=2333: 100 mg → 20 mg/mL ===")
    n['D'] += fix_concentration(con, 2333, "20 mg/mL")

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
