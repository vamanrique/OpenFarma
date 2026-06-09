"""
Fix metronidazol issues in cum_normalizado:
  Phase 1: Fix wrong ATC codes for oral/tablet metronidazol
           (A01AB17 = dental, G01AF20 = combo vaginal → P01AB01 for systemic oral/tablet)
  Phase 2: Fix residual DCI contamination for injectable metronidazol
  Phase 3: Fix concentracion_mg_ml for outlier oral suspensions
  Phase 4: DeepSeek verification of any remaining suspicious entries
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
        "max_tokens": 800,
    })
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def phase1_fix_atc(cur):
    print("=== Phase 1: Fix wrong ATC codes for oral METRONIDAZOL ===")
    # Products with A01AB17 (dental) or G01AF20 (combo vaginal) but are actually oral
    # systemic forms → should be P01AB01
    cur.execute("""
        SELECT expediente_cum, consecutivo_cum, atc_normalizado, forma_normalizada, concentracion_mg_ml
        FROM cum_normalizado
        WHERE principios_dci = '["METRONIDAZOL"]'
        AND atc_normalizado IN ('A01AB17', 'G01AF20')
        AND forma_normalizada IN ('SUSPENSION_ORAL', 'TABLETA', 'CAPSULA', 'SOLUCION_ORAL')
    """)
    rows = cur.fetchall()
    print(f"  Found {len(rows)} products with wrong ATC for oral/tablet forms:")
    for r in rows:
        print(f"    exp={r[0]} cons={r[1]} atc={r[2]} forma={r[3]} conc_ml={r[4]}")

    if rows:
        exps = list({r[0] for r in rows})
        for exp in exps:
            cur.execute("""
                UPDATE cum_normalizado
                SET atc_normalizado = 'P01AB01'
                WHERE expediente_cum = ?
                  AND principios_dci = '["METRONIDAZOL"]'
                  AND atc_normalizado IN ('A01AB17', 'G01AF20')
                  AND forma_normalizada IN ('SUSPENSION_ORAL', 'TABLETA', 'CAPSULA', 'SOLUCION_ORAL')
            """, (exp,))
        print(f"  Fixed ATC -> P01AB01 for {len(rows)} products across {len(exps)} expedientes")
    return len(rows)


def phase2_fix_dci_residual(cur):
    print("\n=== Phase 2: Fix residual DCI contamination for METRONIDAZOL inyectable ===")
    # exp=19938260 cons=1 still has ["LEVOFLOXACINO"] from old batch contamination
    cur.execute("""
        SELECT expediente_cum, consecutivo_cum, principios_dci, atc_normalizado
        FROM cum_normalizado
        WHERE expediente_cum = '19938260'
    """)
    rows = cur.fetchall()
    wrong = [(r[0], r[1]) for r in rows if r[2] != '["METRONIDAZOL"]']
    print(f"  Expediente 19938260 has {len(wrong)} rows with wrong DCI: {[r[2] for r in rows if r[2] != chr(34)+'METRONIDAZOL'+chr(34)]}")
    for exp, cons in wrong:
        cur.execute("""
            UPDATE cum_normalizado
            SET principios_dci = '["METRONIDAZOL"]'
            WHERE expediente_cum = ? AND consecutivo_cum = ?
        """, (exp, cons))
    if wrong:
        print(f"  Fixed {len(wrong)} DCI records for TENAFLOX")
    return len(wrong)


def phase3_fix_conc(cur):
    print("\n=== Phase 3: Verify concentracion_mg_ml for oral METRONIDAZOL suspensions ===")
    cur.execute("""
        SELECT expediente_cum, consecutivo_cum, concentracion_mg_ml, atc_normalizado
        FROM cum_normalizado
        WHERE principios_dci = '["METRONIDAZOL"]'
        AND forma_normalizada IN ('SUSPENSION_ORAL', 'LIQUIDO_ORAL', 'SOLUCION_ORAL')
        AND (concentracion_mg_ml IS NULL OR concentracion_mg_ml < 10 OR concentracion_mg_ml > 100)
        ORDER BY concentracion_mg_ml
    """)
    rows = cur.fetchall()
    print(f"  Suspicious concentracion_mg_ml (null, <10, or >100): {len(rows)}")
    for r in rows:
        print(f"    exp={r[0]} cons={r[1]} conc_ml={r[2]} atc={r[3]}")

    if not rows:
        return 0

    # Build DeepSeek prompt for verification
    prompt_lines = [
        "Eres farmacólogo. Para cada producto de METRONIDAZOL oral en suspensión con concentración sospechosa,",
        "proporciona la concentración correcta en mg/mL.",
        "",
        "Concentraciones estándar de METRONIDAZOL oral en Colombia:",
        "  - Suspensión pediátrica 125mg/5mL = 25 mg/mL",
        "  - Suspensión pediátrica 250mg/5mL = 50 mg/mL",
        "  - Suspensión pediátrica 200mg/5mL = 40 mg/mL",
        "  - Solución 80mg/mL (algunos productos especiales)",
        "",
        "Reglas:",
        "  - Si concentracion_actual es NULL o claramente errónea, proporciona el valor correcto",
        "  - Si no hay suficiente información, responde null",
        "",
        "Responde SOLO con JSON: {\"exp-cons\": concentracion_mg_ml_numerico, ...}",
        "",
    ]
    for r in rows:
        prompt_lines.append(f"exp={r[0]} cons={r[1]} conc_actual={r[2]}")

    resp = ds_query('\n'.join(prompt_lines))
    print(f"  DeepSeek: {resp}")

    json_match = re.search(r'\{[\s\S]+\}', resp)
    if not json_match:
        print("  No JSON in response")
        return 0
    try:
        corrections = json.loads(json_match.group())
    except Exception as e:
        print(f"  JSON parse error: {e}")
        return 0

    fixed = 0
    for r in rows:
        key = f"{r[0]}-{r[1]}"
        new_val = corrections.get(key)
        if new_val is not None and new_val != r[2]:
            print(f"  [{key}] {r[2]} -> {new_val}")
            cur.execute("""
                UPDATE cum_normalizado SET concentracion_mg_ml = ?
                WHERE expediente_cum = ? AND consecutivo_cum = ?
            """, (float(new_val), r[0], r[1]))
            fixed += 1
    print(f"  Fixed: {fixed}")
    return fixed


def phase4_verify_groups(cur):
    print("\n=== Phase 4: Verify METRONIDAZOL grupo_via counts match expectations ===")
    cur.execute("""
        SELECT g.grupo_via, g.concentracion_norm, g.n_productos,
               LENGTH(g.cum_ids) as cum_ids_len
        FROM grupos_equivalencia g
        WHERE g.dci_key = 'METRONIDAZOL'
        ORDER BY g.grupo_via, g.concentracion_norm
    """)
    for r in cur.fetchall():
        print(f"  {r[0]:20s} {str(r[2]):5s} prods  conc={r[1]}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    phase1_fix_atc(cur)
    conn.commit()

    phase2_fix_dci_residual(cur)
    conn.commit()

    phase3_fix_conc(cur)
    conn.commit()

    phase4_verify_groups(cur)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
