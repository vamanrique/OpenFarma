"""
fix_auditoria_conc100.py — Centésima ronda de auditoría.

  A) HIDROXICOBALAMINA → HIDROXOCOBALAMINA (WHO INN-Sp):
     La forma correcta del INN español para hydroxocobalamin es "hidroxocobalamina"
     (del ligando "hidroxo" en química de coordinación, no "hidroxi" de IUPAC).
     Solo un grupo (Bedoyecta Tri: B1+B6+B12 inyectable):
       id=493: HIDROXICOBALAMINA||PIRIDOXINA||TIAMINA | INYECTABLE | 10+50+100 mg

  B) FOLINATO DE CALCIO → ACIDO FOLINICO (normalización sal→ácido INN):
     FOLINATO DE CALCIO = leucovorin calcium. INN OMS: "folinic acid" = ACIDO FOLINICO.
     Por convención DB: los nombres de sal → INN base (ácido libre).
     Coherente con ACIDO FOLICO, no con la sal calcio.
       id=2265: FOLINATO DE CALCIO | INYECTABLE | 10 mg/mL | n=1

  C) OXIDRONATO DE SODIO → TECNECIO (99MTC) OXIDRONATO:
     Osteocis y Osteo-Tec son kits para preparación de Tc-99m oxidronato (HDP bone
     scan). Nombre de la sal (oxidronato de sodio, el ligando) → INN del radiofármaco
     completo (TECNECIO 99MTC OXIDRONATO). Convención ya establecida con SESTAMIBI,
     PENTETATO, SUCCIMERO.
       id=1259: OXIDRONATO DE SODIO | INYECTABLE | 3 mg | n=1
       id=2572: OXIDRONATO DE SODIO | INYECTABLE | 2 mg | n=1
     No auto-merge: concentraciones distintas.

  D) GADOBENATO DE DIMEGLUMINA → ACIDO GADOBENICO (WHO INN #9232):
     MultiHance = gadobenate dimeglumine = sal dimeglumina del ácido gadobénico.
     Los otros agentes de Gd iónicos en la DB usan la forma ácida libre:
     ACIDO GADOTERICO (Dotarem) y ACIDO GADOXETICO (Primovist).
     Los no-iónicos (GADODIAMIDA, GADOBUTROL, GADOTERIDOL) no tienen forma ácida INN.
       id=1445: GADOBENATO DE DIMEGLUMINA | INYECTABLE | 529 mg/mL | n=3

  E) MACROAGREGADOS DE ALBUMINA HUMANA → TECNECIO (99MTC) MACROSALB (WHO INN #9127):
     Pulmocis = kit para preparación Tc-99m MAA (lung perfusion scan).
     INN OMS: "macrosalb" (#9127, 1979) → radiofármaco = TECNECIO (99MTC) MACROSALB.
       id=3336: MACROAGREGADOS DE ALBUMINA HUMANA | INYECTABLE | SIN_CONCENTRACION | n=1
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


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # A. HIDROXICOBALAMINA → HIDROXOCOBALAMINA
    print("\n=== A. HIDROXICOBALAMINA → HIDROXOCOBALAMINA ===")
    n['A'] += rename_component(con, 493, "HIDROXICOBALAMINA", "HIDROXOCOBALAMINA")

    # B. FOLINATO DE CALCIO → ACIDO FOLINICO
    print("\n=== B. FOLINATO DE CALCIO → ACIDO FOLINICO ===")
    n['B'] += rename_component(con, 2265, "FOLINATO DE CALCIO", "ACIDO FOLINICO")

    # C. OXIDRONATO DE SODIO → TECNECIO (99MTC) OXIDRONATO
    print("\n=== C. OXIDRONATO DE SODIO → TECNECIO (99MTC) OXIDRONATO ===")
    for gid in [1259, 2572]:
        n['C'] += rename_component(con, gid, "OXIDRONATO DE SODIO", "TECNECIO (99MTC) OXIDRONATO")

    # D. GADOBENATO DE DIMEGLUMINA → ACIDO GADOBENICO
    print("\n=== D. GADOBENATO DE DIMEGLUMINA → ACIDO GADOBENICO ===")
    n['D'] += rename_component(con, 1445, "GADOBENATO DE DIMEGLUMINA", "ACIDO GADOBENICO")

    # E. MACROAGREGADOS DE ALBUMINA HUMANA → TECNECIO (99MTC) MACROSALB
    print("\n=== E. MACROAGREGADOS DE ALBUMINA HUMANA → TECNECIO (99MTC) MACROSALB ===")
    n['E'] += rename_component(con, 3336, "MACROAGREGADOS DE ALBUMINA HUMANA", "TECNECIO (99MTC) MACROSALB")

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
