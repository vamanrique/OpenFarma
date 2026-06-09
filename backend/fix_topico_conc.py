"""
Fix concentracion_norm for TOPICO groups:
  Phase 1: Mathematical conversions (g/100g -> %, mg/g -> %, comma multi -> plus format)
  Phase 2: DeepSeek for ambiguous cases
  Phase 3: Fix DCI errors (OVALE CHAMPU -> KETOCONAZOL etc)
  Phase 4: Merge duplicate groups after normalization
"""
import re
import json
import sqlite3
import requests

DB_PATH = "farmavigia.db"

def _load_deepseek_key():
    with open(".env") as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("DEEPSEEK_API_KEY not found in .env")

DEEPSEEK_API_KEY = _load_deepseek_key()
DS_URL = "https://api.deepseek.com/v1/chat/completions"
DS_HEADERS = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}


def ds_query(prompt: str) -> str:
    resp = requests.post(DS_URL, headers=DS_HEADERS, json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 600,
    })
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# Mathematical conversions

def g_per_100g_to_pct(x: str) -> str:
    v = float(x.replace(',', '.'))
    return f"{v:g}%"


def mg_per_g_to_pct(x: str) -> str:
    v = float(x.replace(',', '.'))
    pct = v / 10.0
    return f"{pct:g}%"


def convert_part(p: str):
    p = p.strip()
    # X g/100g
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*g\s*/\s*100\s*g$', p, re.IGNORECASE)
    if m:
        return g_per_100g_to_pct(m.group(1))
    # X mg/g
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*mg\s*/\s*g$', p, re.IGNORECASE)
    if m:
        return mg_per_g_to_pct(m.group(1))
    # Already pct
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*%$', p, re.IGNORECASE)
    if m:
        return f"{float(m.group(1)):g}%"
    # UI/g — acceptable unit for biologics
    m = re.match(r'^(\d+)\s*UI/g$', p, re.IGNORECASE)
    if m:
        return p
    return None


def math_convert(conc: str):
    c = conc.strip()
    if not c:
        return None

    # Trivial whitespace: '5 %' -> '5%'
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s+%$', c)
    if m:
        v = float(m.group(1))
        return f"{v:g}%"

    # Single unit conversions
    r = convert_part(c)
    if r:
        return r

    # Multi-component: split by comma or +
    sep = re.compile(r'\s*(?:[,+])\s*')
    parts_raw = sep.split(c)
    if len(parts_raw) >= 2:
        converted = [convert_part(p) for p in parts_raw]
        if all(v is not None for v in converted):
            return ' + '.join(converted)

    return None


def phase1(cur):
    print("=== Phase 1: Mathematical conversions ===")
    cur.execute(
        "SELECT id, concentracion_norm FROM grupos_equivalencia "
        "WHERE grupo_via='TOPICO' AND concentracion_norm IS NOT NULL "
        "AND concentracion_norm NOT IN ('SIN_CONCENTRACION')"
    )
    rows = cur.fetchall()
    fixed = 0
    for gid, conc in rows:
        new = math_convert(conc)
        if new and new != conc:
            print(f"  [{gid}] {conc!r} -> {new!r}")
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new, gid))
            fixed += 1
    print(f"  Fixed: {fixed}")
    return fixed


def is_normalized(conc: str) -> bool:
    if not conc or conc == 'SIN_CONCENTRACION':
        return True
    parts = [p.strip() for p in re.split(r'\s*\+\s*', conc)]
    return all(
        re.match(r'^\d[\d.,]*\s*%$', p) or
        re.match(r'^\d+\s*UI/g$', p, re.IGNORECASE) or
        re.match(r'^\d[\d.,]*\s*mg/mL$', p, re.IGNORECASE)
        for p in parts
    )


