"""
fix_null_conc3.py — Normalización definitiva de concentraciones NULL
====================================================================
Fase 1: extracción rule-based desde componentes[].concentracion_mg_ml  (~80 grupos)
Fase 2: DeepSeek para grupos sin ningún dato numérico                  (~209 grupos)
Fase 3: residuos → SIN_CONCENTRACION
Fase 4: merge de duplicados resultantes

Uso:
    python fix_null_conc3.py [--dry-run] [--skip-ai] [--phase N]
"""
import os, sys, io, json, argparse, httpx, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.grupo_equivalencia import GrupoEquivalencia
from app.models.cum_normalizado import CumNormalizado

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# Threshold: componentes values above this are treated as UI (not mg/mL).
# Common drugs like Metamizol 300mg/mL and Zinc oxide 200mg/mL are below this.
# True UI-based drugs (Polymyxin B ~6000, Nystatin ~10000) are above.
UI_THRESHOLD = 1500.0

# DCIs / keywords that indicate non-quantifiable biologics
BIOLOGIC_TOKENS = {
    "VIRUS", "VACUNA", "BCG", "SALMONELLA", "POLISACARIDO", "SEROTIPO",
    "ONASEMNOGEN", "VORETIGEN", "LYSATE", "LISADO", "LISADOS",
    "EXTRACTO", "MYCOBACTERIUM", "TOXINA", "ANTITOXINA",
    "INMUNOGLOBULINA", "ALBUMINA", "TOXOIDE", "ANTIGEN",
    "DIOXIDO DE CARBONO", "OXIGENO", "PROTOXIDO", "NITROSO",
    "RAXTOZINAMERAN", "OMV", "CRM197",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_biologic(dci_key: str) -> bool:
    upper = dci_key.upper()
    return any(t in upper for t in BIOLOGIC_TOKENS)


def _sort_key(dci: str) -> str:
    return dci.upper().strip()


def _fmt_val(mg_ml: float, via: str) -> tuple[str, float, str]:
    """Returns (display_str, valor, unidad) for one component."""
    if via == "TOPICO":
        if mg_ml >= UI_THRESHOLD:
            return f"{mg_ml:g} UI/g", mg_ml, "UI/g"
        pct = round(mg_ml / 10.0, 4)
        pct = float(f"{pct:g}")
        return f"{pct:g}%", pct, "%"
    else:
        if mg_ml >= UI_THRESHOLD:
            return f"{mg_ml:g} UI/mL", mg_ml, "UI/mL"
        v = round(mg_ml, 3)
        v = float(f"{v:g}")
        return f"{v:g} mg/mL", v, "mg/mL"


def _build_concentration_from_components(
    componentes: list, dci_key: str, grupo_via: str
) -> tuple[str | None, float | None, str | None]:
    """
    Build concentracion_norm from componentes[].concentracion_mg_ml.
    Components are ordered to match dci_key sort order.
    Returns (norm, valor, unidad) or (None, None, None).
    """
    # Map normalized DCI → mg_ml
    comp_map: dict[str, float] = {}
    for c in componentes:
        dci = (c.get("dci") or "").upper().strip()
        v = c.get("concentracion_mg_ml")
        if v and v > 0:
            comp_map[dci] = float(v)

    if not comp_map:
        return None, None, None

    # Get canonical DCI list from dci_key (already sorted)
    dcis = [d.strip() for d in dci_key.split("||")]

    # Match each canonical DCI to comp_map (best substring match)
    parts_display = []
    parts_val = []
    first_val = first_unit = None

    for dci in dcis:
        mg_ml = comp_map.get(dci)
        if mg_ml is None:
            # Fuzzy: longest overlap
            for key, v in comp_map.items():
                if key in dci or dci in key or dci[:8] in key:
                    mg_ml = v
                    break
        if mg_ml is None:
            return None, None, None  # can't build complete string

        display, val, unit = _fmt_val(mg_ml, grupo_via)
        parts_display.append(display)
        if first_val is None:
            first_val, first_unit = val, unit

    norm = " + ".join(parts_display)
    return norm, first_val, first_unit


def _consensus(values: list) -> tuple | None:
    """Return the most common (norm, val, unit) tuple if it appears ≥ 1 time.
    For single-product groups always returns the only value."""
    if not values:
        return None
    c = Counter(v[0] for v in values if v[0])  # count by norm string
    if not c:
        return None
    best_norm = c.most_common(1)[0][0]
    for v in values:
        if v[0] == best_norm:
            return v
    return None


# ── Phase 1: Rule-based from component mg_ml ─────────────────────────────────

def phase1_rule_based(db, dry_run: bool) -> list[int]:
    """Returns list of group IDs still NULL after this phase."""
    print("\n=== FASE 1: Extracción rule-based desde componentes[].concentracion_mg_ml ===")

    null_groups = db.query(GrupoEquivalencia).filter(
        GrupoEquivalencia.concentracion_norm == None
    ).all()

    fixed = 0
    still_null_ids = []

    for g in null_groups:
        # Skip biologics/vaccines/gases — they belong in Phase 3 (SIN_CONCENTRACION)
        if _is_biologic(g.dci_key):
            still_null_ids.append(g.id)
            continue

        cids = g.cum_ids or []
        candidates: list[tuple] = []

        for cid in cids[:8]:
            if "-" not in cid:
                continue
            e, c = cid.split("-", 1)
            cum = db.query(CumNormalizado).filter_by(
                expediente_cum=e, consecutivo_cum=c
            ).first()
            if not cum or not cum.componentes:
                continue

            result = _build_concentration_from_components(
                cum.componentes, g.dci_key, g.grupo_via
            )
            if result[0]:
                candidates.append(result)

        chosen = _consensus(candidates)
        if chosen:
            norm, val, unit = chosen
            print(f"  RULE [{g.id}] {g.dci_key[:42]} | {g.grupo_via} → {norm}")
            if not dry_run:
                g.concentracion_norm = norm
                g.concentracion_valor = val
                g.concentracion_unidad = unit
            fixed += 1
        else:
            still_null_ids.append(g.id)

    if not dry_run:
        db.flush()

    print(f"\n  Fase 1 fijados: {fixed} | Siguen NULL: {len(still_null_ids)}")
    return still_null_ids


# ── Phase 2: DeepSeek para grupos sin datos numéricos ────────────────────────

def _deepseek_batch(groups_info: list[dict]) -> list[dict]:
    system = (
        "Eres un farmacéutico colombiano experto en el Registro CUM-INVIMA. "
        "Para cada grupo de medicamentos registrados en Colombia, determina la "
        "concentración normalizada más representativa o indica que no aplica. "
        "Sé CONSERVADOR: solo da una concentración si estás muy seguro. "
        "Para biologicos, vacunas, gases, agua, nutrición parenteral, lisados bacterianos, "
        "extractos alergénicos, medios de contraste, o productos sin concentración "
        "farmacológica estandarizada → devuelve SIN_CONCENTRACION. "
        "Si el principio activo puede tener MÚLTIPLES concentraciones estándar comunes → "
        "devuelve SIN_CONCENTRACION (ej: Heparina 5000UI/mL vs 25000UI/mL). "
        "Responde SOLO con JSON válido."
    )

    user = json.dumps({
        "grupos": groups_info,
        "instruccion": (
            "Para cada grupo devuelve: id, tipo ('valor'|'SIN_CONCENTRACION'|'desconocido'), "
            "concentracion_norm (string o null), concentracion_valor (número o null), "
            "concentracion_unidad (string o null). "
            "Formato: {'resultados': [...]}"
        ),
    }, ensure_ascii=False)

    with httpx.Client(timeout=90.0) as client:
        resp = client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 4096,
            },
        )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    return parsed.get("resultados", [])


