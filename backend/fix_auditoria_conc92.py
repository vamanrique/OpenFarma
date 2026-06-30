"""
fix_auditoria_conc92.py — Nonagésimosegunda ronda de auditoría.

Correcciones de formulaciones especiales y preparaciones de hierro:

  A) id=1580 (AmBisome, Amphosom-B, Limperic B):
     'ANFOTERICINA B' → 'ANFOTERICINA B LIPOSOMAL'
     INN OMS: amphotericin B, liposomal = anfotericina B liposomal.
     Los 11 productos del grupo son formulaciones liposomales (NO la convencional
     Fungizone). ANFOTERICINA B liposomal ≠ ANFOTERICINA B convencional:
     distintas toxicidades, posologías e indicaciones. Sin merge: único grupo.

  B) id=1532 (Ferinject):
     'HIERRO' → 'CARBOXIMALTOSA FERRICA'
     INN OMS: ferric carboxymaltose = carboximaltosa férrica. ATC B03AC.
     Ferinject (Vifor Pharma) = único grupo INYECTABLE 50 mg/mL. Sin merge.

  C) id=1964 (Hierro Sacarosa 20 mg/mL, genéricos):
     'HIERRO' → 'HIERRO SACAROSA'
     Productos: "Complejo De Hidroxido De Hierro En Sacarosa". Mismo INN que
     id=1500 (HIERRO SACAROSA, 20 mg/mL, 26 productos). → auto-merge.

  D) id=2522 (Monofer):
     'HIERRO' → 'DERISOMALTOSA FERRICA'
     INN OMS (2020): ferric derisomaltose = derisomaltosa ferrica.
     Monofer (Pharmacosmos) = iron isomaltoside 1000 / ferric derisomaltose.
     Sin merge: único grupo INYECTABLE 10 mg/mL.

  E) id=3402 (Ferroprotina):
     'HIERRO FERRICO' → 'PROTEINSUCCINILATO FERRICO'
     INN OMS: ferric proteinsuccinylate = proteinsuccinilato ferrico.
     Ferroprotina = hierro proteinsuccinilato, ATC B03AB99 (oral, SIN_CONC).
     Sin merge: único grupo.
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
            mapped = [sync_map.get(d, d) for d in pdci]
            new_pdci = list(dict.fromkeys(mapped))
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
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # A. id=1580: ANFOTERICINA B → ANFOTERICINA B LIPOSOMAL
    print("\n=== A. id=1580 AmBisome: ANFOTERICINA B -> ANFOTERICINA B LIPOSOMAL ===")
    n['A'] += rename_dci(con, 1580, "ANFOTERICINA B LIPOSOMAL", {
        "ANFOTERICINA B": "ANFOTERICINA B LIPOSOMAL",
    })

    # B. id=1532: HIERRO → CARBOXIMALTOSA FERRICA (Ferinject)
    print("\n=== B. id=1532 Ferinject: HIERRO -> CARBOXIMALTOSA FERRICA ===")
    n['B'] += rename_dci(con, 1532, "CARBOXIMALTOSA FERRICA", {
        "HIERRO": "CARBOXIMALTOSA FERRICA",
    })

    # C. id=1964: HIERRO → HIERRO SACAROSA
    print("\n=== C. id=1964 Hierro Sacarosa 20mg/mL: HIERRO -> HIERRO SACAROSA ===")
    n['C'] += rename_dci(con, 1964, "HIERRO SACAROSA", {
        "HIERRO": "HIERRO SACAROSA",
    })

    # D. id=2522: HIERRO → DERISOMALTOSA FERRICA (Monofer)
    print("\n=== D. id=2522 Monofer: HIERRO -> DERISOMALTOSA FERRICA ===")
    n['D'] += rename_dci(con, 2522, "DERISOMALTOSA FERRICA", {
        "HIERRO": "DERISOMALTOSA FERRICA",
    })

    # E. id=3402: HIERRO FERRICO → PROTEINSUCCINILATO FERRICO (Ferroprotina)
    print("\n=== E. id=3402 Ferroprotina: HIERRO FERRICO -> PROTEINSUCCINILATO FERRICO ===")
    n['E'] += rename_dci(con, 3402, "PROTEINSUCCINILATO FERRICO", {
        "HIERRO FERRICO": "PROTEINSUCCINILATO FERRICO",
    })

    # Post-fix auto-merge
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
