"""
fix_auditoria_conc3.py — Tercera ronda de auditoría.

Correcciones:
  A) DCI key: variantes tipográficas (CONDROITIN→CONDROITINA, espacio en MSM)
  B) concentracion_unidad: estandarizar valores inconsistentes
  C) concentracion_valor: poblar NULL para grupos monocomponente con norma parseable
  D) Fusionar duplicados post-DCI
"""
import sqlite3, sys, re, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"

# ── A. DCI key replacements ──────────────────────────────────────────────────
# Formato: (substring_a_buscar, reemplazar_por)
DCI_SUBS = [
    ("CONDROITIN SULFATO", "CONDROITINA SULFATO"),   # CONDROITIN → CONDROITINA
    ("METILSULFONIL METANO", "METILSULFONILMETANO"),  # espacio → sin espacio
]

# ── B. concentracion_unidad → estándar ───────────────────────────────────────
UNIT_MAP = {
    "ui": "UI",
    "MG/ML": "mg/mL",
    "meq": "mEq",
    "mg/g": "%",         # ya convertimos mg/g → % en la norma
    "mg/5mL": "mg/mL",
    "mg/5ml": "mg/mL",
    "mg/5 mL": "mg/mL",
    "g/100mL": "mg/mL",
    "g/100 mL": "mg/mL",
    "g/100g": "%",
    "g": "mg",           # en SOLIDO_ORAL, g → mg (ya debería ser mg en la norma)
}

# ── C. Parser de concentracion_norm → (valor, unidad) ────────────────────────
NORM_PATTERNS = [
    # X mg
    (r'^([\d.]+)\s*mg$', lambda m: (float(m.group(1)), "mg")),
    # X mg/mL
    (r'^([\d.]+)\s*mg/mL$', lambda m: (float(m.group(1)), "mg/mL")),
    # X%
    (r'^([\d.]+)\s*%$', lambda m: (float(m.group(1)), "%")),
    # X UI/mL
    (r'^([\d.]+)\s*UI/mL$', lambda m: (float(m.group(1)), "UI/mL"), re.I),
    # X UI/g
    (r'^([\d.]+)\s*UI/g$', lambda m: (float(m.group(1)), "UI/g"), re.I),
    # X UI
    (r'^([\d.]+)\s*UI$', lambda m: (float(m.group(1)), "UI"), re.I),
    # X mcg/dosis
    (r'^([\d.]+)\s*mcg/dosis$', lambda m: (float(m.group(1)), "mcg/dosis"), re.I),
    # X mg/dosis
    (r'^([\d.]+)\s*mg/dosis$', lambda m: (float(m.group(1)), "mg/dosis"), re.I),
]

def parse_norm(conc: str):
    """Returns (valor, unidad) or (None, None)."""
    if not conc or '+' in conc or conc == 'SIN_CONCENTRACION':
        return None, None
    for item in NORM_PATTERNS:
        pat, fn = item[0], item[1]
        flags = item[2] if len(item) > 2 else 0
        m = re.match(pat, conc.strip(), flags)
        if m:
            try:
                return fn(m)
            except Exception:
                pass
    return None, None