def phase2_deepseek(cur):
    print("\n=== Phase 2: DeepSeek for ambiguous concentrations ===")
    cur.execute(
        "SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia "
        "WHERE grupo_via='TOPICO' AND concentracion_norm IS NOT NULL "
        "AND concentracion_norm NOT IN ('SIN_CONCENTRACION')"
    )
    rows = cur.fetchall()
    problem_rows = [(gid, dci, conc) for gid, dci, conc in rows if not is_normalized(conc or '')]
    if not problem_rows:
        print("  Nothing to fix.")
        return 0

    print(f"  {len(problem_rows)} groups need DeepSeek:")
    for gid, dci, conc in problem_rows:
        print(f"    [{gid}] {dci!r} conc={conc!r}")

    prompt_lines = [
        "Eres farmacólogo. Para cada grupo tópico colombiano con concentracion_norm incorrecta,",
        "proporciona el valor correcto en formato % o UI/g.",
        "Reglas:",
        "  - Una sola conc: '5%'",
        "  - Multi: '0.1% + 0.1%' (mismo orden y numero de partes que el DCI key)",
        "  - UI/g solo para enzimas/bacterias con unidades internacionales",
        "  - Si no determinable: 'SIN_CONCENTRACION'",
        "",
        "Concentraciones de referencia conocidas:",
        "  - BETAMETASONA+GENTAMICINA topico crema: tipicamente betametasona 0.1% + gentamicina 0.1%",
        "  - ADAPALENO gel topico: 0.3% (3mg/g -> 0.3%)",
        "  - ACIDO HIPOCLOROSO topico antiseptico: 0.01% a 0.05%",
        "  - SULFATO DE ALUMINIO polvo topico en sobre: SIN_CONCENTRACION",
        "  - NISTATINA+OXIDO DE ZINC crema: 20000 UI/g + 20%",
        "",
        "Responde SOLO con JSON valido: {\"id_num\": \"nueva_conc\", ...}",
        "",
    ]
    for gid, dci, conc in problem_rows:
        prompt_lines.append(f"ID {gid}: DCI={dci!r}, conc_actual={conc!r}")

    resp = ds_query('\n'.join(prompt_lines))
    print(f"  DeepSeek response: {resp}")

    json_match = re.search(r'\{[\s\S]+\}', resp)
    if not json_match:
        print("  Could not parse DeepSeek response")
        return 0
    try:
        corrections = json.loads(json_match.group())
    except Exception as e:
        print(f"  JSON parse error: {e}")
        return 0

    fixed = 0
    for gid, dci, old_conc in problem_rows:
        new_conc = corrections.get(str(gid)) or corrections.get(gid)
        if new_conc and new_conc != old_conc:
            print(f"  [{gid}] {old_conc!r} -> {new_conc!r}  (DCI: {dci})")
            cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
            fixed += 1
    print(f"  Fixed: {fixed}")
    return fixed


