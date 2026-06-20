"""
fix_auditoria_conc15.py — Decimoquinta ronda de auditoría.

Correcciones — LIQUIDO_ORAL multi-componente con concentración incompleta o sumada:
  A) ETL omitió segundo componente o sumó todos:
     - id=2820 ACIDO DIATRIZOICO||MEGLUMINA: "760 mg/mL" -> "100 mg/mL + 660 mg/mL" (ETL sumó)
     - id=2827 PAPAVERINA||SIMETICONA: "66 mg/mL" -> "10 mg/mL + 66 mg/mL"
     - id=2909 DEXCLORFENIRAMINA||PARACETAMOL: "100 mg/mL" -> "0.5 mg/mL + 100 mg/mL"
     - id=2974 GUAIFENESINA||TERBUTALINA: "13.3 mg/mL" -> "13.3 mg/mL + 0.3 mg/mL"
     - id=3147 CLORURO DE POTASIO||CLORURO DE SODIO: "12.5 mg/mL" -> "12.5 mg/mL + 37.5 mg/mL"
     - id=3155 CARBOCISTEINA||GUAIACOLATO DE GLICERILO: "30 mg/mL" -> "30 mg/mL + 20 mg/mL"
     - id=3279 GUAYACOLATO DE GLICERILO||N-ACETILCISTEINA: "30 mg/mL" -> "30 mg/mL + 20 mg/mL"
     - id=3289 FENILEFRINA||FEXOFENADINA: "6 mg/mL" -> "3 mg/mL + 6 mg/mL"
     - id=3338 ALGINATO DE SODIO||SIMETICONA (n=1): "25 mg/mL" -> "25 mg/mL + 10 mg/mL"
     - id=3339 ALGINATO DE SODIO||SIMETICONA (n=4): "10 mg/mL" -> "25 mg/mL + 10 mg/mL" -> merge con id=3338
     - id=3342 METOCLOPRAMIDA||SIMETICONA: "1 mg/mL" -> "1 mg/mL + 5 mg/mL"
     - id=3365 AMBROXOL||DEXTROMETORFANO||TEOFILINA: "18.5 mg/mL" -> "2.5 mg/mL + 3 mg/mL + 13 mg/mL" (ETL sumó)
     - id=3380 LORATADINA||NOSCAPINA||TERBUTALINA: "1.8 mg/mL" -> "1 mg/mL + 0.5 mg/mL + 0.3 mg/mL" (ETL sumó)
     - id=3636 ACIDO ALGINICO||BICARBONATO DE SODIO||CARBONATO DE CALCIO: "50 mg/mL" -> "50 mg/mL + 21.3 mg/mL + 32.5 mg/mL"
     - id=3697 GUAIFENESINA||N-ACETILCISTEINA: "20 mg/mL" -> "20 mg/mL + 20 mg/mL"
     - id=3878 ALUMINIO HIDROXIDO||MAGNESIO CARBONATO: "23.9 mg/mL" -> "6.3 mg/mL + 23.9 mg/mL"
  B) BROMEXINA DCI typo id=3285 -> BROMHEXINA||GUAIACOLATO + conc completa -> merge id=3253
  C) CONDROITINA SULFATO DE SODIO||HIPROMELOSA id=3351: LIQUIDO_ORAL -> OFTALMICO + conc completa
     - "Splash Tears" via_normalizada=["TOPICA"] -> clasificación correcta OFTALMICO
     - "1 mg/mL" -> "1 mg/mL + 2 mg/mL" (CONDROITINA=1, HIPROMELOSA=2)
  D) Post-fix auto-merge duplicados
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
    n = {k: 0 for k in ['A', 'B', 'C', 'merge']}

    # -- A. LIQUIDO_ORAL multi-componente ------------------------------------------
    print("\n=== A. LIQUIDO_ORAL multi-componente (16 grupos) ===")
    fixes_a = [
        # (id, new_conc, note)
        (2820, "100 mg/mL + 660 mg/mL",          "A_diatrizoico_meglumina_sum"),
        (2827, "10 mg/mL + 66 mg/mL",             "A_papaverina_simeticona"),
        (2909, "0.5 mg/mL + 100 mg/mL",           "A_dexclorfeniramina_paracetamol"),
        (2974, "13.3 mg/mL + 0.3 mg/mL",          "A_guaifenesina_terbutalina"),
        (3147, "12.5 mg/mL + 37.5 mg/mL",         "A_kcl_nacl"),
        (3155, "30 mg/mL + 20 mg/mL",             "A_carbocisteina_guaiacolato"),
        (3279, "30 mg/mL + 20 mg/mL",             "A_guayacolato_nacetilcisteina"),
        (3289, "3 mg/mL + 6 mg/mL",               "A_fenilefrina_fexofenadina"),
        (3338, "25 mg/mL + 10 mg/mL",             "A_alginato_simeticona_n1"),
        (3339, "25 mg/mL + 10 mg/mL",             "A_alginato_simeticona_n4"),
        (3342, "1 mg/mL + 5 mg/mL",               "A_metoclopramida_simeticona"),
        (3365, "2.5 mg/mL + 3 mg/mL + 13 mg/mL", "A_ambroxol_dextro_teofilina_sum"),
        (3380, "1 mg/mL + 0.5 mg/mL + 0.3 mg/mL","A_loratadina_noscapina_terbu_sum"),
        (3636, "50 mg/mL + 21.3 mg/mL + 32.5 mg/mL", "A_alginico_bicarbonato_calcio"),
        (3697, "20 mg/mL + 20 mg/mL",             "A_guaifenesina_nacetilcisteina"),
        (3878, "6.3 mg/mL + 23.9 mg/mL",          "A_aluminio_magnesio_carbonato"),
    ]
    for gid, new_conc, tag in fixes_a:
        n['A'] += fix_conc(cur, gid, new_conc, tag)

    # -- B. BROMEXINA DCI typo -> BROMHEXINA id=3285 -------------------------------
    print("\n=== B. BROMEXINA DCI typo -> BROMHEXINA ===")
    cur.execute("SELECT dci_key, concentracion_norm, cum_ids FROM grupos_equivalencia WHERE id=3285")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='BROMHEXINA||GUAIACOLATO DE GLICERILO',
                concentracion_norm='0.8 mg/mL + 20 mg/mL'
            WHERE id=3285
        """)
        print(f"  [B] id=3285: dci '{row[0]}'->BROMHEXINA||GUAIACOLATO, conc '{row[1]}'->'0.8 mg/mL + 20 mg/mL'")
        n['B'] += 1
        # Sync cum_normalizado principios_dci BROMEXINA -> BROMHEXINA
        cids = json.loads(row[2] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
            p = cur.fetchone()
            if p and p[0]:
                pdci = json.loads(p[0])
                new_pdci = ["BROMHEXINA" if d == "BROMEXINA" else d for d in pdci]
                if new_pdci != pdci:
                    cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                                (json.dumps(new_pdci), exp, consec))
                    updated += 1
        print(f"  [B] cum_normalizado: {updated} productos BROMEXINA->BROMHEXINA")
    # Merge into id=3253 (BROMHEXINA||GUAIACOLATO DE GLICERILO 0.8 mg/mL + 20 mg/mL, n=20)
    n['merge'] += merge_into(con, 3253, 3285)

    # -- C. CONDROITINA SULFATO DE SODIO||HIPROMELOSA id=3351: LIQUIDO_ORAL -> OFTALMICO
    print("\n=== C. id=3351 CONDROITINA||HIPROMELOSA LIQUIDO_ORAL -> OFTALMICO ===")
    cur.execute("SELECT grupo_via, concentracion_norm FROM grupos_equivalencia WHERE id=3351")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET grupo_via='OFTALMICO', concentracion_norm='1 mg/mL + 2 mg/mL'
            WHERE id=3351
        """)
        print(f"  [C] id=3351: via '{row[0]}'->OFTALMICO, conc '{row[1]}'->'1 mg/mL + 2 mg/mL'")
        n['C'] += 1

    # -- D. Post-fix auto-merge duplicados -----------------------------------------
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