def rebuild_dci_key(old_key: str, subs: list) -> str:
    new_key = old_key
    for old, new in subs:
        new_key = new_key.replace(old, new)
    if new_key == old_key:
        return old_key
    # Re-sort components
    parts = [p.strip() for p in new_key.split('||')]
    return '||'.join(sorted(parts))


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        return 0
    merged = list(dict.fromkeys(
        json.loads(keep[0] or '[]') + json.loads(rem[0] or '[]')
    ))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}→{keep_id}: total={len(merged)}")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A_grupos','A_cum','B','C','merge']}

    # ── A. DCI key fix en grupos_equivalencia ────────────────────────────────
    print("\n=== A. DCI key en grupos_equivalencia ===")
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia")
    rows = cur.fetchall()
    for gid, old_key in rows:
        new_key = rebuild_dci_key(old_key, DCI_SUBS)
        if new_key != old_key:
            cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=?", (new_key, gid))
            print(f"  id={gid}: '{old_key}' → '{new_key}'")
            n['A_grupos'] += 1

    # ── A2. DCI fix en cum_normalizado principios_dci ─────────────────────────
    print("\n=== A2. DCI key en cum_normalizado ===")
    cur.execute("SELECT expediente_cum, consecutivo_cum, principios_dci FROM cum_normalizado WHERE principios_dci IS NOT NULL")
    updated_cum = 0
    for exp, consec, pdci_json in cur.fetchall():
        cid = (exp, consec)  # composite PK
        pdci = json.loads(pdci_json) if pdci_json else []
        new_pdci = []
        changed = False
        for p in pdci:
            new_p = p
            for old, new in DCI_SUBS:
                new_p = new_p.replace(old, new)
            new_pdci.append(new_p)
            if new_p != p:
                changed = True
        if changed:
            exp, consec = cid
            cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                       (json.dumps(new_pdci), exp, consec))
            updated_cum += 1
    print(f"  {updated_cum} registros cum_normalizado actualizados")
    n['A_cum'] = updated_cum

    # ── B. concentracion_unidad standardización ───────────────────────────────
    print("\n=== B. concentracion_unidad ===")
    for old_unit, new_unit in UNIT_MAP.items():
        cur.execute(
            "UPDATE grupos_equivalencia SET concentracion_unidad=? WHERE concentracion_unidad=?",
            (new_unit, old_unit)
        )
        if cur.rowcount:
            print(f"  '{old_unit}' → '{new_unit}': {cur.rowcount} grupos")
            n['B'] += cur.rowcount
    # UI/g mantenerlo (UI/g es estándar para heparina/nistatina)

    # ── C. concentracion_valor para grupos con NULL ───────────────────────────
    print("\n=== C. concentracion_valor NULL → parsear ===")
    cur.execute("""
        SELECT id, concentracion_norm FROM grupos_equivalencia
        WHERE concentracion_valor IS NULL
          AND concentracion_norm IS NOT NULL
          AND concentracion_norm != 'SIN_CONCENTRACION'
          AND concentracion_norm NOT LIKE '% + %'
    """)
    rows = cur.fetchall()
    for gid, conc in rows:
        val, unit = parse_norm(conc)
        if val is not None:
            cur.execute(
                "UPDATE grupos_equivalencia SET concentracion_valor=?, concentracion_unidad=? WHERE id=?",
                (val, unit, gid)
            )
            n['C'] += 1
    print(f"  {n['C']} grupos actualizados")

    # ── D. Fusionar duplicados post-DCI ──────────────────────────────────────
    print("\n=== D. Fusionar duplicados post-DCI ===")
    cur.execute("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as cnt,
               GROUP_CONCAT(id ORDER BY id)
        FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING cnt > 1
    """)
    for dci, via, conc, cnt, ids_str in cur.fetchall():
        ids = list(map(int, ids_str.split(',')))
        keep = ids[0]
        for del_id in ids[1:]:
            n['merge'] += merge_into(con, keep, del_id)

    # ── Fix n_productos ───────────────────────────────────────────────────────
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # ── Resumen ───────────────────────────────────────────────────────────────
    print("\n=== RESUMEN ===")
    for k, v in n.items():
        if v:
            print(f"  {k}: {v}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_norm='SIN_CONCENTRACION'")
    sin = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_valor IS NULL AND concentracion_norm != 'SIN_CONCENTRACION' AND concentracion_norm NOT LIKE '% + %'")
    null_val = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia GROUP BY dci_key,grupo_via,concentracion_norm HAVING COUNT(*)>1")
    dups = len(cur.fetchall())

    print(f"\nDB: {total} grupos | {sin} SIN_CONCENTRACION | concentracion_valor NULL mono: {null_val} | {dups} duplicados")
    con.close()


if __name__ == "__main__":
    main()
