"""
fix_auditoria_conc45.py — Cuadragesimoquinta ronda de auditoría.

Correcciones — FLUTICASONA sin ester -> FLUTICASONA PROPIONATO / FLUTICASONA FUROATO:
  Fluticasona tiene dos ésteres distintos, NO intercambiables:
  - PROPIONATO: Flixotide/Flixohaler (inh), Flonase/Nasoblas (nasal), Seretide (con salmeterol), Dymista (con azelastina)
  - FUROATO: Avamys (nasal 27.5mcg), "Furoato De Fluticasona" (INHALADO clasificado así por INVIMA)
  Los grupos pre-existentes FLUTICASONA||VILANTEROL y FLUTICASONA||UMECLIDINIO||VILANTEROL
  ya fueron corregidos a FUROATO en ronda 44.

  A) FLUTICASONA -> FLUTICASONA FUROATO:
     - id=2161: FLUTICASONA INHALADO 27.5mcg/dosis (n=4, "Furoato De Fluticasona") -> sin merge
     - id=1142: FLUTICASONA NASAL 27.5mcg/dosis (n=5, Avamys) -> sin merge
       (vias distintas: INHALADO vs NASAL -> sin colision)

  B) FLUTICASONA -> FLUTICASONA PROPIONATO (monofarmaco):
     - id=676:  FLUTICASONA INHALADO 50mcg/dosis  (n=24, Flixotide) -> sin merge
     - id=2075: FLUTICASONA INHALADO 250mcg/dosis (n=3, Flixohaler) -> sin merge
     - id=3257: FLUTICASONA NASAL 0.5mg/mL        (n=1, Nasoblas)  -> sin merge

  C) FLUTICASONA||SALMETEROL -> FLUTICASONA PROPIONATO||SALMETEROL (Seretide):
     - id=605:  INHALADO 500mcg/dosis + 50mcg/dosis (n=43) -> sin merge
     - id=606:  INHALADO 100mcg/dosis + 50mcg/dosis (n=5)  -> sin merge
     - id=674:  INHALADO 125mcg/dosis + 25mcg/dosis (n=24) -> sin merge
     - id=675:  INHALADO 250mcg/dosis + 25mcg/dosis (n=8)  -> sin merge
     - id=1341: INHALADO 250mcg/dosis + 50mcg/dosis (n=55) -> sin merge

  D) AZELASTINA||FLUTICASONA -> AZELASTINA||FLUTICASONA PROPIONATO (Dymista/Azec):
     - id=2100: NASAL 137mcg/dosis + 50mcg/dosis (n=12) -> sin merge
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    ff_map = {"FLUTICASONA": "FLUTICASONA FUROATO"}
    fp_map = {"FLUTICASONA": "FLUTICASONA PROPIONATO"}

    # -- A. FLUTICASONA -> FLUTICASONA FUROATO ----------------------------------------
    print("\n=== A. FLUTICASONA -> FLUTICASONA FUROATO ===")
    # id=2161: INHALADO 27.5mcg (brand=Furoato De Fluticasona)
    n['A'] += rename_dci(con, 2161, "FLUTICASONA FUROATO", ff_map)
    # id=1142: NASAL 27.5mcg (brand=Avamys)
    n['A'] += rename_dci(con, 1142, "FLUTICASONA FUROATO", ff_map)

    # -- B. FLUTICASONA -> FLUTICASONA PROPIONATO (mono) ------------------------------
    print("\n=== B. FLUTICASONA -> FLUTICASONA PROPIONATO (mono) ===")
    # id=676: INHALADO 50mcg (Flixotide)
    n['B'] += rename_dci(con, 676, "FLUTICASONA PROPIONATO", fp_map)
    # id=2075: INHALADO 250mcg (Flixohaler)
    n['B'] += rename_dci(con, 2075, "FLUTICASONA PROPIONATO", fp_map)
    # id=3257: NASAL 0.5mg/mL (Nasoblas)
    n['B'] += rename_dci(con, 3257, "FLUTICASONA PROPIONATO", fp_map)

    # -- C. FLUTICASONA||SALMETEROL -> FLUTICASONA PROPIONATO||SALMETEROL (Seretide) --
    print("\n=== C. FLUTICASONA||SALMETEROL -> FLUTICASONA PROPIONATO||SALMETEROL ===")
    for gid in [605, 606, 674, 675, 1341]:
        n['C'] += rename_dci(con, gid, "FLUTICASONA PROPIONATO||SALMETEROL", fp_map)

    # -- D. AZELASTINA||FLUTICASONA -> AZELASTINA||FLUTICASONA PROPIONATO (Dymista) ---
    print("\n=== D. AZELASTINA||FLUTICASONA -> AZELASTINA||FLUTICASONA PROPIONATO ===")
    n['D'] += rename_dci(con, 2100, "AZELASTINA||FLUTICASONA PROPIONATO", fp_map)

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
