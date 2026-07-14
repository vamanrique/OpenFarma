"""
fix_auditoria_conc7.py — Séptima ronda de auditoría.

Correcciones:
  A) Normalizar 'ui' minúscula → 'UI' en concentracion_norm (152 grupos)
  B) COLECALCIFEROL 16000 UI → 400 UI (conversión errónea mcg→UI doble):
     - id=1336 CALCIO||COLECALCIFEROL: "600mg+16000UI" → "600mg+400UI"
     - id=1505 CALCIO||COLECALCIFEROL||ISOFLAVONAS||MAGNESIO: "950mg+16000UI+50+50" → "950mg+400UI+50+50" → merge id=1501
     - id=1506 ACIDO FOLICO||CALCIO||COLECALCIFEROL||HIERRO: "+16000UI+" → "+400UI+"
  C) CALCIO||COLECALCIFEROL concentraciones erróneas:
     - id=847: "600mg+8UI" → "600mg+200UI" (8UI←→200UI doble conversión) → merge id=1552
     - id=1522: "1657.895mg+800UI" → "400mg+800UI" (citrato calcio→elemental)
  D) EPINEFRINA||LIDOCAINA formato per-cartridge → per-mL:
     - id=716: "0.0225mg+36mg" → "0.0125mg/mL+20mg/mL" (2%+1:80000, 1.8mL cartridge)
     - id=731: "0.01mg+20mg" → "0.01mg/mL+20mg/mL" (2%+1:100000, ya per-mL pero sin /mL)
  E) OXITOCINA id=2812: "10 UI" → "10 UI/mL" → merge id=2813 (Syntocinon 1mL amp)
  F) Post-fix auto-merge duplicados
"""
import sqlite3, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP merge] {del_id}->{keep_id}: missing")
        return 0
    merged = list(dict.fromkeys(
        json.loads(keep[0] or '[]') + json.loads(rem[0] or '[]')
    ))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}->{keep_id}: total={len(merged)}")
    return 1


def fix_conc(cur, gid: int, new_conc: str, tag: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{row[0]}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. Normalizar 'ui' minuscula -> 'UI' ------------------------------------
    print("\n=== A. Normalizar lowercase ui -> UI ===")
    # Pattern: number(s) + space + "ui" at end or before "/" or before " +"
    cur.execute("""
        SELECT id, concentracion_norm FROM grupos_equivalencia
        WHERE concentracion_norm LIKE '% ui%'
           OR concentracion_norm LIKE '%ui/%'
    """)
    rows = cur.fetchall()
    updated = 0
    for gid, conc in rows:
        # Replace " ui" -> " UI" (handles " ui/mL", " ui\n", " ui " etc.)
        new_conc = re.sub(r' ui(?=[/ \n]|$)', ' UI', conc)
        if new_conc != conc:
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?",
                        (new_conc, gid))
            updated += 1
    print(f"  {updated} grupos actualizados")
    n['A'] = updated

    # -- B. COLECALCIFEROL 16000 UI -> 400 UI (doble conversion mcg->IU) --------
    print("\n=== B. COLECALCIFEROL 16000 UI -> 400 UI ===")
    # id=1336 CALCIO||COLECALCIFEROL
    n['B'] += fix_conc(cur, 1336, "600 mg + 400 UI", "B_caltrate_D3")
    # id=1505 -> merge into id=1501 (same formula "950mg+400UI+50+50")
    n['B'] += fix_conc(cur, 1505, "950 mg + 400 UI + 50 mg + 50 mg", "B_calcibon_soya")
    n['merge'] += merge_into(con, 1501, 1505)
    # id=1506 ACIDO FOLICO||CALCIO||COLECALCIFEROL||HIERRO
    n['B'] += fix_conc(cur, 1506, "0.4 mg + 200 mg + 400 UI + 18 mg", "B_calcibon_natal")

    # -- C. CALCIO||COLECALCIFEROL concentraciones erroneas ----------------------
    print("\n=== C. CALCIO||COLECALCIFEROL erroneas ===")
    # id=847 "600mg+8UI" -> "600mg+200UI" (Zivical D = 600mg Ca + 200 UI D3)
    n['C'] += fix_conc(cur, 847, "600 mg + 200 UI", "C_zivical_D3_8->200")
    n['merge'] += merge_into(con, 1552, 847)
    # id=1522 "1657.895mg+800UI" -> "400mg+800UI" (Ca citrate salt -> elemental)
    # 1657.895mg Ca citrate anhydrous * 24.12% = 400.0mg elemental Ca
    n['C'] += fix_conc(cur, 1522, "400 mg + 800 UI", "C_calcibon_citrate->elemental")

    # -- D. EPINEFRINA||LIDOCAINA per-cartridge -> per-mL ------------------------
    print("\n=== D. EPINEFRINA||LIDOCAINA formato ===")
    # id=716 Newcaina 2% E80: 36mg/1.8mL=20mg/mL lid, 0.0225mg/1.8mL=0.0125mg/mL epi
    n['D'] += fix_conc(cur, 716, "0.0125 mg/mL + 20 mg/mL", "D_newcaina_2pct_E80")
    # id=731 Lidocaina 2% E-100: values already per-mL, just missing /mL unit
    # 20mg/mL=2%, 0.01mg/mL=1:100000 epi
    n['D'] += fix_conc(cur, 731, "0.01 mg/mL + 20 mg/mL", "D_lidocaina_2pct_E100")

    # -- E. OXITOCINA id=2812 "10 UI" -> "10 UI/mL" -> merge id=2813 ------------
    print("\n=== E. OXITOCINA ===")
    # Syntocinon 10 UI = 10 IU in 1mL ampule = 10 UI/mL
    n['E'] += fix_conc(cur, 2812, "10 UI/mL", "E_syntocinon_10UI->perml")
    n['merge'] += merge_into(con, 2813, 2812)

    # -- F. Post-fix auto-merge duplicados ---------------------------------------
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

    # -- Fix n_productos ---------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen -----------------------------------------------------------------
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
