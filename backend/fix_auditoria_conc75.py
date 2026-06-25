"""
fix_auditoria_conc75.py — Septuagesimacinquinta ronda de auditoría.

Correcciones:

  A) id=3611 (Vaxigrip Tetra u otro cuadrivalente reciente con cepas anuales):
     La DB agrupa vacunas equivalentes por subtipo, no por cepa anual específica.
     Los nombres de cepa (A/Missouri/11/2025, A/Singapore/GP20238/2024, etc.) son
     designaciones anuales OMS — no forman parte del INN/DCI del producto.
     Convención establecida en ronda 66 (id=3610): componentes canónicos por subtipo.
     - HEMAGLUTININA DE LA CEPA DE TIPO A/MISSOURI/11/2025 (H1N1)PDM09 -> INFLUENZA A H1N1
     - HEMAGLUTININA DE LA CEPA DE TIPO A/SINGAPORE/GP20238/2024 (H3N2) -> INFLUENZA A H3N2
     - HEMAGLUTININA DE LA CEPA DE TIPO B/AUSTRIA/1359417/2021 -> INFLUENZA B LINAJE VICTORIA
       (B/Austria/1359417/2021 es cepa linaje Victoria)
     - HEMAGLUTININA DE LA CEPA DE TIPO B/PHUKET/3073/2013 -> INFLUENZA B LINAJE YAMAGATA
       (B/Phuket/3073/2013 es cepa linaje Yamagata)
     -> auto-merge con id=3610 (mismo dci_key INYECTABLE SIN_CONC): n=1+1=2

  B) id=2817 (vacuna antirrábica):
     VIRUS DE LA RABIA -> VIRUS DE LA RABIA (INACTIVADO)
     (convención establecida: especificar si inactivado, análogo a
      VIRUS DE LA HEPATITIS A (INACTIVADO) en id=3134; la vacuna antirrábica
      usa siempre virus inactivado, no vivo atenuado)
     -> sin merge
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"

FLU_CANONICAL = (
    "INFLUENZA A H1N1||INFLUENZA A H3N2||"
    "INFLUENZA B LINAJE VICTORIA||INFLUENZA B LINAJE YAMAGATA"
)

FLU_SYNC = {
    "HEMAGLUTININA DE LA CEPA DE TIPO A/MISSOURI/11/2025 (H1N1)PDM09": "INFLUENZA A H1N1",
    "HEMAGLUTININA DE LA CEPA DE TIPO A/SINGAPORE/GP20238/2024 (H3N2)": "INFLUENZA A H3N2",
    "HEMAGLUTININA DE LA CEPA DE TIPO B/AUSTRIA/1359417/2021": "INFLUENZA B LINAJE VICTORIA",
    "HEMAGLUTININA DE LA CEPA DE TIPO B/PHUKET/3073/2013": "INFLUENZA B LINAJE YAMAGATA",
}


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
    print(f"  [RENAME] id={gid}: '{old_dci[:80]}' -> '{new_dci[:80]}'")
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

    # -- A. id=3611: cepas anuales -> subtipos canónicos (merge con id=3610) ----------
    print("\n=== A. id=3611 influenza cepas -> subtipos canónicos ===")
    n['A'] += rename_dci(con, 3611, FLU_CANONICAL, FLU_SYNC)

    # -- B. id=2817: VIRUS DE LA RABIA -> VIRUS DE LA RABIA (INACTIVADO) --------------
    print("\n=== B. id=2817 VIRUS DE LA RABIA -> (INACTIVADO) ===")
    n['B'] += rename_dci(con, 2817, "VIRUS DE LA RABIA (INACTIVADO)",
                         {"VIRUS DE LA RABIA": "VIRUS DE LA RABIA (INACTIVADO)"})

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
