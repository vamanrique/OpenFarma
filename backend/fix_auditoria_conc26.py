"""
fix_auditoria_conc26.py — Vigesimosexta ronda de auditoría.

Correcciones — ALUMINIO HIDROXIDO, MAGNESIO HIDROXIDO, MAGNESIO CARBONATO:
  A) Casos simples (sin cambio de orden de componentes):
     - id=3277 ALUMINIO HIDROXIDO solo  -> HIDROXIDO DE ALUMINIO (LIQUIDO_ORAL 61.5 mg/mL)
     - id=2981 MAGNESIO HIDROXIDO solo  -> HIDROXIDO DE MAGNESIO (LIQUIDO_ORAL SIN_CONC)
     - id=2982 MAGNESIO HIDROXIDO       -> HIDROXIDO DE MAGNESIO 85 mg/mL -> merge id=2986 (n=26)
     - id=2835 Al||Mg||Sim 40+40+4      -> HdAl||HdMg||Sim -> merge id=3542 (n=93)
     - id=2838 Al||Mg||Sim 80+80+6      -> HdAl||HdMg||Sim
     - id=2839 Al||Mg||Sim 40+20+4      -> HdAl||HdMg||Sim
     - id=2840 Al||Mg||Sim 40 mg/mL     -> HdAl||HdMg||Sim (conc incompleta, no merge)
  B) id=2537: Al||MgCO3||MgOH||Sim 282+282+85+25 -> CarbMg||HdAl||HdMg||Sim
     (conc string idéntico: primeros dos valores iguales, no requiere reorden)
  C) Con reorden de concentracion_norm (orden de componentes cambia):
     - id=1958: Al||Dic 200+100 -> Dic||HdAl, fix conc 200+100 -> 100+200 -> merge id=141 (n=10)
     - id=2841: Al||Dim||MgOH 40+4+40 -> Dim||HdAl||HdMg, fix conc -> 4+40+40 mg/mL
     - id=2912: Al||MgCO3 6.33+23.9 -> CarbMg||HdAl, fix conc -> 23.9+6.33 mg/mL
     - id=3878: Al||MgCO3 6.3+23.9  -> CarbMg||HdAl, fix conc -> 23.9+6.3 mg/mL
     - id=309:  Al||CaCO3||MgOH||Sim 470+410+328+25
                -> CarbCa||HdAl||HdMg||Sim, fix conc -> 410+470+328+25 mg
  D) Post-fix auto-merge duplicados
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


def fix_conc(cur, gid: int, new_conc: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya conc] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [FIX_CONC] id={gid}: '{row[0]}' -> '{new_conc}'")
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
    n = {k: 0 for k in ['A', 'B', 'C', 'merge']}

    ah_map = {"ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO"}
    mh_map = {"MAGNESIO HIDROXIDO": "HIDROXIDO DE MAGNESIO"}
    ah_mh_map = {"ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO",
                 "MAGNESIO HIDROXIDO": "HIDROXIDO DE MAGNESIO"}
    ah_mc_mh_map = {
        "ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO",
        "MAGNESIO CARBONATO": "CARBONATO DE MAGNESIO",
        "MAGNESIO HIDROXIDO": "HIDROXIDO DE MAGNESIO",
    }

    # -- A. Casos simples (sin cambio de orden de componentes) -----------------------
    print("\n=== A. Casos simples: ALUMINIO/MAGNESIO HIDROXIDO -> HIDROXIDO DE... ===")

    # Solo groups
    n['A'] += rename_dci(con, 3277, "HIDROXIDO DE ALUMINIO", ah_map)
    n['A'] += rename_dci(con, 2981, "HIDROXIDO DE MAGNESIO", mh_map)
    n['A'] += rename_dci(con, 2982, "HIDROXIDO DE MAGNESIO", mh_map)
    # auto-merge: 2982 (n=20) -> 2986 (n=6) -> total=26

    # Al||Mg||Simeticona combos (same relative order A<M<S -> H-Al<H-Mg<S)
    new_dci_ams = "HIDROXIDO DE ALUMINIO||HIDROXIDO DE MAGNESIO||SIMETICONA"
    n['A'] += rename_dci(con, 2835, new_dci_ams, ah_mh_map)
    # auto-merge: 2835 (n=92) -> 3542 (n=1) or keep bigger
    n['A'] += rename_dci(con, 2838, new_dci_ams, ah_mh_map)
    n['A'] += rename_dci(con, 2839, new_dci_ams, ah_mh_map)
    n['A'] += rename_dci(con, 2840, new_dci_ams, ah_mh_map)

    # -- B. id=2537 simétrico (conc string idéntico) --------------------------------
    print("\n=== B. id=2537: Al||MgCO3||MgOH||Sim -> CarbMg||HdAl||HdMg||Sim ===")
    n['B'] += rename_dci(con, 2537,
                         "CARBONATO DE MAGNESIO||HIDROXIDO DE ALUMINIO||HIDROXIDO DE MAGNESIO||SIMETICONA",
                         ah_mc_mh_map)

    # -- C. Con reorden de concentracion_norm ----------------------------------------
    print("\n=== C. Con reorden de concentracion_norm ===")

    # id=1958: Al||Dic 200+100 -> Dic||HdAl, conc 200+100 -> 100+200 (Dic=100, Al=200)
    n['C'] += rename_dci(con, 1958,
                         "DICLOFENACO||HIDROXIDO DE ALUMINIO",
                         {"ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO"})
    fix_conc(cur, 1958, "100 mg + 200 mg")
    # auto-merge: 1958 -> 141 (DICLOFENACO||HIDROXIDO DE ALUMINIO 100+200, n=10)

    # id=2841: Al||Dim||MgOH 40+4+40 -> Dim||HdAl||HdMg, conc -> 4+40+40 mg/mL
    n['C'] += rename_dci(con, 2841,
                         "DIMETICONA||HIDROXIDO DE ALUMINIO||HIDROXIDO DE MAGNESIO",
                         ah_mh_map)
    fix_conc(cur, 2841, "4 mg/mL + 40 mg/mL + 40 mg/mL")

    # id=2912: Al||MgCO3 6.33+23.9 -> CarbMg||HdAl, conc -> 23.9+6.33 mg/mL
    n['C'] += rename_dci(con, 2912,
                         "CARBONATO DE MAGNESIO||HIDROXIDO DE ALUMINIO",
                         {"ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO",
                          "MAGNESIO CARBONATO": "CARBONATO DE MAGNESIO"})
    fix_conc(cur, 2912, "23.9 mg/mL + 6.33 mg/mL")

    # id=3878: Al||MgCO3 6.3+23.9 -> CarbMg||HdAl, conc -> 23.9+6.3 mg/mL
    n['C'] += rename_dci(con, 3878,
                         "CARBONATO DE MAGNESIO||HIDROXIDO DE ALUMINIO",
                         {"ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO",
                          "MAGNESIO CARBONATO": "CARBONATO DE MAGNESIO"})
    fix_conc(cur, 3878, "23.9 mg/mL + 6.3 mg/mL")

    # id=309: Al||CaCO3||MgOH||Sim 470+410+328+25 -> CarbCa||HdAl||HdMg||Sim
    # New order: CarbCa(1)=410, HdAl(2)=470, HdMg(3)=328, Sim(4)=25
    n['C'] += rename_dci(con, 309,
                         "CARBONATO DE CALCIO||HIDROXIDO DE ALUMINIO||HIDROXIDO DE MAGNESIO||SIMETICONA",
                         {"ALUMINIO HIDROXIDO": "HIDROXIDO DE ALUMINIO",
                          "CALCIO CARBONATO": "CARBONATO DE CALCIO",
                          "MAGNESIO HIDROXIDO": "HIDROXIDO DE MAGNESIO"})
    fix_conc(cur, 309, "410 mg + 470 mg + 328 mg + 25 mg")

    # -- D. Post-fix auto-merge -------------------------------------------------------
    print("\n=== D. Post-fix auto-merge ===")
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
