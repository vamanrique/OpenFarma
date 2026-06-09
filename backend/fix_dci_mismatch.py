"""
fix_dci_mismatch.py
--------------------
Fix corrupted principios_dci in cum_normalizado by syncing from grupos_equivalencia.

Root cause: During LLM batch normalization, context contamination caused ~50,000
products to be assigned fluoroquinolone DCIs (CIPROFLOXACINO, LEVOFLOXACINO, etc.)
regardless of their actual active ingredient.

grupos_equivalencia has CORRECT dci_key values (built from CUM source data).
cum_normalizado.principios_dci is CORRUPTED (~95% wrong).

Fix strategy:
  Phase 1: For every cum_id in grupos_equivalencia, restore principios_dci
           from the group's dci_key. Also fix tipo_formula.
  Phase 2: Orphan products (~2,194) not in any group:
           - INN-named (788): extract DCI from name, add to matching grupo.
           - Brand-named (1,406): use DeepSeek.
  Phase 3: Stats summary.

Usage:
    python fix_dci_mismatch.py [--dry-run] [--phase N] [--skip-ai]
"""
import os, sys, io, json, argparse, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.cum_normalizado import CumNormalizado
from app.models.grupo_equivalencia import GrupoEquivalencia
from etl.transformacion import normalizar_principio, _grupo_forma

_TIPO_FORMULA = {
    1: "monocomponente",
    2: "biconjugado",
    3: "triconjugado",
    4: "tetraconjugado",
}

# DCIs that were used as contaminants — their presence means the DCI is likely wrong
# (unless the product name confirms the drug is actually this)
CONTAMINANT_DCIS = frozenset({
    "CIPROFLOXACINO", "LEVOFLOXACINO", "MOXIFLOXACINO", "NORFLOXACINO",
    "OFLOXACINO", "EZETIMIBA", "SIMVASTATINA", "EPOETINA ALFA",
})


def _extract_dci_from_name(name: str) -> tuple[str | None, bool]:
    """
    Extract likely DCI from a product name. Returns (dci_upper, is_combo).
    Only reliable for INN-first names like 'Midazolam 15 Mg/3 Ml'.
    """
    if not name:
        return None, False
    n = name.upper().strip()

    is_combo = bool(re.search(r'\s+\+\s+|(?<=[A-Z])/(?=[A-Z])|\bMAS\b|\bPLUS\b', n))

    # Remove pharmaceutical form words at end
    n = re.sub(
        r'\s+(TABLETA|COMPRIMIDO|CAPSULA|AMPOLLA|AMPOLLAS|VIAL|'
        r'SOLUCION|SUSPENSION|EMULSION|CREMA|UNGUENTO|UNGÜENTO|'
        r'POMADA|GEL|GOTAS|JARABE|SPRAY|AEROSOL|INYECTABLE|'
        r'COLIRIO|INHALADOR|POLVO|GRANULADO|LIOFILIZADO)S?\b.*$',
        '', n,
    ).strip()

    # Take text before first dose number
    m = re.search(r'\s+\d[\d.,]*/?\d*\s*(MG|MCG|G|ML|UI|IU|%)', n)
    if m:
        n = n[:m.start()].strip()

    if len(n) < 3:
        return None, is_combo

    dci = normalizar_principio(n)
    # Remove any residual numbers
    dci = re.sub(r'\s*\d.*$', '', dci).strip()
    if len(dci) < 3:
        return None, is_combo

    return dci.upper(), is_combo


