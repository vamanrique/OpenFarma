"""
fix_auditoria_conc13.py — Decimotercera ronda de auditoría.

Correcciones:
  A) DESLORATADINA id=3095: "0.001 mg/mL" -> "0.5 mg/mL"
     - ETL nota: "0.05 por 100 mL" -> leyó mg/100mL en vez de g/100mL -> 1000x error
     - Sync concentracion_mg_ml en cum_normalizado
     - Merge en id=3094 (DESLORATADINA 0.5 mg/mL, n=66)
  B) METRONIDAZOL id=2601: "80 mg/mL" -> "50 mg/mL"
     - ETL nota: "8000mg/100mL = 80 mg/mL" vs nombre producto "250 Mg/5Ml" = 50 mg/mL
     - Nombre del producto es autoritativo (100x error en dato fuente)
     - Merge en id=2599 (METRONIDAZOL 50 mg/mL, n=19)
  C) Multi-componente OFTALMICO con concentración incompleta (6 grupos):
     - ETL solo capturó el componente principal; falta el segundo
     - id=3366 BRINZOLAMIDA||TIMOLOL: "10 mg/mL" -> "10 mg/mL + 5 mg/mL"
     - id=2832 CROMOGLICATO DE SODIO||NAFAZOLINA: "40 mg/mL" -> "40 mg/mL + 0.2 mg/mL"
     - id=3340 DEXAMETASONA||MOXIFLOXACINO: "5 mg/mL" -> "1 mg/mL + 5 mg/mL"
     - id=3665 DEXAMETASONA||NAFAZOLINA: "1 mg/mL" -> "1 mg/mL + 0.12 mg/mL"
     - id=3476 FLUOROMETOLONA||TETRAHIDROZOLINA: "1 mg/mL" -> "1 mg/mL + 0.25 mg/mL"
     - id=3076 LATANOPROST||TIMOLOL: "5 mg/mL" -> "0.05 mg/mL + 5 mg/mL"
  D) TAVOPROST||TIMOLOL id=3283: DCI typo + concentración
     - dci_key: "TAVOPROST||TIMOLOL" -> "TIMOLOL||TRAVOPROST" (typo TAVOPROST->TRAVOPROST)
     - concentracion_norm: "2 mg/mL" -> "5 mg/mL + 0.04 mg/mL"
     - Sync cum_normalizado principios_dci: TAVOPROST -> TRAVOPROST
     - Merge en id=3709 (TIMOLOL||TRAVOPROST 5 mg/mL + 0.04 mg/mL, n=4)
  E) Post-fix auto-merge duplicados
"""
import sqlite3, sys, json
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. DESLORATADINA id=3095: 0.001 mg/mL (1000x error) -> 0.5 mg/mL ----------
    print("\n=== A. DESLORATADINA id=3095 ===")
    n['A'] += fix_conc(cur, 3095, "0.5 mg/mL", "A_desloratadina_1000x")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=3095")
    g = cur.fetchone()
    if g:
        cids = json.loads(g[0] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("""
                UPDATE cum_normalizado
                SET concentracion_mg_ml=0.5
                WHERE expediente_cum=? AND consecutivo_cum=?
                AND concentracion_mg_ml < 0.01
            """, (exp, consec))
            if cur.rowcount:
                updated += 1
        print(f"  [A] cum_normalizado: {updated} productos actualizados a 0.5 mg/mL")
    n['merge'] += merge_into(con, 3094, 3095)

    # -- B. METRONIDAZOL id=2601: 80 mg/mL -> 50 mg/mL ----------------------------
    print("\n=== B. METRONIDAZOL id=2601 ===")
    n['B'] += fix_conc(cur, 2601, "50 mg/mL", "B_metronidazol_nombre_autoritativo")
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=2601")
    g = cur.fetchone()
    if g:
        cids = json.loads(g[0] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("""
                UPDATE cum_normalizado
                SET concentracion_mg_ml=50.0
                WHERE expediente_cum=? AND consecutivo_cum=?
                AND concentracion_mg_ml > 70.0
            """, (exp, consec))
            if cur.rowcount:
                updated += 1
        print(f"  [B] cum_normalizado: {updated} productos actualizados a 50 mg/mL")
    n['merge'] += merge_into(con, 2599, 2601)

    # -- C. Multi-componente OFTALMICO: concentración incompleta -------------------
    print("\n=== C. Multi-componente OFTALMICO: añadir segunda concentracion ===")
    # DCI alphabetical order determines component value order
    # id=3366 BRINZOLAMIDA(10) + TIMOLOL(5): B < T -> "10 mg/mL + 5 mg/mL"
    n['C'] += fix_conc(cur, 3366, "10 mg/mL + 5 mg/mL", "C_brinzolamida_timolol")
    # id=2832 CROMOGLICATO DE SODIO(40) + NAFAZOLINA(0.2): C < N -> "40 mg/mL + 0.2 mg/mL"
    n['C'] += fix_conc(cur, 2832, "40 mg/mL + 0.2 mg/mL", "C_cromoglicato_nafazolina")
    # id=3340 DEXAMETASONA(1) + MOXIFLOXACINO(5): D < M -> "1 mg/mL + 5 mg/mL"
    n['C'] += fix_conc(cur, 3340, "1 mg/mL + 5 mg/mL", "C_dexametasona_moxifloxacino")
    # id=3665 DEXAMETASONA(1) + NAFAZOLINA(0.12): D < N -> "1 mg/mL + 0.12 mg/mL"
    n['C'] += fix_conc(cur, 3665, "1 mg/mL + 0.12 mg/mL", "C_dexametasona_nafazolina")
    # id=3476 FLUOROMETOLONA(1) + TETRAHIDROZOLINA(0.25): F < T -> "1 mg/mL + 0.25 mg/mL"
    n['C'] += fix_conc(cur, 3476, "1 mg/mL + 0.25 mg/mL", "C_fluorometolona_tetrahidrozolina")
    # id=3076 LATANOPROST(0.05) + TIMOLOL(5): L < T -> "0.05 mg/mL + 5 mg/mL"
    n['C'] += fix_conc(cur, 3076, "0.05 mg/mL + 5 mg/mL", "C_latanoprost_timolol")

    # -- D. TAVOPROST||TIMOLOL id=3283: DCI typo + conc fix -----------------------
    print("\n=== D. TAVOPROST||TIMOLOL id=3283 -> TIMOLOL||TRAVOPROST ===")
    cur.execute("SELECT dci_key, concentracion_norm, cum_ids FROM grupos_equivalencia WHERE id=3283")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='TIMOLOL||TRAVOPROST', concentracion_norm='5 mg/mL + 0.04 mg/mL'
            WHERE id=3283
        """)
        print(f"  [D] id=3283: dci '{row[0]}'->'TIMOLOL||TRAVOPROST', conc '{row[1]}'->'5 mg/mL + 0.04 mg/mL'")
        n['D'] += 1
        # Sync cum_normalizado: principios_dci TAVOPROST -> TRAVOPROST
        cids = json.loads(row[2] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("""
                SELECT principios_dci FROM cum_normalizado
                WHERE expediente_cum=? AND consecutivo_cum=?
            """, (exp, consec))
            p = cur.fetchone()
            if p and p[0]:
                pdci = json.loads(p[0])
                new_pdci = ["TRAVOPROST" if d == "TAVOPROST" else d for d in pdci]
                if new_pdci != pdci:
                    cur.execute("""
                        UPDATE cum_normalizado SET principios_dci=?
                        WHERE expediente_cum=? AND consecutivo_cum=?
                    """, (json.dumps(new_pdci), exp, consec))
                    updated += 1
        print(f"  [D] cum_normalizado: {updated} productos TAVOPROST->TRAVOPROST")
    n['merge'] += merge_into(con, 3709, 3283)

    # -- E. Post-fix auto-merge duplicados ------------------------------------------
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

    # -- Fix n_productos ------------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen --------------------------------------------------------------------
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
