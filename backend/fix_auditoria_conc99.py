"""
fix_auditoria_conc99.py — Nonagésimonovena ronda de auditoría.

  A) SESTAMIBI → TECNECIO (99MTC) SESTAMIBI (WHO INN-Sp):
     Los productos son kits para preparación radiofarmacéutica de Tc-99m sestamibi
     (Cardiolite/Stamicis/Draximage/Mon.Mibi). Usar nombre completo del radiofármaco.
       id=992:  SESTAMIBI | INYECTABLE | 1 mg | n=5
       id=2534: SESTAMIBI | INYECTABLE | 0.5 mg | n=1
     No auto-merge entre sí (concentraciones distintas).

  B) ACIDO PENTETICO → TECNECIO (99MTC) PENTETATO:
     Productos: Poltechdtpa, Rphnefro, Nefro-Tec — todos kits Tc-99m DTPA renales.
     ACIDO PENTETICO (ácido libre) es forma química; INN radiofármaco = TECNECIO (99MTC) PENTETATO.
     Hay id=3689 (TECNECIO 99MTC PENTETATO INHALADO SIN_CONC) — no hace auto-merge
     con estos dos INYECTABLE.
       id=1868: ACIDO PENTETICO | INYECTABLE | 10 mg | n=2
       id=2571: ACIDO PENTETICO | INYECTABLE | 5 mg | n=1

  C) ACIDO DIMERCAPTOSUCCINICO → TECNECIO (99MTC) SUCCIMERO (WHO INN #8994):
     Succimer = DMSA (ácido dimercaptosuccínico). Kits: Renocis, Rphreno, Kidney-Tec.
     ACIDO DIMERCAPTOSUCCINICO es nombre químico; INN = TECNECIO (99MTC) SUCCIMERO.
       id=3335: SIN_CONCENTRACION | n=2 → keep
       id=2574: 1 mg | n=1 → fix conc a SIN_CONCENTRACION → auto-merge con 3335
     → auto-merge: total n=3.

  D) SACUBITRILO → SACUBITRIL (WHO INN #10125):
     El INN OMS en inglés y español es "sacubitril" (sin -O final). SACUBITRILO es
     una hispanización no canónica. Tres grupos (Entresto 50/100/200mg):
       id=2449: SACUBITRILO||VALSARTAN | SOLIDO_ORAL | 24 mg + 26 mg | n=10
       id=2450: SACUBITRILO||VALSARTAN | SOLIDO_ORAL | 49 mg + 51 mg | n=12
       id=2452: SACUBITRILO||VALSARTAN | SOLIDO_ORAL | 97 mg + 103 mg | n=10
     No auto-merge entre sí (concentraciones distintas). Sort: SACUBITRIL||VALSARTAN.
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


def rename_component(con, gid: int, old_component: str, new_component: str) -> int:
    cur = con.cursor()
    cur.execute("SELECT dci_key, cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_dci = row[0]
    parts = old_dci.split("||")
    if old_component not in parts:
        print(f"  [SKIP] id={gid}: '{old_component}' not in '{old_dci[:50]}'")
        return 0
    new_parts = [new_component if p == old_component else p for p in parts]
    new_dci = "||".join(sorted(new_parts))
    if new_dci == old_dci:
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
            new_pdci = [new_component if d == old_component else d for d in pdci]
            new_pdci = list(dict.fromkeys(new_pdci))
            if new_pdci != pdci:
                cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                            (json.dumps(new_pdci), exp, consec))
                updated += 1
    if updated:
        print(f"    cum_normalizado: {updated} productos actualizados")
    return 1


def fix_concentration(con, gid: int, new_conc: str) -> int:
    cur = con.cursor()
    cur.execute("SELECT dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    old_conc = row[1]
    if old_conc == new_conc:
        print(f"  [OK ya] id={gid}: conc already {new_conc}")
        return 0
    if new_conc == "SIN_CONCENTRACION":
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=?, concentracion_valor=NULL, concentracion_unidad=NULL WHERE id=?",
                    (new_conc, gid))
    else:
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [FIX_CONC] id={gid} ({row[0][:40]}): '{old_conc}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # A. SESTAMIBI → TECNECIO (99MTC) SESTAMIBI
    print("\n=== A. SESTAMIBI → TECNECIO (99MTC) SESTAMIBI ===")
    for gid in [992, 2534]:
        n['A'] += rename_component(con, gid, "SESTAMIBI", "TECNECIO (99MTC) SESTAMIBI")

    # B. ACIDO PENTETICO → TECNECIO (99MTC) PENTETATO
    print("\n=== B. ACIDO PENTETICO → TECNECIO (99MTC) PENTETATO ===")
    for gid in [1868, 2571]:
        n['B'] += rename_component(con, gid, "ACIDO PENTETICO", "TECNECIO (99MTC) PENTETATO")

    # C. ACIDO DIMERCAPTOSUCCINICO → TECNECIO (99MTC) SUCCIMERO
    print("\n=== C. ACIDO DIMERCAPTOSUCCINICO → TECNECIO (99MTC) SUCCIMERO ===")
    # Fix id=2574 concentration first (1mg → SIN_CONCENTRACION) so it can merge with 3335
    n['C'] += fix_concentration(con, 2574, "SIN_CONCENTRACION")
    for gid in [3335, 2574]:
        n['C'] += rename_component(con, gid, "ACIDO DIMERCAPTOSUCCINICO", "TECNECIO (99MTC) SUCCIMERO")

    # D. SACUBITRILO → SACUBITRIL
    print("\n=== D. SACUBITRILO → SACUBITRIL ===")
    for gid in [2449, 2450, 2452]:
        n['D'] += rename_component(con, gid, "SACUBITRILO", "SACUBITRIL")

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
