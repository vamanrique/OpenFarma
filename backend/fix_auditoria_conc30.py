"""
fix_auditoria_conc30.py — Trigésima ronda de auditoría.

Correcciones — forma DE estándar y normalización DCI:
  A) HIERRO (III) OXIDO -> OXIDO DE HIERRO (III) (Caladerm, TOPICO):
     - id=3399: HIERRO (III) OXIDO||OXIDO DE ZINC -> OXIDO DE HIERRO (III)||OXIDO DE ZINC
       (H<Z mismo orden, sin reorden de conc)
  B) CONDROITINA SULFATO DE SODIO -> CONDROITINA SULFATO (viscosuplentes OFTALMICO):
     - id=3351: CONDROITINA SULFATO DE SODIO||HIPROMELOSA (C<H mismo orden, sin reorden)
     - id=3352: CONDROITINA SULFATO DE SODIO||HIALURONATO DE SODIO (C<H mismo orden)
  C) METILO SALICILATO -> SALICILATO DE METILO (id=2789, TOPICO 6.75%+4%):
     - Forma correcta ya usada en grupos 1005, 2704, 2705, 2706, 3625
     - S<Y: orden relativo sin cambio, sin reorden de conc
  D) FLUOR -> FLUORURO (id=3597 Sensitrace trace elements INYECTABLE):
     - Forma INN estándar (FLUORURO DE SODIO ya normalizado en ronda 25)
     - FL< HI: posición relativa sin cambio; id=3540 tiene conc SIN_CONC -> no merge
  E) LUTECIO (177LU) CLORURO -> CLORURO DE LUTECIO (177LU) (id=3553 Lutapol):
     - Aplica forma DE al radiofármaco (singleton INYECTABLE SIN_CONC)
  F) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. HIERRO (III) OXIDO -> OXIDO DE HIERRO (III) ------------------------------
    print("\n=== A. id=3399: HIERRO (III) OXIDO -> OXIDO DE HIERRO (III) ===")
    n['A'] += rename_dci(con, 3399,
                         "OXIDO DE HIERRO (III)||OXIDO DE ZINC",
                         {"HIERRO (III) OXIDO": "OXIDO DE HIERRO (III)"})

    # -- B. CONDROITINA SULFATO DE SODIO -> CONDROITINA SULFATO ----------------------
    print("\n=== B. CONDROITINA SULFATO DE SODIO -> CONDROITINA SULFATO ===")
    cs_map = {"CONDROITINA SULFATO DE SODIO": "CONDROITINA SULFATO"}

    # id=3351: CONDROITINA SULFATO DE SODIO||HIPROMELOSA 1+2 mg/mL (C<H: mismo orden)
    n['B'] += rename_dci(con, 3351,
                         "CONDROITINA SULFATO||HIPROMELOSA",
                         cs_map)
    # id=3352: CONDROITINA SULFATO DE SODIO||HIALURONATO DE SODIO 1.8+1 mg/mL (C<H)
    n['B'] += rename_dci(con, 3352,
                         "CONDROITINA SULFATO||HIALURONATO DE SODIO",
                         cs_map)

    # -- C. METILO SALICILATO -> SALICILATO DE METILO --------------------------------
    print("\n=== C. id=2789: METILO SALICILATO -> SALICILATO DE METILO ===")
    # S<Y: mismo orden relativo en dci_key, sin reorden conc
    n['C'] += rename_dci(con, 2789,
                         "SALICILATO DE METILO||YODO",
                         {"METILO SALICILATO": "SALICILATO DE METILO"})

    # -- D. FLUOR -> FLUORURO (Sensitrace trace elements) ----------------------------
    print("\n=== D. id=3597: FLUOR -> FLUORURO ===")
    # Posición: CROMO < FLUORURO < HIERRO (igual que CROMO < FLUOR < HIERRO)
    n['D'] += rename_dci(con, 3597,
                         "COBRE||CROMO||FLUORURO||HIERRO||MANGANESO||MOLIBDENO||SELENIO||YODO||ZINC",
                         {"FLUOR": "FLUORURO"})

    # -- E. LUTECIO (177LU) CLORURO -> CLORURO DE LUTECIO (177LU) ------------------
    print("\n=== E. id=3553: LUTECIO (177LU) CLORURO -> CLORURO DE LUTECIO (177LU) ===")
    n['E'] += rename_dci(con, 3553,
                         "CLORURO DE LUTECIO (177LU)",
                         {"LUTECIO (177LU) CLORURO": "CLORURO DE LUTECIO (177LU)"})

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
