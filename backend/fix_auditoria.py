"""
fix_auditoria.py
-----------------
Auditoría guiada + correcciones para alcanzar confiabilidad excelente.

Fases:
  1. tipo_formula: normaliza MONO→monocomponente, BI→biconjugado, etc.
     También deriva de principios_dci para los OTRO/desconocidos.
  2. ATC contaminados: ~20 productos con J01MA pero DCI no-fluoroquinolona.
     DeepSeek asigna el ATC correcto.
  3. Huérfanos (no en ningún grupo): DeepSeek clasifica y asigna a grupo.
  4. Componentes faltantes: DeepSeek infiere componentes para 191 productos.
  5. Stats resumen.

Uso:
    python fix_auditoria.py [--dry-run] [--phase N] [--skip-ai]
"""
import os, sys, io, json, re, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.cum_normalizado import CumNormalizado
from app.models.grupo_equivalencia import GrupoEquivalencia
from etl.transformacion import normalizar_principio, _grupo_forma

# ── Constantes ─────────────────────────────────────────────────────────────

TIPO_MAP = {
    "MONO":  "monocomponente",
    "BI":    "biconjugado",
    "TRI":   "triconjugado",
    "TETRA": "tetraconjugado",
    "OTRO":  None,   # derivar de len(principios_dci)
}

TIPO_BY_COUNT = {1: "monocomponente", 2: "biconjugado", 3: "triconjugado", 4: "tetraconjugado"}

# ATC prefijos de fluoroquinolonas (J01MA)
FLUOROQUINOLONA_ATC = {"J01MA"}
FLUOROQUINOLONA_DCI = {"CIPROFLOXACINO", "LEVOFLOXACINO", "MOXIFLOXACINO",
                        "NORFLOXACINO", "OFLOXACINO", "PEFLOXACINO"}


# ── DeepSeek helper ────────────────────────────────────────────────────────

def _deepseek(system: str, user: str, schema_hint: str = "") -> dict | None:
    try:
        import openai
        client = openai.OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"  [DeepSeek error] {e}")
        return None


