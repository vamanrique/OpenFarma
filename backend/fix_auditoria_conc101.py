"""
fix_auditoria_conc101.py — Centésimoprima ronda de auditoría.

  A) Concentraciones GBq parseadas como 'g' — generadores radiofarmacéuticos:
     El ETL no reconoció 'GBq' (gigabecquerel) y lo truncó a 'g' (gramos).
     Los generadores Mo-99/Tc-99m y el precursor Lu-177 se expresan en GBq
     de actividad, no en gramos → SIN_CONCENTRACION para agrupación correcta.
       id=3496: MOLIBDATO DE SODIO (99MO)||PERTECNETATO... | 120 g → SIN_CONCENTRACION
               → auto-merge con id=3008 (SIN_CONCENTRACION, n=2)
       id=3589: MOLIBDATO DE SODIO (99MO)||PERTECNETATO... | 43 g → SIN_CONCENTRACION
               → auto-merge con id=3008 (tras merge anterior)
       id=3640: CLORURO DE LUTECIO (177LU) | 40 g → SIN_CONCENTRACION
               → auto-merge con id=3553 (SIN_CONCENTRACION, n=1)

  B) MERTIATIDA → TECNECIO (99MTC) MERTIATIDA (consistencia radiofármacos):
     Nephromag y Technescan MAG3 son kits para preparación Tc-99m MAG3 (renal
     tubular scan). Por convención DB, el INN incluye el radionucleido.
       id=2010: MERTIATIDA | INYECTABLE | 0.2 mg | n=1
       id=3623: MERTIATIDA | INYECTABLE | SIN_CONCENTRACION | n=1
     No auto-merge: concentraciones distintas.

  C) EDOTREOTIDA → GALIO (68GA) EDOTREOTIDA (WHO INN: gallium (68Ga) edotreotide):
     Tektrotyd = kit para preparación Ga-68 DOTATOC (DOTA-Tyr3-octreotida) para
     PET oncológico. El INN OMS incluye el radionucleido: GALIO (68GA) EDOTREOTIDA.
     Patrón análogo a TECNECIO (99MTC) SESTAMIBI, TECNECIO (99MTC) PENTETATO, etc.
       id=2395: EDOTREOTIDA | INYECTABLE | 0.02 mg | n=1
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
    n = {k: 0 for k in ['A', 'B', 'C', 'merge']}

    # A. GBq misread as g → SIN_CONCENTRACION
    print("\n=== A. Generadores radiofarmacéuticos: g (GBq) → SIN_CONCENTRACION ===")
    n['A'] += fix_concentration(con, 3496, "SIN_CONCENTRACION")  # MOLIBDATO 120 GBq
    n['A'] += fix_concentration(con, 3589, "SIN_CONCENTRACION")  # MOLIBDATO 43 GBq
    n['A'] += fix_concentration(con, 3640, "SIN_CONCENTRACION")  # LUTECIO 40 GBq

    # B. MERTIATIDA → TECNECIO (99MTC) MERTIATIDA
    print("\n=== B. MERTIATIDA → TECNECIO (99MTC) MERTIATIDA ===")
    for gid in [2010, 3623]:
        n['B'] += rename_component(con, gid, "MERTIATIDA", "TECNECIO (99MTC) MERTIATIDA")

    # C. EDOTREOTIDA → GALIO (68GA) EDOTREOTIDA
    print("\n=== C. EDOTREOTIDA → GALIO (68GA) EDOTREOTIDA ===")
    n['C'] += rename_component(con, 2395, "EDOTREOTIDA", "GALIO (68GA) EDOTREOTIDA")

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
