"""
fix_auditoria_conc82.py — Octogesimosegunda ronda de auditoría.

Correcciones — Normalización INN de penicilinas:

  El INN OMS para las penicilinas del tipo "Penicilina G":
    - BENCILPENICILINA (benzylpenicillin) = sal sódica/potásica IV, corta duración
    - BENCILPENICILINA BENZATINA = sal benzatínica IM, larga duración
    - BENCILPENICILINA PROCAINA = sal procaínica IM, duración media

  El INN OMS para "Penicilina V":
    - FENOXIMETILPENICILINA (phenoxymethylpenicillin) = vía oral, ácido resistente

  Estado actual de la DB: 3 nombres distintos (PENICILINA G, BENCILPENICILINA,
  PENICILINA G BENZATINICA/PROCAINA), mezclando formas salinas dentro de cada grupo.

  Acciones:
  A) id=2953 (PENICILINA G 1000K UI, productos sódicos) → BENCILPENICILINA
  B) id=2954 (PENICILINA G 5000K UI, productos sódicos) → BENCILPENICILINA
  C) id=2951 (PENICILINA G 400K UI, productos procaínicos) → BENCILPENICILINA PROCAINA
  D) id=2952 (PENICILINA G 1200K UI, productos benzatínicos) → BENCILPENICILINA BENZATINA
  E) id=2956 (PENICILINA G 2400K UI, productos benzatínicos) → BENCILPENICILINA BENZATINA
  F) id=2971 (BENCILPENICILINA 2400K UI, productos benzatínicos) → BENCILPENICILINA BENZATINA
  G) id=2972 (BENCILPENICILINA 800K UI, productos procaínicos) → BENCILPENICILINA PROCAINA
  H) id=3485 (BENCILPENICILINA 1200K UI, productos benzatínicos) → BENCILPENICILINA BENZATINA
  I) id=3087 (PENICILINA G BENZATINICA 2400K UI) → BENCILPENICILINA BENZATINA
  J) id=3088 (PENICILINA G BENZATINICA 1200K UI) → BENCILPENICILINA BENZATINA
  K) id=2973 (PENICILINA G PROCAINA 800K UI) → BENCILPENICILINA PROCAINA
  L) id=3873 (PENICILINA V 500mg, sólido oral) → FENOXIMETILPENICILINA
  M) id=3389 (PENICILINA V 50mg/mL, líquido oral) → FENOXIMETILPENICILINA

  Post-merge esperados:
  - BENCILPENICILINA 5000K: id=2970 + id=2954(rename)
  - BENCILPENICILINA BENZATINA 2400K: id=2971(rename) + id=2956(rename) + id=3087(rename)
  - BENCILPENICILINA BENZATINA 1200K: id=2952(rename) + id=3485(rename) + id=3088(rename)
  - BENCILPENICILINA PROCAINA 800K: id=2972(rename) + id=2973(rename)
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"

FIXES = [
    # (gid, new_dci, sync_map)
    # A & B: sodium penicillin G → BENCILPENICILINA
    (2953, "BENCILPENICILINA", {"PENICILINA G": "BENCILPENICILINA"}),
    (2954, "BENCILPENICILINA", {"PENICILINA G": "BENCILPENICILINA"}),
    # C: procaine → BENCILPENICILINA PROCAINA
    (2951, "BENCILPENICILINA PROCAINA", {"PENICILINA G": "BENCILPENICILINA PROCAINA"}),
    # D & E: benzathine → BENCILPENICILINA BENZATINA
    (2952, "BENCILPENICILINA BENZATINA", {"PENICILINA G": "BENCILPENICILINA BENZATINA"}),
    (2956, "BENCILPENICILINA BENZATINA", {"PENICILINA G": "BENCILPENICILINA BENZATINA"}),
    # F: BENCILPENICILINA with benzathine products
    (2971, "BENCILPENICILINA BENZATINA", {"BENCILPENICILINA": "BENCILPENICILINA BENZATINA"}),
    # G: BENCILPENICILINA with procaine products
    (2972, "BENCILPENICILINA PROCAINA", {"BENCILPENICILINA": "BENCILPENICILINA PROCAINA"}),
    # H: BENCILPENICILINA with benzathine products
    (3485, "BENCILPENICILINA BENZATINA", {"BENCILPENICILINA": "BENCILPENICILINA BENZATINA"}),
    # I & J: PENICILINA G BENZATINICA → BENCILPENICILINA BENZATINA
    (3087, "BENCILPENICILINA BENZATINA",
     {"PENICILINA G BENZATINICA": "BENCILPENICILINA BENZATINA"}),
    (3088, "BENCILPENICILINA BENZATINA",
     {"PENICILINA G BENZATINICA": "BENCILPENICILINA BENZATINA"}),
    # K: PENICILINA G PROCAINA → BENCILPENICILINA PROCAINA
    (2973, "BENCILPENICILINA PROCAINA",
     {"PENICILINA G PROCAINA": "BENCILPENICILINA PROCAINA"}),
    # L & M: PENICILINA V → FENOXIMETILPENICILINA
    (3873, "FENOXIMETILPENICILINA", {"PENICILINA V": "FENOXIMETILPENICILINA"}),
    (3389, "FENOXIMETILPENICILINA", {"PENICILINA V": "FENOXIMETILPENICILINA"}),
]


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
    print(f"  [RENAME] id={gid}: '{old_dci}' -> '{new_dci}'")
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
    n_rename = 0
    n_merge = 0

    print("\n=== Renombrando grupos penicilina ===")
    for gid, new_dci, sync_map in FIXES:
        n_rename += rename_dci(con, gid, new_dci, sync_map)

    print("\n=== Post-fix auto-merge ===")
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
            n_merge += merge_into(con, keep_id, del_id)

    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    print(f"\n=== RESUMEN ===")
    print(f"  renombrados: {n_rename}")
    print(f"  merges: {n_merge}")

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