VALID_UNITS = {
    "mg", "mcg", "g", "UI", "UI/mL", "UI/g", "mg/mL", "mg/g", "%",
    "mEq", "mEq/mL", "mmol", "mmol/mL", "mg/dosis", "mcg/dosis",
    "ng/mL", "mg/m2", "UI/kg", "mL",
}


def phase2_deepseek(db, still_null_ids: list[int], dry_run: bool) -> list[int]:
    print("\n=== FASE 2: DeepSeek para grupos sin datos numéricos ===")

    if not DEEPSEEK_API_KEY:
        print("  DEEPSEEK_API_KEY no encontrada — saltando fase 2")
        return still_null_ids

    groups = db.query(GrupoEquivalencia).filter(
        GrupoEquivalencia.id.in_(still_null_ids)
    ).all()

    print(f"  Grupos a procesar: {len(groups)}")

    id_to_group = {g.id: g for g in groups}
    fixed = 0
    still_null = []
    BATCH = 15

    for batch_start in range(0, len(groups), BATCH):
        batch = groups[batch_start: batch_start + BATCH]
        groups_info = []

        for g in batch:
            cids = g.cum_ids or []
            product_names = []
            comp_summary = []

            for cid in cids[:5]:
                if "-" not in cid:
                    continue
                e, c = cid.split("-", 1)
                row = db.execute(text(
                    "SELECT nombre_comercial_norm, componentes FROM cum_normalizado "
                    "WHERE expediente_cum=:e AND consecutivo_cum=:c"
                ), {"e": e, "c": c}).fetchone()
                if row:
                    if row[0]:
                        product_names.append(row[0][:50])
                    if row[1]:
                        try:
                            comps = json.loads(row[1])
                            for comp in comps[:4]:
                                dci = comp.get("dci", "")
                                dosis = comp.get("dosis_mg")
                                mg_ml = comp.get("concentracion_mg_ml")
                                comp_summary.append(
                                    f"{dci}: dosis={dosis}, mg_ml={mg_ml}"
                                )
                        except Exception:
                            pass

            groups_info.append({
                "id": g.id,
                "dci_key": g.dci_key,
                "grupo_via": g.grupo_via,
                "n_productos": g.n_productos,
                "nombres_muestra": list(dict.fromkeys(product_names))[:4],
                "componentes_muestra": comp_summary[:6],
            })

        batch_num = batch_start // BATCH + 1
        total_batches = (len(groups) + BATCH - 1) // BATCH
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} grupos)...")

        try:
            results = _deepseek_batch(groups_info)
            for r in results:
                gid = r.get("id")
                tipo = r.get("tipo", "desconocido")
                g = id_to_group.get(gid)
                if not g:
                    continue

                if tipo == "valor":
                    cnorm = (r.get("concentracion_norm") or "").strip()
                    cval = r.get("concentracion_valor")
                    cunit = (r.get("concentracion_unidad") or "").strip()
                    if cnorm and cval is not None:
                        try:
                            cval = float(cval)
                        except (TypeError, ValueError):
                            cval = None
                        print(
                            f"    AI [{gid}] {g.dci_key[:40]} | {g.grupo_via} → {cnorm}"
                        )
                        if not dry_run:
                            g.concentracion_norm = cnorm
                            g.concentracion_valor = cval
                            g.concentracion_unidad = cunit if cunit in VALID_UNITS else None
                        fixed += 1
                    else:
                        # AI gave "valor" type but no valid norm → SIN_CONCENTRACION
                        still_null.append(gid)

                elif tipo == "SIN_CONCENTRACION":
                    print(
                        f"    SIN  [{gid}] {g.dci_key[:40]} | {g.grupo_via}"
                    )
                    if not dry_run:
                        g.concentracion_norm = "SIN_CONCENTRACION"
                        g.concentracion_valor = None
                        g.concentracion_unidad = None
                    fixed += 1

                else:  # desconocido → defer to phase 3
                    still_null.append(gid)

        except Exception as exc:
            print(f"  [ERROR] Batch {batch_num}: {exc}")
            for g in batch:
                still_null.append(g.id)

    if not dry_run:
        db.flush()

    print(f"\n  Fase 2 procesados: {fixed} | Siguen NULL: {len(still_null)}")
    return still_null


