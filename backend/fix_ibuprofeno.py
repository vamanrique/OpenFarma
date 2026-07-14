"""
Fix ibuprofeno grupos_equivalencia fragmentation:
  Phase 1: Merge HIOSCINA/HIOSCINA BUTILBROMURO groups → BUTILBROMURO DE HIOSCINA (canonical)
  Phase 2: Merge LIQUIDO_ORAL ibuprofeno 100mg/5mL → 20mg/mL (same concentration)
  Phase 3: Fix CETIRIZINA+FENILEFRINA+IBUPROFENO wrong concentration order (merge id=52→id=58)
  Phase 4: DeepSeek verification of injectable concentrations (4, 5, 6 mg/mL)
"""
import json
import sqlite3
import requests
import re

DB_PATH = "openfarma.db"


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
        "max_tokens": 800,
    })
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def merge_groups(cur, source_id: int, target_id: int, reason: str = ""):
    """Merges source group into target: unions cum_ids, updates n_productos, deletes source."""
    cur.execute("SELECT cum_ids, n_productos, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (source_id,))
    src = cur.fetchone()
    if not src:
        print(f"  Source id={source_id} not found, skipping")
        return 0

    cur.execute("SELECT cum_ids, n_productos, dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (target_id,))
    tgt = cur.fetchone()
    if not tgt:
        print(f"  Target id={target_id} not found, skipping")
        return 0

    src_ids = json.loads(src[0]) if isinstance(src[0], str) else (src[0] or [])
    tgt_ids = json.loads(tgt[0]) if isinstance(tgt[0], str) else (tgt[0] or [])

    merged = list(dict.fromkeys(tgt_ids + src_ids))  # union, preserve order, dedup
    label = reason or f"{src[2]} → {tgt[2]}"
    added = len(merged) - len(tgt_ids)
    print(f"  Merge id={source_id} ({src[2]!r}, {src[3]!r}, n={src[1]}) "
          f"→ id={target_id} ({tgt[2]!r}, {tgt[3]!r}, n={tgt[1]}) "
          f"+{added} products [{label}]")

    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(merged), len(merged), target_id)
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (source_id,))
    return added


def phase1_hioscina(cur):
    print("=== Phase 1: Merge HIOSCINA variants → BUTILBROMURO DE HIOSCINA ===")
    total = 0
    # HIOSCINA||IBUPROFENO and HIOSCINA BUTILBROMURO||IBUPROFENO → BUTILBROMURO DE HIOSCINA||IBUPROFENO (id=1004)
    for src_id in [1001, 1340, 1338]:
        total += merge_groups(cur, src_id, 1004, "HIOSCINA* → BUTILBROMURO DE HIOSCINA")

    # CAFEINA||HIOSCINA*||IBUPROFENO → BUTILBROMURO DE HIOSCINA||CAFEINA||IBUPROFENO (id=1770)
    for src_id in [1772, 1769]:
        total += merge_groups(cur, src_id, 1770, "CAFEINA+HIOSCINA* → BUTILBROMURO DE HIOSCINA+CAFEINA")

    print(f"  Total products merged: {total}")
    return total


def phase2_liquido_oral(cur):
    print("\n=== Phase 2: Merge LIQUIDO_ORAL ibuprofeno 100mg/5mL → 20mg/mL ===")
    # 100mg/5mL = 20mg/mL: merge id=2620 into id=2621
    added = merge_groups(cur, 2620, 2621, "100mg/5mL == 20mg/mL")
    print(f"  Products added to 20mg/mL group: {added}")
    return added


def phase3_cetirizina(cur):
    print("\n=== Phase 3: Fix CETIRIZINA+FENILEFRINA+IBUPROFENO concentration order ===")
    # id=52 has wrong order '200 mg + 3.3 mg + 10 mg' (sorted by IBUPROFENO first)
    # id=58 has correct order '3.3 mg + 10 mg + 200 mg' (sorted by CETIRIZINA first, canonical)
    added = merge_groups(cur, 52, 58, "wrong conc order → canonical DCI-sorted order")
    print(f"  Products merged into canonical group: {added}")
    return added


