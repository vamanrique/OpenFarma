"""
fix_auditoria_conc16.py — Decimosexta ronda de auditoría.

Correcciones — Multi-componente INYECTABLE y TOPICO:
  A) INYECTABLE — ETL omitió, sumó o usó unidad incorrecta:
     - id=586  ACEITE DE OLIVA||ACEITE DE SOYA: "200 mg/mL" -> "160 mg/mL + 40 mg/mL" (ETL sumó)
     - id=212  CLORURO DE SODIO||DEXTROSA D5/0.45%NS: "50 mg/mL" -> "4.5 mg/mL + 50 mg/mL"
     - id=3156 CLORURO DE SODIO||DEXTROSA D5/0.9%NS: "5%" -> "9 mg/mL + 50 mg/mL" -> merge id=2759
     - id=3278 CLORURO DE CALCIO||CLORURO DE POTASIO||CLORURO DE SODIO||LACTATO DE SODIO:
               "0.02 g" -> "0.2 mg/mL + 0.3 mg/mL + 6 mg/mL + 3.1 mg/mL" (Ringer's Lactate)
     - id=3550 DEXTROSA||DOBUTAMINA "Docarip 1 Mg/Ml": "1 mg" -> "50 mg/mL + 1 mg/mL"
     - id=1852 DEXTROSA||NITROGLICERINA: "0.105 mg/mL" -> "42.59 mg/mL + 0.105 mg/mL"
  B) TOPICO — concentración corresponde a solo uno de los componentes:
     (componentes en mg/g, concentracion_norm en %; 10 mg/g = 1%)
     - id=447  ACIDO GLICOLICO(100mg/g)||HIDROQUINONA(20mg/g): "10%" -> "10% + 2%"
     - id=508  LIDOCAINA(25mg/g)||PRILOCAINA(25mg/g): "2.5%" -> "2.5% + 2.5%" (EMLA)
     - id=902  MINOXIDIL(50mg/g)||TRETINOINA(0.25mg/g): "5%" -> "5% + 0.025%"
     - id=1200 ACIDO LACTICO(45.24mg/g)||ACIDO SALICILICO(180.95mg/g): "4.52%" -> "4.52% + 18.1%"
     - id=1258 ACIDO LACTICO(50)||ACIDO SALICILICO(200)||POLIETILENGLICOL 6000(10):
               "5%" -> "5% + 20% + 1%"
     - id=1596 ACIDO BENZOICO(50)||ACIDO SALICILICO(50)||RESORCINOL(30): "5%" -> "5% + 5% + 3%"
     - id=2147 ADAPALENO(1mg/g)||CLINDAMICINA(10mg/g): "1%" -> "0.1% + 1%" (Epiduo standard)
     - id=2894 BORNANONA(25mg/g)||HIDROQUINONA(50mg/g): "5%" -> "2.5% + 5%"
  C) Post-fix auto-merge duplicados
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


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
    n = {k: 0 for k in ['A', 'B', 'merge']}

    # -- A. INYECTABLE multi-componente -------------------------------------------
    print("\n=== A. INYECTABLE multi-componente ===")
    # Clinoleic/Intralipid: ACEITE DE OLIVA=160 + ACEITE DE SOYA=40 -> ETL sumó A<S
    n['A'] += fix_conc(cur, 586, "160 mg/mL + 40 mg/mL", "A_aceite_oliva_soya_sum")
    # D5/0.45%NS: CLORURO DE SODIO=4.5 + DEXTROSA=50 C<D
    n['A'] += fix_conc(cur, 212, "4.5 mg/mL + 50 mg/mL", "A_d5_045_ns")
    # D5/0.9%NS: CLORURO DE SODIO=9 + DEXTROSA=50 C<D -> merge id=2759 (same conc, n=6)
    n['A'] += fix_conc(cur, 3156, "9 mg/mL + 50 mg/mL", "A_d5_09_ns")
    n['merge'] += merge_into(con, 2759, 3156)
    # Ringer's Lactate: 4-component, "0.02 g" was CaCl/100mL in grams
    n['A'] += fix_conc(cur, 3278, "0.2 mg/mL + 0.3 mg/mL + 6 mg/mL + 3.1 mg/mL", "A_ringers_lactate")
    # Docarip 1mg/mL: DEXTROSA=50 (vehicle) + DOBUTAMINA=1 D<D -> DEXT<DOBU (E<O)
    n['A'] += fix_conc(cur, 3550, "50 mg/mL + 1 mg/mL", "A_dextrosa_dobutamina")
    # NTG en dextrosa 5%: DEXTROSA=42.59 + NITROGLICERINA=0.105 D<N
    n['A'] += fix_conc(cur, 1852, "42.59 mg/mL + 0.105 mg/mL", "A_dextrosa_nitroglicerina")

    # -- B. TOPICO multi-componente (componentes en mg/g -> %) -------------------
    print("\n=== B. TOPICO multi-componente ===")
    fixes_b = [
        # (id, new_conc, tag)
        (447,  "10% + 2%",          "B_glicol_hidroquinona"),
        (508,  "2.5% + 2.5%",       "B_lidocaina_prilocaina_emla"),
        (902,  "5% + 0.025%",        "B_minoxidil_tretinoina"),
        (1200, "4.52% + 18.1%",      "B_lactco_salicilico"),
        (1258, "5% + 20% + 1%",      "B_lactco_salicilico_peg"),
        (1596, "5% + 5% + 3%",       "B_benzoico_salicilico_resorcinol"),
        (2147, "0.1% + 1%",          "B_adapaleno_clindamicina_epiduo"),
        (2894, "2.5% + 5%",          "B_bornanona_hidroquinona"),
    ]
    for gid, new_conc, tag in fixes_b:
        n['B'] += fix_conc(cur, gid, new_conc, tag)

    # -- C. Post-fix auto-merge duplicados ----------------------------------------
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

    # -- Fix n_productos -----------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen -------------------------------------------------------------------
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