def _ask_deepseek(products_batch: list[dict]) -> dict:
    try:
        import openai
        client = openai.OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
    except Exception as e:
        print(f"  [DeepSeek] No disponible: {e}")
        return {}

    items = "\n".join(
        f'  - cum_id="{p["cum_id"]}" nombre="{p["nombre"]}" forma="{p["forma"]}"'
        for p in products_batch
    )
    system = (
        "Eres farmaceutico experto en el CUM colombiano. "
        "Para cada producto, extrae los principios activos (DCI canonico en espanol, "
        "sin sales ni sufijos). "
        'Responde SOLO JSON: {"results": [{"cum_id":"...", '
        '"principios_dci":["DCI1"], "tipo_formula":"monocomponente|biconjugado|triconjugado"}]}'
    )
    try:
        import openai
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Extrae principios activos:\n" + items},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return {r["cum_id"]: r for r in data.get("results", []) if r.get("cum_id")}
    except Exception as e:
        print(f"  [DeepSeek] Error: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-ai", action="store_true", help="Skip DeepSeek for brand-named orphans")
    parser.add_argument("--phase", type=int, default=0, help="0=all, 1=groups, 2=orphans, 3=stats")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 70)
        print("FIX DCI MISMATCH (grupos -> cum_normalizado)"
              + (" [DRY-RUN]" if args.dry_run else " [GUARDANDO]"))
        print("=" * 70)

        # ── Phase 1: Sync principios_dci from grupos_equivalencia ──────────
        if args.phase in (0, 1):
            print("\n=== FASE 1: Sincronizar principios_dci desde grupos_equivalencia ===")

            all_groups = db.query(GrupoEquivalencia).all()
            total_groups = len(all_groups)
            print(f"Grupos a procesar: {total_groups}")

            fixed = 0
            already_ok = 0
            missing = 0   # cum_id in group but not found in cum_normalizado
            processed_cids: set[str] = set()

            for i, group in enumerate(all_groups):
                correct_dcis = [d.strip() for d in group.dci_key.split("||")]
                correct_tipo = _TIPO_FORMULA.get(len(correct_dcis), "monocomponente")
                cum_ids = group.cum_ids or []

                for cum_id in cum_ids:
                    if cum_id in processed_cids:
                        continue
                    processed_cids.add(cum_id)

                    parts = cum_id.split("-", 1)
                    if len(parts) != 2:
                        missing += 1
                        continue

                    cum = db.query(CumNormalizado).filter_by(
                        expediente_cum=parts[0], consecutivo_cum=parts[1]
                    ).first()
                    if not cum:
                        missing += 1
                        continue

                    current_dcis = cum.principios_dci or []
                    needs_fix = (
                        sorted(d.upper() for d in current_dcis) !=
                        sorted(d.upper() for d in correct_dcis)
                    )

                    if needs_fix:
                        if not args.dry_run:
                            cum.principios_dci = correct_dcis
                            cum.tipo_formula = correct_tipo
                        fixed += 1
                    else:
                        already_ok += 1

                # Progress every 500 groups
                if (i + 1) % 500 == 0:
                    print(f"  ...{i+1}/{total_groups} grupos procesados "
                          f"(corregidos={fixed}, ok={already_ok})")

            print(f"\nFase 1 resultados:")
            print(f"  Productos corregidos:       {fixed}")
            print(f"  Ya correctos:               {already_ok}")
            print(f"  cum_id no encontrado en DB: {missing}")
            print(f"  Total cum_ids procesados:   {len(processed_cids)}")

        # ── Phase 2: Orphaned products (not in any group) ─────────────────
        if args.phase in (0, 2):
            print("\n=== FASE 2: Huerfanos (no estan en ningun grupo) ===")

            # Build reference sets
            all_group_cids: set[str] = set()
            for g in db.query(GrupoEquivalencia).all():
                all_group_cids.update(g.cum_ids or [])

            # Known DCIs from the now-corrected database
            known_dcis: set[str] = set()
            for r2 in db.execute(text("SELECT DISTINCT principios_dci FROM cum_normalizado WHERE principios_dci IS NOT NULL")).fetchall():
                try:
                    for d in json.loads(r2[0]):
                        known_dcis.add(d.upper())
                except Exception:
                    pass
            known_dcis -= CONTAMINANT_DCIS  # remove the bad ones

            # Fetch orphans with contaminated DCIs
            orphan_rows = db.execute(text("""
                SELECT expediente_cum, consecutivo_cum, nombre_comercial_norm,
                       principios_dci, forma_normalizada, via_normalizada
                FROM cum_normalizado
                WHERE (principios_dci LIKE '%CIPROFLOXACINO%'
                    OR principios_dci LIKE '%LEVOFLOXACINO%'
                    OR principios_dci LIKE '%MOXIFLOXACINO%'
                    OR principios_dci LIKE '%NORFLOXACINO%'
                    OR principios_dci LIKE '%EPOETINA ALFA%'
                    OR principios_dci LIKE '%EZETIMIBA%')
            """)).fetchall()

            orphans = [r for r in orphan_rows if f"{r[0]}-{r[1]}" not in all_group_cids]
            print(f"  Huerfanos con DCI contaminada: {len(orphans)}")

            inn_fixed = 0
            inn_added_to_group = 0
            brand_queue = []

            for row in orphans:
                exp, cons = row[0], row[1]
                nombre = row[2] or ""
                cum_id = f"{exp}-{cons}"

                extracted, is_combo = _extract_dci_from_name(nombre)

                # INN-named: extracted DCI is in known DCIs and different from current
                if extracted and extracted in known_dcis and not is_combo:
                    current = [d.upper() for d in json.loads(row[3] or "[]")]
                    if extracted not in current:
                        new_dcis = [extracted]
                        nuevo_tipo = _TIPO_FORMULA.get(1, "monocomponente")

                        print(f"  INN [{cum_id}] {nombre[:40]!r} -> {extracted}")
                        if not args.dry_run:
                            cum = db.query(CumNormalizado).filter_by(
                                expediente_cum=exp, consecutivo_cum=cons
                            ).first()
                            if cum:
                                cum.principios_dci = new_dcis
                                cum.tipo_formula = nuevo_tipo

                        # Try to add to matching grupo
                        forma = row[4] or ""
                        via_raw = row[5] or "[]"
                        try:
                            vias = json.loads(via_raw) if isinstance(via_raw, str) else via_raw
                        except Exception:
                            vias = []
                        via = vias[0] if vias else ""
                        grupo_via = _grupo_forma(forma, via)

                        # Find group matching (dci_key=extracted, grupo_via)
                        # Prefer exact conc match; fallback to any group with same DCI+via
                        matching_groups = db.query(GrupoEquivalencia).filter_by(
                            dci_key=extracted, grupo_via=grupo_via
                        ).all()

                        if matching_groups:
                            # Add to the largest group (most likely the canonical one)
                            best = max(matching_groups, key=lambda g: g.n_productos)
                            print(f"    -> grupo [{best.id}] {best.dci_key} | {best.grupo_via} | {best.concentracion_norm}")
                            if not args.dry_run:
                                ids = list(best.cum_ids or [])
                                if cum_id not in ids:
                                    ids.append(cum_id)
                                    best.cum_ids = ids
                                    best.n_productos = len(ids)
                            inn_added_to_group += 1

                        inn_fixed += 1
                else:
                    # Brand name or combo → queue for DeepSeek
                    brand_queue.append({
                        "cum_id": cum_id,
                        "exp": exp,
                        "cons": cons,
                        "nombre": nombre,
                        "forma": row[4] or "",
                        "via": row[5] or "[]",
                    })

            print(f"\n  INN huerfanos corregidos:        {inn_fixed}")
            print(f"  INN huerfanos asignados a grupo: {inn_added_to_group}")
            print(f"  Marca/combo para DeepSeek:       {len(brand_queue)}")

            # DeepSeek for brand-named orphans
            if brand_queue and not args.skip_ai:
                print(f"\n  Procesando {len(brand_queue)} marca/combo con DeepSeek...")
                BATCH = 20
                ai_fixed = 0

                for i in range(0, len(brand_queue), BATCH):
                    batch = brand_queue[i : i + BATCH]
                    bn = i // BATCH + 1
                    total_batches = (len(brand_queue) + BATCH - 1) // BATCH
                    print(f"  Batch {bn}/{total_batches}...")
                    ds_batch = [
                        {"cum_id": p["cum_id"], "nombre": p["nombre"], "forma": p["forma"]}
                        for p in batch
                    ]
                    results = _ask_deepseek(ds_batch)

                    for item in batch:
                        r = results.get(item["cum_id"])
                        if not r or not r.get("principios_dci"):
                            continue

                        new_dcis_raw = r["principios_dci"]
                        new_dcis = [normalizar_principio(d).upper() for d in new_dcis_raw]
                        new_dcis = [d for d in new_dcis if len(d) >= 3]
                        if not new_dcis:
                            continue

                        new_key = "||".join(sorted(new_dcis))
                        nuevo_tipo = _TIPO_FORMULA.get(len(new_dcis), "monocomponente")

                        print(f"  AI [{item['cum_id']}] {item['nombre'][:40]!r} -> {new_key}")
                        if not args.dry_run:
                            cum = db.query(CumNormalizado).filter_by(
                                expediente_cum=item["exp"],
                                consecutivo_cum=item["cons"],
                            ).first()
                            if cum:
                                cum.principios_dci = new_dcis
                                cum.tipo_formula = nuevo_tipo

                        # Try to add to group
                        try:
                            vias = json.loads(item["via"]) if isinstance(item["via"], str) else []
                        except Exception:
                            vias = []
                        via = vias[0] if vias else ""
                        grupo_via = _grupo_forma(item["forma"], via)

                        if not args.dry_run:
                            matching = db.query(GrupoEquivalencia).filter_by(
                                dci_key=new_key, grupo_via=grupo_via
                            ).all()
                            if matching:
                                best = max(matching, key=lambda g: g.n_productos)
                                ids = list(best.cum_ids or [])
                                cid = item["cum_id"]
                                if cid not in ids:
                                    ids.append(cid)
                                    best.cum_ids = ids
                                    best.n_productos = len(ids)

                        ai_fixed += 1

                print(f"  AI corregidos: {ai_fixed}")
            elif brand_queue and args.skip_ai:
                print(f"  (--skip-ai: omitiendo {len(brand_queue)} marca/combo)")

        # ── Phase 3: Stats ─────────────────────────────────────────────────
        if args.phase in (0, 3):
            print("\n=== FASE 3: Estadisticas ===")

            if not args.dry_run and args.phase != 3:
                db.flush()

            total_cum = db.execute(text("SELECT COUNT(*) FROM cum_normalizado")).scalar()
            still_bad = db.execute(text("""
                SELECT COUNT(*) FROM cum_normalizado
                WHERE (principios_dci LIKE '%CIPROFLOXACINO%'
                    OR principios_dci LIKE '%LEVOFLOXACINO%'
                    OR principios_dci LIKE '%MOXIFLOXACINO%'
                    OR principios_dci LIKE '%NORFLOXACINO%'
                    OR principios_dci LIKE '%EPOETINA ALFA%')
                  AND nombre_comercial_norm NOT LIKE '%CIPROFLOXACIN%'
                  AND nombre_comercial_norm NOT LIKE '%LEVOFLOXACIN%'
                  AND nombre_comercial_norm NOT LIKE '%MOXIFLOXACIN%'
                  AND nombre_comercial_norm NOT LIKE '%NORFLOXACIN%'
                  AND nombre_comercial_norm NOT LIKE '%ERITROPOYETIN%'
                  AND nombre_comercial_norm NOT LIKE '%EPOETINA%'
            """)).scalar()

            dci_dist = db.execute(text("""
                SELECT principios_dci, COUNT(*) as n
                FROM cum_normalizado
                GROUP BY principios_dci
                ORDER BY n DESC
                LIMIT 10
            """)).fetchall()

            print(f"  Total cum_normalizado: {total_cum}")
            print(f"  Aun con DCI incorrecto (estimado): {still_bad}")
            print(f"  Top 10 DCIs:")
            for r in dci_dist:
                pct = r[1] / total_cum * 100
                print(f"    {str(r[0])[:55]:55s}  {r[1]:6d} ({pct:.1f}%)")

        # ── Commit ─────────────────────────────────────────────────────────
        if not args.dry_run:
            db.commit()
            print("\n=== GUARDADO EXITOSO ===")
        else:
            db.rollback()
            print("\n=== DRY-RUN completado ===")

    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
