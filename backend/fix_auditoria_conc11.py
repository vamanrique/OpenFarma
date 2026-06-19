"""
fix_auditoria_conc11.py — Undécima ronda de auditoría.

Correcciones:
  A) TIMOLOL||TRAVOPROST id=3709,3710: ETL dividió mg totales del frasco entre volumen
     - id=3709: "0.5 mg/mL + 0.004 mg/mL" (5mg/10mL, 0.04mg/10mL) -> "5 mg/mL + 0.04 mg/mL"
     - id=3710: "1 mg/mL + 0.008 mg/mL" (5mg/5mL, 0.04mg/5mL) -> "5 mg/mL + 0.04 mg/mL" -> merge id=3709
  B) LOTEPREDNOL ETABONATO: normalizar dci + corregir concentraciones
     - id=3523: dci "LOTEPREDNOL ETABONATO" -> "LOTEPREDNOL", conc "5 mg/mL" -> "2 mg/mL"
       (productos TQ Oftaprednol tienen concentracion_mg_ml=2.0, non 5.0)
     - id=3524: dci "LOTEPREDNOL ETABONATO" -> "LOTEPREDNOL", conc "0.002 mg/mL" -> "2 mg/mL"
       (nota confirma "0.002 mg/mL (2 mcg/mL)" -> error 1000x, debe ser 2 mg/mL = 0.2%)
     - Actualizar cum_normalizado principios_dci para ambos grupos
     - Post-merge: ambos -> id=3481 (LOTEPREDNOL 2 mg/mL)
  C) OXITETRACICLINA||POLIMIXINA B OFTALMICO id=3312: ETL calculó 100x menos
     - nota: "0.005 g/100g = 0.05 mg/g" pero Terramycin es 0.5 g/100g = 5 mg/g
     - "0.05 mg/g + 0.01 mg/g" -> "5 mg/g + 10000 UI/g" -> merge id=3311
  D) OXITETRACICLINA||POLIMIXINA B id=3310: via TOPICO -> OFTALMICO + conc % -> mg/g
     - "TQ Oxyoftal Unguento Oftalmico" es producto oftálmico, no tópico
     - "0.5% + 0.001%" -> "5 mg/g + 10000 UI/g" -> merge id=3311
  E) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. TIMOLOL||TRAVOPROST: total/volume error --------------------------------
    print("\n=== A. TIMOLOL||TRAVOPROST ETL volume error ===")
    # Biofocus 10mL: 5mg timolol + 0.04mg travoprost -> 0.5+0.004 (wrong: divided by vol)
    n['A'] += fix_conc(cur, 3709, "5 mg/mL + 0.04 mg/mL", "A_timolol_travoprost_10mL")
    # Biofocus 5mL: same drug, same concentration, different bottle size
    n['A'] += fix_conc(cur, 3710, "5 mg/mL + 0.04 mg/mL", "A_timolol_travoprost_5mL")
    # Same dci+via+conc after fix -> merge 3710 into 3709
    n['merge'] += merge_into(con, 3709, 3710)

    # -- B. LOTEPREDNOL ETABONATO: dci normalization + concentration fixes ---------
    print("\n=== B. LOTEPREDNOL ETABONATO normalization ===")

    # B1: id=3523 dci "LOTEPREDNOL ETABONATO" -> "LOTEPREDNOL", conc "5 mg/mL" -> "2 mg/mL"
    # Products (20086574-1, 20086574-2) have concentracion_mg_ml=2.0 in cum_normalizado
    cur.execute("SELECT dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=3523")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='LOTEPREDNOL', concentracion_norm='2 mg/mL'
            WHERE id=3523
        """)
        print(f"  [B1] id=3523: dci '{row[0]}' -> 'LOTEPREDNOL', conc '{row[1]}' -> '2 mg/mL'")
        n['B'] += 1

    # B2: id=3524 dci + conc (0.002 mg/mL = 1000x error -> 2 mg/mL = 0.2%)
    cur.execute("SELECT dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=3524")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='LOTEPREDNOL', concentracion_norm='2 mg/mL'
            WHERE id=3524
        """)
        print(f"  [B2] id=3524: dci '{row[0]}' -> 'LOTEPREDNOL', conc '{row[1]}' -> '2 mg/mL'")
        n['B'] += 1

    # B3: sync cum_normalizado principios_dci: LOTEPREDNOL ETABONATO -> LOTEPREDNOL
    cur.execute("""
        SELECT expediente_cum, consecutivo_cum, principios_dci
        FROM cum_normalizado
        WHERE principios_dci LIKE '%LOTEPREDNOL ETABONATO%'
    """)
    updated_cum = 0
    for exp, consec, pdci_json in cur.fetchall():
        pdci = json.loads(pdci_json) if pdci_json else []
        new_pdci = ["LOTEPREDNOL" if p == "LOTEPREDNOL ETABONATO" else p for p in pdci]
        if new_pdci != pdci:
            cur.execute(
                "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                (json.dumps(new_pdci), exp, consec)
            )
            updated_cum += 1
    print(f"  [B3] cum_normalizado: {updated_cum} registros actualizados")

    # -- C. OXITETRACICLINA||POLIMIXINA B id=3312: 100x error ---------------------
    print("\n=== C. OXITETRACICLINA||POLIMIXINA B id=3312 OFTALMICO ===")
    # Terramycin ophthalmic ointment: 0.5 g/100g = 5 mg/g OTC + 10000 UI/g polymyxin B
    # ETL note: "0.005 g/100g = 0.05 mg/g" (100x too low) — raw was likely 0.5 g/100g
    n['C'] += fix_conc(cur, 3312, "5 mg/g + 10000 UI/g", "C_terramycin_oftalmico")
    n['merge'] += merge_into(con, 3311, 3312)

    # -- D. OXITETRACICLINA||POLIMIXINA B id=3310: TOPICO -> OFTALMICO + % -> mg/g
    print("\n=== D. OXITETRACICLINA||POLIMIXINA B id=3310 TOPICO -> OFTALMICO ===")
    cur.execute("SELECT grupo_via, concentracion_norm FROM grupos_equivalencia WHERE id=3310")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET grupo_via='OFTALMICO', concentracion_norm='5 mg/g + 10000 UI/g'
            WHERE id=3310
        """)
        print(f"  [D] id=3310: via '{row[0]}' -> 'OFTALMICO', conc '{row[1]}' -> '5 mg/g + 10000 UI/g'")
        n['D'] += 1
    n['merge'] += merge_into(con, 3311, 3310)

    # -- E. Post-fix auto-merge duplicados -----------------------------------------
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
