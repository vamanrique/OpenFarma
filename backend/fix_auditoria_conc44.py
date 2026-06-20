"""
fix_auditoria_conc44.py — Cuadragesimocuarta ronda de auditoría.

Correcciones:
  A) ACEITE DE SOJA -> ACEITE DE SOYA (conv. DB: SOYA es la denominación mayoritaria):
     - id=3212: ACEITE DE SOJA||TRIGLICERIDOS DE CADENA MEDIA||TRIGLICERIDOS OMEGA 3
       INYECTABLE 20% (n=2, Lipoplus) -> sin merge

  B) FLUTICASONA -> FLUTICASONA FUROATO (ester incorrecto para productos Relvar/Trelegy):
     Los productos Relvar Ellipta y Trelegy Ellipta contienen fluticasona FUROATO
     (no propionato). La DB tenía solo 'FLUTICASONA' sin especificar el ester.
     - id=1888: FLUTICASONA||VILANTEROL INHALADO 100+25mcg/dosis (n=3, Relvar 100)
       -> FLUTICASONA FUROATO||VILANTEROL (sin merge; no existe FF||VI 100+25)
     - id=1911: FLUTICASONA||VILANTEROL INHALADO 184+22mcg/dosis (n=2, Relvar 200)
       -> FLUTICASONA FUROATO||VILANTEROL
       auto-merge -> id=1910 (FF||VI 184+22, n=1 -> n=3)
     - id=2170: FLUTICASONA||UMECLIDINIO||VILANTEROL INHALADO 100+62.5+25mcg/dosis
       (n=2, Trelegy Ellipta) -> FLUTICASONA FUROATO||UMECLIDINIO||VILANTEROL (sin merge)
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
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # -- A. ACEITE DE SOJA -> ACEITE DE SOYA (id=3212) --------------------------------
    print("\n=== A. id=3212: ACEITE DE SOJA -> ACEITE DE SOYA ===")
    n['A'] += rename_dci(
        con, 3212,
        "ACEITE DE SOYA||TRIGLICERIDOS DE CADENA MEDIA||TRIGLICERIDOS OMEGA 3",
        {"ACEITE DE SOJA": "ACEITE DE SOYA"}
    )

    # -- B. FLUTICASONA -> FLUTICASONA FUROATO (Relvar/Trelegy Ellipta) ---------------
    print("\n=== B. FLUTICASONA -> FLUTICASONA FUROATO (Relvar/Trelegy) ===")
    ff_map = {"FLUTICASONA": "FLUTICASONA FUROATO"}
    # id=1888: Relvar 100mcg/25mcg -> sin merge (no existe FF||VI 100+25)
    n['B'] += rename_dci(con, 1888, "FLUTICASONA FUROATO||VILANTEROL", ff_map)
    # id=1911: Relvar 200mcg/25mcg -> auto-merge en id=1910 (n=1 -> n=3)
    n['B'] += rename_dci(con, 1911, "FLUTICASONA FUROATO||VILANTEROL", ff_map)
    # id=2170: Trelegy Ellipta -> sin merge (no existe FF||UMECLIDINIO||VI group)
    n['B'] += rename_dci(con, 2170, "FLUTICASONA FUROATO||UMECLIDINIO||VILANTEROL", ff_map)

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