def _ask_batch(items: list[dict], task: str) -> dict:
    """
    task="atc"    → {cum_id: {"atc": "J01MA02"}}
    task="grupo"  → {cum_id: {"principios_dci":[], "grupo_via":"SOLIDO_ORAL",
                               "concentracion_norm":"500 mg", ...}}
    task="comp"   → {cum_id: {"componentes":[{"dci":"X","concentracion_mg_ml":5.0}]}}
    """
    if task == "atc":
        system = (
            "Eres farmacéutico experto en clasificación ATC. "
            "Para cada producto, devuelve el código ATC correcto (7 dígitos). "
            'JSON: {"results":[{"cum_id":"...","atc":"J01MA02"}]}'
        )
        lines = "\n".join(
            f'  - cum_id="{p["cum_id"]}" nombre="{p["nombre"]}" dci="{p["dci"]}"'
            for p in items
        )
        user = "Asigna el código ATC correcto:\n" + lines

    elif task == "grupo":
        system = (
            "Eres farmacéutico experto en el CUM colombiano. "
            "Para cada producto devuelve: principios_dci (lista de DCI canónicos sin sales), "
            "tipo_formula (monocomponente|biconjugado|triconjugado|tetraconjugado), "
            "grupo_via (SOLIDO_ORAL|SOLIDO_ORAL_LP|LIQUIDO_ORAL|INYECTABLE|TOPICO|INHALADO|"
            "OFTALMICO|OTICO|NASAL|VAGINAL|RECTAL|TRANSDERMICO|SUBLINGUAL), "
            "concentracion_norm (string display ej '500 mg','5 mg/mL','5%','SIN_CONCENTRACION'). "
            'JSON: {"results":[{"cum_id":"...","principios_dci":["DCI"],'
            '"tipo_formula":"monocomponente","grupo_via":"SOLIDO_ORAL",'
            '"concentracion_norm":"500 mg","concentracion_valor":500.0,'
            '"concentracion_unidad":"mg"}]}'
        )
        lines = "\n".join(
            f'  - cum_id="{p["cum_id"]}" nombre="{p["nombre"]}" '
            f'forma="{p["forma"]}" via="{p["via"]}" conc_mg_ml="{p.get("conc_mg_ml","")}"'
            for p in items
        )
        user = "Clasifica estos productos del CUM colombiano:\n" + lines

    elif task == "comp":
        system = (
            "Eres farmacéutico experto. Para cada producto, extrae los componentes activos "
            "con su concentración en mg/mL (0 si no aplica). "
            'JSON: {"results":[{"cum_id":"...","componentes":[{"dci":"DCI","concentracion_mg_ml":5.0,"dosis_mg":500.0}]}]}'
        )
        lines = "\n".join(
            f'  - cum_id="{p["cum_id"]}" nombre="{p["nombre"]}" '
            f'dci="{p["dci"]}" forma="{p["forma"]}"'
            for p in items
        )
        user = "Extrae componentes con concentración:\n" + lines
    else:
        return {}

    data = _deepseek(system, user)
    if not data:
        return {}
    return {r["cum_id"]: r for r in data.get("results", []) if r.get("cum_id")}


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-ai", action="store_true")
    parser.add_argument("--phase", type=int, default=0,
                        help="0=all, 1=tipo_formula, 2=atc, 3=huerfanos, 4=componentes, 5=stats")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 70)
        print("AUDITORÍA + FIX CONFIABILIDAD"
              + (" [DRY-RUN]" if args.dry_run else " [GUARDANDO]"))
        print("=" * 70)

        # ── Fase 1: tipo_formula ─────────────────────────────────────────
        if args.phase in (0, 1):
            print("\n=== FASE 1: Normalizar tipo_formula ===")

            bad_rows = db.execute(text("""
                SELECT expediente_cum, consecutivo_cum, tipo_formula, principios_dci
                FROM cum_normalizado
                WHERE tipo_formula IN ('MONO','BI','TRI','TETRA','OTRO')
                   OR tipo_formula IS NULL
            """)).fetchall()

            print(f"  Productos con tipo_formula incorrecto o NULL: {len(bad_rows)}")

            fixed_tf = 0
            for exp, cons, tf, pdci_json in bad_rows:
                # Derive tipo from map
                nuevo = TIPO_MAP.get(tf or "OTRO")  # None for OTRO/NULL
                if nuevo is None:
                    # Derive from DCI count
                    try:
                        pdcis = json.loads(pdci_json or "[]")
                    except Exception:
                        pdcis = []
                    n = len(pdcis)
                    nuevo = TIPO_BY_COUNT.get(n, "monocomponente")

                if not args.dry_run:
                    db.execute(text(
                        "UPDATE cum_normalizado SET tipo_formula=:tf "
                        "WHERE expediente_cum=:exp AND consecutivo_cum=:cons"
                    ), {"tf": nuevo, "exp": exp, "cons": cons})
                fixed_tf += 1

            print(f"  tipo_formula corregidos: {fixed_tf}")

            # Also fix the startup migration to include this
            if not args.dry_run:
                db.flush()

        # ── Fase 2: ATC contaminados ─────────────────────────────────────
        if args.phase in (0, 2):
            print("\n=== FASE 2: ATC contaminados (J01MA en no-fluoroquinolonas) ===")

            # Products with J01MA ATC but DCI is not a fluoroquinolone
            atc_bad = db.execute(text("""
                SELECT expediente_cum, consecutivo_cum,
                       nombre_comercial_norm, principios_dci, atc_normalizado
                FROM cum_normalizado
                WHERE atc_normalizado LIKE 'J01MA%'
            """)).fetchall()

            # Filter: keep only those whose DCI is NOT a fluoroquinolone
            truly_bad = []
            for row in atc_bad:
                pdcis = []
                try:
                    pdcis = json.loads(row[3] or "[]")
                except Exception:
                    pass
                if not any(d.upper() in FLUOROQUINOLONA_DCI for d in pdcis):
                    truly_bad.append(row)

            print(f"  Candidatos J01MA con DCI no-fluoroquinolona: {len(truly_bad)}")
            if truly_bad:
                for r in truly_bad[:5]:
                    print(f"    {r[0]}-{r[1]}: {(r[2] or '')[:40]} | DCI={r[3]} | ATC={r[4]}")

            if truly_bad and not args.skip_ai:
                batch = [
                    {"cum_id": f"{r[0]}-{r[1]}", "nombre": r[2] or "",
                     "dci": r[3] or ""}
                    for r in truly_bad
                ]
                BSIZE = 20
                fixed_atc = 0
                for i in range(0, len(batch), BSIZE):
                    lote = batch[i:i+BSIZE]
                    print(f"  ATC batch {i//BSIZE+1}/{(len(batch)+BSIZE-1)//BSIZE}...")
                    results = _ask_batch(lote, "atc")
                    for item in lote:
                        r = results.get(item["cum_id"])
                        if not r or not r.get("atc"):
                            continue
                        new_atc = r["atc"].strip().upper().replace(".", "")
                        if len(new_atc) < 4:
                            continue
                        parts = item["cum_id"].split("-", 1)
                        print(f"    FIX {item['cum_id']}: {item['nombre'][:35]} -> ATC={new_atc}")
                        if not args.dry_run:
                            db.execute(text(
                                "UPDATE cum_normalizado SET atc_normalizado=:atc "
                                "WHERE expediente_cum=:exp AND consecutivo_cum=:cons"
                            ), {"atc": new_atc, "exp": parts[0], "cons": parts[1]})
                        fixed_atc += 1
                print(f"  ATC corregidos: {fixed_atc}")
            elif args.skip_ai:
                print("  (--skip-ai: omitiendo)")

        # ── Fase 3: Huérfanos sin grupo ───────────────────────────────────
        if args.phase in (0, 3):
            print("\n=== FASE 3: Productos huérfanos (no en ningún grupo) ===")

            # Build set of all cum_ids in groups
            all_group_cids: set[str] = set()
            for g in db.query(GrupoEquivalencia).all():
                all_group_cids.update(g.cum_ids or [])

            # Build known DCIs from groups
            known_dcis: set[str] = set()
            for g in db.query(GrupoEquivalencia).all():
                for d in g.dci_key.split("||"):
                    known_dcis.add(d.strip().upper())

            # All products not in any group
            all_cum = db.execute(text(
                "SELECT expediente_cum, consecutivo_cum, nombre_comercial_norm, "
                "principios_dci, forma_normalizada, via_normalizada, concentracion_mg_ml "
                "FROM cum_normalizado"
            )).fetchall()

            orphans = [r for r in all_cum if f"{r[0]}-{r[1]}" not in all_group_cids]
            print(f"  Total huérfanos: {len(orphans)}")

            # Split: those we can fix by name vs those needing DeepSeek
            rule_fixed = 0
            ai_queue = []

            for row in orphans:
                exp, cons = row[0], row[1]
                cum_id = f"{exp}-{cons}"
                nombre = row[2] or ""
                pdcis_raw = []
                try:
                    pdcis_raw = json.loads(row[3] or "[]")
                except Exception:
                    pass

                # Only process if we already know the correct DCI
                if not pdcis_raw:
                    ai_queue.append(row)
                    continue

                dci_key = "||".join(sorted(d.upper() for d in pdcis_raw))
                forma = row[4] or ""
                via_raw = row[5] or "[]"
                try:
                    vias = json.loads(via_raw) if isinstance(via_raw, str) else via_raw
                except Exception:
                    vias = []
                via = vias[0] if vias else ""
                grupo_via = _grupo_forma(forma, via)

                # Find matching group
                matching = db.query(GrupoEquivalencia).filter_by(
                    dci_key=dci_key, grupo_via=grupo_via
                ).all()

                if matching:
                    # Add to the group with most products (most representative)
                    best = max(matching, key=lambda g: g.n_productos)
                    print(f"  ASSIGN [{cum_id}] {nombre[:40]!r}"
                          f" -> grupo [{best.id}] {dci_key} | {grupo_via} | {best.concentracion_norm}")
                    if not args.dry_run:
                        ids = list(best.cum_ids or [])
                        if cum_id not in ids:
                            ids.append(cum_id)
                            best.cum_ids = ids
                            best.n_productos = len(ids)
                    rule_fixed += 1
                else:
                    # Known DCI but no group with that via → queue for DeepSeek
                    # to verify and possibly create group
                    ai_queue.append(row)

            print(f"  Asignados por regla (DCI ya conocido): {rule_fixed}")
            print(f"  Para DeepSeek: {len(ai_queue)}")

            if ai_queue and not args.skip_ai:
                BSIZE = 15
                ai_fixed = 0
                created_groups = 0

                for i in range(0, len(ai_queue), BSIZE):
                    lote = ai_queue[i:i+BSIZE]
                    bn = i // BSIZE + 1
                    total_b = (len(ai_queue) + BSIZE - 1) // BSIZE
                    print(f"  Batch {bn}/{total_b} ({len(lote)} productos)...")

                    batch_items = [
                        {
                            "cum_id": f"{r[0]}-{r[1]}",
                            "nombre": r[2] or "",
                            "forma": r[4] or "",
                            "via": str(r[5] or "[]"),
                            "conc_mg_ml": str(r[6] or ""),
                        }
                        for r in lote
                    ]
                    results = _ask_batch(batch_items, "grupo")

                    for item, row in zip(batch_items, lote):
                        r = results.get(item["cum_id"])
                        if not r or not r.get("principios_dci"):
                            continue

                        new_dcis = [normalizar_principio(d).upper()
                                    for d in r["principios_dci"]]
                        new_dcis = [d for d in new_dcis if len(d) >= 3]
                        if not new_dcis:
                            continue

                        new_key = "||".join(sorted(new_dcis))
                        nuevo_tipo = TIPO_BY_COUNT.get(len(new_dcis), "monocomponente")
                        grupo_via = r.get("grupo_via", "")
                        conc_norm = r.get("concentracion_norm")
                        conc_val = r.get("concentracion_valor")
                        conc_unit = r.get("concentracion_unidad")
                        cum_id = item["cum_id"]
                        exp, cons = row[0], row[1]

                        print(f"  AI [{cum_id}] {item['nombre'][:40]!r}"
                              f" -> {new_key} | {grupo_via} | {conc_norm}")

                        if not args.dry_run:
                            # Update principios_dci if changed
                            old_pdcis = []
                            try:
                                old_pdcis = json.loads(row[3] or "[]")
                            except Exception:
                                pass
                            old_key = "||".join(sorted(d.upper() for d in old_pdcis))
                            if old_key != new_key:
                                db.execute(text(
                                    "UPDATE cum_normalizado "
                                    "SET principios_dci=:pdci, tipo_formula=:tf "
                                    "WHERE expediente_cum=:exp AND consecutivo_cum=:cons"
                                ), {
                                    "pdci": json.dumps(new_dcis, ensure_ascii=False),
                                    "tf": nuevo_tipo,
                                    "exp": exp, "cons": cons,
                                })

                            # Find or create grupo
                            grupo = db.query(GrupoEquivalencia).filter_by(
                                dci_key=new_key, grupo_via=grupo_via,
                                concentracion_norm=conc_norm,
                            ).first()

                            if not grupo:
                                grupo = GrupoEquivalencia(
                                    dci_key=new_key,
                                    grupo_via=grupo_via,
                                    concentracion_norm=conc_norm,
                                    concentracion_valor=conc_val,
                                    concentracion_unidad=conc_unit,
                                    cum_ids=[],
                                    n_productos=0,
                                    revisado_ia=True,
                                )
                                db.add(grupo)
                                db.flush()
                                created_groups += 1

                            ids = list(grupo.cum_ids or [])
                            if cum_id not in ids:
                                ids.append(cum_id)
                                grupo.cum_ids = ids
                                grupo.n_productos = len(ids)

                        ai_fixed += 1

                    if not args.dry_run:
                        db.flush()

                print(f"\n  AI huérfanos procesados: {ai_fixed}")
                print(f"  Nuevos grupos creados:   {created_groups}")
            elif args.skip_ai:
                print("  (--skip-ai: omitiendo DeepSeek)")

        # ── Fase 4: Componentes faltantes ────────────────────────────────
        if args.phase in (0, 4):
            print("\n=== FASE 4: Componentes faltantes ===")

            no_comp = db.execute(text("""
                SELECT expediente_cum, consecutivo_cum,
                       nombre_comercial_norm, principios_dci, forma_normalizada
                FROM cum_normalizado
                WHERE (componentes IS NULL OR componentes = '[]')
                  AND principios_dci IS NOT NULL
                  AND principios_dci != '[]'
                LIMIT 300
            """)).fetchall()

            print(f"  Productos sin componentes: {len(no_comp)}")

            if no_comp and not args.skip_ai:
                BSIZE = 20
                fixed_comp = 0

                for i in range(0, len(no_comp), BSIZE):
                    lote = no_comp[i:i+BSIZE]
                    bn = i // BSIZE + 1
                    total_b = (len(no_comp) + BSIZE - 1) // BSIZE
                    print(f"  Batch {bn}/{total_b}...")

                    batch_items = [
                        {
                            "cum_id": f"{r[0]}-{r[1]}",
                            "nombre": r[2] or "",
                            "dci": r[3] or "[]",
                            "forma": r[4] or "",
                        }
                        for r in lote
                    ]
                    results = _ask_batch(batch_items, "comp")

                    for item, row in zip(batch_items, lote):
                        r = results.get(item["cum_id"])
                        if not r or not r.get("componentes"):
                            continue
                        comps = r["componentes"]
                        if not isinstance(comps, list) or not comps:
                            continue

                        exp, cons = row[0], row[1]
                        print(f"  COMP [{item['cum_id']}] {item['nombre'][:35]} "
                              f"-> {len(comps)} componentes")

                        if not args.dry_run:
                            db.execute(text(
                                "UPDATE cum_normalizado SET componentes=:comp "
                                "WHERE expediente_cum=:exp AND consecutivo_cum=:cons"
                            ), {
                                "comp": json.dumps(comps, ensure_ascii=False),
                                "exp": exp, "cons": cons,
                            })
                        fixed_comp += 1

                    if not args.dry_run:
                        db.flush()

                print(f"  Componentes completados: {fixed_comp}")
            elif args.skip_ai:
                print("  (--skip-ai: omitiendo)")

        # ── Fase 5: Stats ────────────────────────────────────────────────
        if args.phase in (0, 5):
            print("\n=== FASE 5: Resumen de confiabilidad ===")

            if not args.dry_run:
                db.flush()

            total = db.execute(text("SELECT COUNT(*) FROM cum_normalizado")).scalar()
            total_g = db.execute(text("SELECT COUNT(*) FROM grupos_equivalencia")).scalar()

            bad_tf = db.execute(text(
                "SELECT COUNT(*) FROM cum_normalizado "
                "WHERE tipo_formula IN ('MONO','BI','TRI','TETRA','OTRO') "
                "   OR tipo_formula IS NULL"
            )).scalar()

            null_dci = db.execute(text(
                "SELECT COUNT(*) FROM cum_normalizado "
                "WHERE principios_dci IS NULL OR principios_dci = '[]'"
            )).scalar()

            null_atc = db.execute(text(
                "SELECT COUNT(*) FROM cum_normalizado WHERE atc_normalizado IS NULL"
            )).scalar()

            no_comp_count = db.execute(text(
                "SELECT COUNT(*) FROM cum_normalizado "
                "WHERE componentes IS NULL OR componentes = '[]'"
            )).scalar()

            # Orphans
            all_cids: set[str] = set()
            for r in db.execute(text("SELECT cum_ids FROM grupos_equivalencia")).fetchall():
                try:
                    all_cids.update(json.loads(r[0] or "[]"))
                except Exception:
                    pass
            orphan_count = total - len(all_cids)

            contam_est = db.execute(text("""
                SELECT COUNT(*) FROM cum_normalizado
                WHERE (principios_dci LIKE '%CIPROFLOXACINO%'
                    OR principios_dci LIKE '%LEVOFLOXACINO%')
                  AND nombre_comercial_norm NOT LIKE '%CIPROFLOXACIN%'
                  AND nombre_comercial_norm NOT LIKE '%LEVOFLOXACIN%'
            """)).scalar()

            print(f"\n  Total productos cum_normalizado: {total}")
            print(f"  Total grupos_equivalencia:       {total_g}")
            print(f"  Huerfanos (sin grupo):           {orphan_count} ({orphan_count/total*100:.1f}%)")
            print(f"  DCI NULL o vacios:               {null_dci}")
            print(f"  DCI contaminados (estimado):     {contam_est}")
            print(f"  tipo_formula incorrecto:         {bad_tf}")
            print(f"  ATC NULL:                        {null_atc}")
            print(f"  Sin componentes:                 {no_comp_count}")

            score = 100.0
            score -= (orphan_count / total) * 30   # 30% del score
            score -= (contam_est / total) * 25      # 25%
            score -= (bad_tf / total) * 15          # 15%
            score -= (null_dci / total) * 20        # 20%
            score -= (no_comp_count / total) * 10   # 10%
            print(f"\n  Score confiabilidad estimado: {score:.1f}/100")

        # ── Commit ──────────────────────────────────────────────────────
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