def phase3_dci_fix(cur):
    print("\n=== Phase 3: Fix DCI errors ===")
    bad_dcis = ('OVALE CHAMPU', 'DCI')
    bad_groups = []
    for bad in bad_dcis:
        cur.execute(
            "SELECT id, dci_key, concentracion_norm, cum_ids FROM grupos_equivalencia "
            "WHERE dci_key=? AND grupo_via='TOPICO'", (bad,)
        )
        bad_groups.extend(cur.fetchall())

    if not bad_groups:
        print("  Nothing to fix.")
        return 0

    prompt = (
        "Para cada grupo topico con dci_key incorrecto (nombre comercial o placeholder):\n"
        "Proporciona dci_correcto (INN colombiano) y concentracion_norm en %.\n"
        "OVALE CHAMPU = KETOCONAZOL champu 2%.\n"
        "DCI (placeholder) con conc '20 mg/mL' champu = KETOCONAZOL 2%.\n"
        "Responde SOLO JSON: {\"ID\": {\"dci\": \"...\", \"conc\": \"...\"}, ...}\n\n"
    )
    for gid, dci, conc, cum_ids_json in bad_groups:
        sample = json.loads(cum_ids_json or '[]')[:2]
        prompt += f"ID {gid}: dci_key={dci!r} conc={conc!r} sample={sample}\n"

    resp = ds_query(prompt)
    print(f"  DeepSeek: {resp}")

    json_match = re.search(r'\{[\s\S]+\}', resp)
    if not json_match:
        return 0
    try:
        corrections = json.loads(json_match.group())
    except Exception as e:
        print(f"  JSON parse error: {e}")
        return 0

    fixed = 0
    for gid, old_dci, old_conc, _ in bad_groups:
        corr = corrections.get(str(gid)) or corrections.get(gid)
        if not corr:
            continue
        new_dci = corr.get('dci', old_dci).strip().upper()
        new_conc = corr.get('conc', old_conc)
        if new_dci != old_dci or new_conc != old_conc:
            print(f"  [{gid}] dci: {old_dci!r}->{new_dci!r}  conc: {old_conc!r}->{new_conc!r}")
            cur.execute(
                "UPDATE grupos_equivalencia SET dci_key=?, concentracion_norm=? WHERE id=?",
                (new_dci, new_conc, gid)
            )
            fixed += 1
    print(f"  Fixed: {fixed}")
    return fixed


def phase4_merge(cur):
    print("\n=== Phase 4: Merge duplicate TOPICO groups ===")
    cur.execute("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as cnt,
               GROUP_CONCAT(id) as ids
        FROM grupos_equivalencia
        WHERE grupo_via='TOPICO'
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING cnt > 1
    """)
    dupes = cur.fetchall()
    if not dupes:
        print("  No duplicates.")
        return 0

    merged = 0
    for dci, via, conc, cnt, ids_str in dupes:
        ids = [int(x) for x in ids_str.split(',')]
        keeper = min(ids)
        to_delete = [i for i in ids if i != keeper]
        print(f"  Merge {ids} -> keep {keeper} ({dci!r} {conc!r})")

        all_cum_ids = set()
        for gid in ids:
            cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (gid,))
            row = cur.fetchone()
            all_cum_ids.update(json.loads(row[0] or '[]'))

        cur.execute(
            "UPDATE grupos_equivalencia SET cum_ids=? WHERE id=?",
            (json.dumps(sorted(all_cum_ids)), keeper)
        )
        for gid in to_delete:
            cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (gid,))
        merged += 1

    print(f"  Merged: {merged}")
    return merged


def stats(cur):
    cur.execute("""
        SELECT concentracion_norm, COUNT(*) FROM grupos_equivalencia
        WHERE grupo_via='TOPICO'
        GROUP BY concentracion_norm
        ORDER BY COUNT(*) DESC
    """)
    print("\n=== TOPICO concentration distribution ===")
    non_pct = []
    for conc, cnt in cur.fetchall():
        flag = ''
        if conc and conc not in ('SIN_CONCENTRACION',):
            parts = [p.strip() for p in re.split(r'\s*\+\s*', conc)]
            bad = [p for p in parts if not (
                re.match(r'^\d[\d.,]*\s*%$', p) or
                re.match(r'^\d+\s*UI/g$', p, re.IGNORECASE) or
                re.match(r'^\d[\d.,]*\s*mg/mL$', p, re.IGNORECASE)
            )]
            if bad:
                flag = '  <NON-PCT>'
                non_pct.append(conc)
        print(f"  {cnt:3d}x  {conc!r}{flag}")
    return non_pct


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    phase1(cur)
    conn.commit()

    phase2_deepseek(cur)
    conn.commit()

    phase3_dci_fix(cur)
    conn.commit()

    phase4_merge(cur)
    conn.commit()

    remaining = stats(cur)
    if remaining:
        print(f"\n{len(remaining)} concentrations still not normalized: {remaining}")
    else:
        print("\nAll TOPICO concentrations normalized.")

    conn.close()


if __name__ == "__main__":
    main()