def phase4_inyectable_verify(cur):
    print("\n=== Phase 4: Verify injectable ibuprofeno concentrations via DeepSeek ===")
    cur.execute("""
        SELECT id, concentracion_norm, n_productos
        FROM grupos_equivalencia
        WHERE dci_key='IBUPROFENO' AND grupo_via='INYECTABLE'
        ORDER BY concentracion_valor
    """)
    rows = cur.fetchall()
    print(f"  Injectable ibuprofeno groups: {len(rows)}")
    for r in rows:
        print(f"    id={r[0]:5d}  conc={r[1]:12s}  n={r[2]}")

    if not rows:
        return

    prompt = (
        "Eres farmacólogo clínico especializado en Colombia. Tengo los siguientes grupos de "
        "IBUPROFENO INYECTABLE registrados en el CUM (Código Único de Medicamentos de Colombia).\n\n"
        + "\n".join(f"  id={r[0]}: {r[1]} ({r[2]} productos)" for r in rows)
        + "\n\nPor favor responde:\n"
        "1. ¿Cuáles de estas concentraciones son farmacológicamente legítimas para ibuprofeno IV?\n"
        "2. ¿Hay alguna que parezca un error de datos (por ej., concentración inusual o no registrada en farmacopeas)?\n"
        "3. Si hay un grupo sospechoso, ¿qué concentración debería tener?\n\n"
        "Responde SOLO con JSON: "
        "{\"legitimas\": [id, ...], \"sospechoso\": {\"id\": null_o_numero, \"razon\": \"...\", \"concentracion_correcta\": null_o_string}}"
    )
    resp = ds_query(prompt)
    print(f"  DeepSeek: {resp}")

    json_match = re.search(r'\{[\s\S]+\}', resp)
    if not json_match:
        print("  No JSON in response, manual review needed")
        return
    try:
        result = json.loads(json_match.group())
    except Exception as e:
        print(f"  JSON parse error: {e}")
        return

    suspicious = result.get("sospechoso", {})
    if suspicious and suspicious.get("id") and suspicious.get("concentracion_correcta"):
        sid = suspicious["id"]
        new_conc = suspicious["concentracion_correcta"]
        print(f"  Suspicious group id={sid}: {suspicious.get('razon', '')}")
        print(f"  Proposed correction: {new_conc}")
        # Find target group with correct concentration
        cur.execute(
            "SELECT id, concentracion_norm, n_productos FROM grupos_equivalencia "
            "WHERE dci_key='IBUPROFENO' AND grupo_via='INYECTABLE' AND concentracion_norm=?",
            (new_conc,)
        )
        target = cur.fetchone()
        if target:
            print(f"  Merging id={sid} into id={target[0]} ({target[1]})")
            merge_groups(cur, sid, target[0], f"wrong conc → {new_conc}")
        else:
            print(f"  No matching target group for {new_conc!r}, updating concentracion_norm directly")
            cur.execute(
                "UPDATE grupos_equivalencia SET concentracion_norm=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                (new_conc, sid)
            )
    else:
        print("  All injectable concentrations verified as legitimate.")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    phase1_hioscina(cur)
    conn.commit()

    phase2_liquido_oral(cur)
    conn.commit()

    phase3_cetirizina(cur)
    conn.commit()

    phase4_inyectable_verify(cur)
    conn.commit()

    # Final stats
    print("\n=== Final state: IBUPROFENO LIQUIDO_ORAL groups ===")
    cur.execute("""
        SELECT id, dci_key, concentracion_norm, n_productos
        FROM grupos_equivalencia
        WHERE dci_key='IBUPROFENO' AND grupo_via='LIQUIDO_ORAL'
        ORDER BY concentracion_norm
    """)
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[2]:20s}  n={r[3]}")

    print("\n=== Final state: BUTILBROMURO DE HIOSCINA+IBUPROFENO groups ===")
    cur.execute("""
        SELECT id, dci_key, concentracion_norm, n_productos
        FROM grupos_equivalencia
        WHERE dci_key LIKE '%HIOSCINA%' AND dci_key LIKE '%IBUPROFENO%'
        ORDER BY dci_key, concentracion_norm
    """)
    for r in cur.fetchall():
        print(f"  id={r[0]:5d}  conc={r[2]:20s}  n={r[3]}  dci={r[1]}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
