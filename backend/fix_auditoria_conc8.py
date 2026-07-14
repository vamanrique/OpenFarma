"""
fix_auditoria_conc8.py — Octava ronda de auditoría.

Correcciones:
  A) INHALADO multi-componente: formato "X + Y mcg/dosis" -> "X mcg/dosis + Y mcg/dosis"
     (17 grupos: FLUTICASONA||SALMETEROL, BUDESONIDA||FORMOTEROL, etc.)
  B) CALCITRIOL id=777: "0.00025 mg" -> "0.25 mcg" (convención estándar)
  C) VITAMINA E id=834: dci_key "VITAMINA E" -> "TOCOFEROL", conc "400 mg" -> "400 UI"
     -> merge id=2874 (TOCOFEROL 400 UI, n=178)
  D) id=860 complejo multivitamínico: concentración en mg incorrecta -> SIN_CONCENTRACION
  E) Post-fix auto-merge duplicados
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


def expand_unit_suffix(conc: str) -> str:
    """Convert 'X + Y unit' -> 'X unit + Y unit' (unit applied to all components)."""
    # Match: parts separated by " + " where last part has a unit
    parts = conc.split(' + ')
    if len(parts) < 2:
        return conc
    last = parts[-1]
    # Extract unit from last part (e.g., "50 mcg/dosis" -> unit="mcg/dosis", val="50")
    m = re.match(r'^([\d.]+)\s+(mcg/dosis|mg/dosis|mcg|mg/mL)$', last)
    if not m:
        return conc
    unit = m.group(2)
    # Rebuild: each part that is just a number gets the unit appended
    new_parts = []
    for i, p in enumerate(parts):
        p_clean = p.strip()
        if i == len(parts) - 1:
            # Last part already has unit
            new_parts.append(p_clean)
        else:
            # Check if it's just a number (possibly with existing unit)
            # Remove any trailing "mcg" to normalize
            p_no_unit = re.sub(r'\s*(mcg|mg)$', '', p_clean)
            new_parts.append(f"{p_no_unit} {unit}")
    return ' + '.join(new_parts)


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'merge']}

    # -- A. INHALADO multi-componente: distribuir unidad mcg/dosis ---------------
    print("\n=== A. INHALADO formato mcg/dosis ===")
    # Groups with "X + Y mcg/dosis" but NOT "X mcg/dosis + Y ..."
    cur.execute("""
        SELECT id, concentracion_norm FROM grupos_equivalencia
        WHERE concentracion_norm LIKE '% + % mcg/dosis'
          AND concentracion_norm NOT LIKE '% mcg/dosis + %'
    """)
    rows = cur.fetchall()
    updated = 0
    for gid, conc in rows:
        new_conc = expand_unit_suffix(conc)
        if new_conc != conc:
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?",
                        (new_conc, gid))
            print(f"  id={gid}: '{conc}' -> '{new_conc}'")
            updated += 1
    # Also fix "X mcg + Y mcg + Z mcg/dosis" patterns (mixed, id=13)
    cur.execute("""
        SELECT id, concentracion_norm FROM grupos_equivalencia
        WHERE concentracion_norm LIKE '% mcg + % mcg/dosis'
    """)
    for gid, conc in cur.fetchall():
        new_conc = expand_unit_suffix(conc)
        if new_conc != conc:
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?",
                        (new_conc, gid))
            print(f"  id={gid}: '{conc}' -> '{new_conc}'")
            updated += 1
    print(f"  {updated} grupos actualizados")
    n['A'] = updated

    # -- B. CALCITRIOL id=777: mg -> mcg -----------------------------------------
    print("\n=== B. CALCITRIOL ===")
    n['B'] += fix_conc(cur, 777, "0.25 mcg", "B_calcitriol_mcg")

    # -- C. VITAMINA E id=834: dci + conc fix -> merge id=2874 -------------------
    print("\n=== C. VITAMINA E -> TOCOFEROL ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=834")
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE grupos_equivalencia
            SET dci_key='TOCOFEROL', concentracion_norm='400 UI'
            WHERE id=834
        """)
        print(f"  [C] id=834: dci '{row[1]}' -> 'TOCOFEROL', conc '{row[2]}' -> '400 UI'")
        n['C'] += 1
        # Also update cum_normalizado for the 2 products
        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=834")
        ids = json.loads(cur.fetchone()[0] or '[]')
        for cid in ids:
            exp, consec = cid.split('-')
            cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?",
                        (exp, consec))
            r = cur.fetchone()
            if r:
                pdci = json.loads(r[0] or '[]')
                new_pdci = ["TOCOFEROL" if p == "VITAMINA E" else p for p in pdci]
                if new_pdci != pdci:
                    cur.execute(
                        "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                        (json.dumps(new_pdci), exp, consec)
                    )
        n['merge'] += merge_into(con, 2874, 834)

    # -- D. id=860 multivitamínico con unidades incorrectas -> SIN_CONCENTRACION -
    print("\n=== D. id=860 complejo multivitaminico -> SIN_CONCENTRACION ===")
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=860")
    row = cur.fetchone()
    if row and row[0] != 'SIN_CONCENTRACION':
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='SIN_CONCENTRACION' WHERE id=860")
        print(f"  [D] id=860: '{row[0][:60]}...' -> 'SIN_CONCENTRACION'")
        n['D'] += 1

    # -- E. Post-fix auto-merge duplicados ----------------------------------------
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

    # -- Fix n_productos ----------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen ------------------------------------------------------------------
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