# ── Phase 3: Mark remaining as SIN_CONCENTRACION ─────────────────────────────

def phase3_sin_concentracion(db, still_null_ids: list[int], dry_run: bool) -> int:
    print(f"\n=== FASE 3: {len(still_null_ids)} grupos residuales → SIN_CONCENTRACION ===")

    if not still_null_ids:
        return 0

    groups = db.query(GrupoEquivalencia).filter(
        GrupoEquivalencia.id.in_(still_null_ids)
    ).all()

    for g in groups:
        print(f"  SIN  [{g.id}] {g.dci_key[:50]} | {g.grupo_via}")
        if not dry_run:
            g.concentracion_norm = "SIN_CONCENTRACION"
            g.concentracion_valor = None
            g.concentracion_unidad = None

    if not dry_run:
        db.flush()

    return len(groups)


# ── Phase 4: Merge duplicates ─────────────────────────────────────────────────

def phase4_merge_duplicates(db, dry_run: bool) -> int:
    print("\n=== FASE 4: Merge de duplicados (dci_key, grupo_via, concentracion_norm) ===")

    dupes = db.execute(text("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as n
        FROM grupos_equivalencia
        WHERE concentracion_norm IS NOT NULL
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING COUNT(*) > 1
        ORDER BY n DESC
    """)).fetchall()

    print(f"  Triples duplicadas: {len(dupes)}")
    merged = 0

    for dci_key, grupo_via, conc_norm, n in dupes:
        groups = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.dci_key == dci_key,
            GrupoEquivalencia.grupo_via == grupo_via,
            GrupoEquivalencia.concentracion_norm == conc_norm,
        ).all()

        if len(groups) <= 1:
            continue

        groups.sort(key=lambda x: x.n_productos, reverse=True)
        target = groups[0]
        seen = set(target.cum_ids or [])
        combined = list(target.cum_ids or [])

        for g in groups[1:]:
            for cid in (g.cum_ids or []):
                if cid not in seen:
                    seen.add(cid)
                    combined.append(cid)
            if not dry_run:
                db.delete(g)
            merged += 1

        if not dry_run:
            target.cum_ids = combined
            target.n_productos = len(combined)

        print(
            f"  MERGE {n} grupos: {dci_key[:35]} | {grupo_via} | {conc_norm}"
        )

    if not dry_run:
        db.flush()

    print(f"  Grupos eliminados en merge: {merged}")
    return merged


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-ai", action="store_true", help="Skip DeepSeek phase")
    parser.add_argument("--phase", type=int, default=0, help="Run only phase N (0=all)")
    args = parser.parse_args()

    if not args.skip_ai and not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY no encontrada. Usa --skip-ai para omitir la IA.")
        sys.exit(1)

    db = SessionLocal()
    try:
        print("=" * 65)
        print(
            "FIX NULL CONC v3"
            + (" [DRY-RUN]" if args.dry_run else " [GUARDANDO]")
            + (" [SKIP-AI]" if args.skip_ai else "")
        )
        print("=" * 65)

        initial_null = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.concentracion_norm == None
        ).count()
        print(f"NULL concentraciones al inicio: {initial_null}")

        run_all = args.phase == 0

        # Phase 1
        if run_all or args.phase == 1:
            still_null = phase1_rule_based(db, args.dry_run)
        else:
            still_null = [
                g.id for g in db.query(GrupoEquivalencia).filter(
                    GrupoEquivalencia.concentracion_norm == None
                ).all()
            ]

        # Phase 2
        if (run_all or args.phase == 2) and not args.skip_ai:
            still_null = phase2_deepseek(db, still_null, args.dry_run)
        elif args.skip_ai:
            print("\n  [SKIP-AI] Saltando fase 2")

        # Phase 3
        if run_all or args.phase == 3:
            phase3_sin_concentracion(db, still_null, args.dry_run)

        # Phase 4
        if run_all or args.phase == 4:
            phase4_merge_duplicates(db, args.dry_run)

        if not args.dry_run:
            db.commit()
            print("\n=== GUARDADO EXITOSO ===")
        else:
            db.rollback()
            print("\n=== DRY-RUN completado — sin cambios guardados ===")

        # Final stats
        final_null = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.concentracion_norm == None
        ).count()
        sin_conc = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.concentracion_norm == "SIN_CONCENTRACION"
        ).count()
        total = db.query(GrupoEquivalencia).count()

        print(f"\nEstado final:")
        print(f"  Total grupos:          {total}")
        print(f"  NULL concentracion:    {final_null}")
        print(f"  SIN_CONCENTRACION:     {sin_conc}")
        print(f"  Con concentracion:     {total - final_null - sin_conc}")

    except Exception as exc:
        db.rollback()
        print(f"\nERROR: {exc}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
