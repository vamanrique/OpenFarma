"""
construir_grupos.py
-------------------
Construye la tabla `grupos_equivalencia` a partir de `cum_normalizado`.

Uso:
    python construir_grupos.py [--solo-locales] [--dci NOMBRE] [--fix]

Flags:
    --solo-locales   Salta la clasificacion DeepSeek (solo calculo local)
    --dci NOMBRE     Solo procesa un DCI especifico (util para pruebas)
    --fix            Guarda los grupos en la base de datos (sin este flag es dry-run)

El script lee DEEPSEEK_API_KEY del archivo .env en el mismo directorio.
"""

import os
import sys
import json
import argparse
import httpx
from collections import defaultdict
from datetime import datetime, timezone

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.database import SessionLocal, engine, Base
from app.models.cum_normalizado import CumNormalizado
from app.models.grupo_equivalencia import GrupoEquivalencia
from etl.transformacion import _grupo_forma

# ── Constantes ────────────────────────────────────────────────────────────────
GRUPOS_MASA = {
    "SOLIDO_ORAL", "SOLIDO_ORAL_LP", "ORAL_DISPERSABLE", "SUBLINGUAL",
    "RECTAL", "VAGINAL", "OTICO", "NASAL", "TRANSDERMICO", "INHALADO",
}
GRUPOS_ML = {"LIQUIDO_ORAL", "INYECTABLE"}

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


# ── Helpers ───────────────────────────────────────────────────────────────────

def compute_grupo_via(cum: CumNormalizado) -> str:
    vias = cum.via_normalizada or []
    return _grupo_forma(cum.forma_normalizada or "", vias[0] if vias else "")


def compute_concentracion(cum: CumNormalizado, grupo_via: str) -> tuple:
    """
    Returns (concentracion_norm: str|None, concentracion_valor: float|None,
             concentracion_unidad: str|None)
    """
    # Multi-component: use componentes dosis_mg joined
    componentes = cum.componentes or []
    if len(componentes) > 1:
        dosis = [round(c["dosis_mg"], 1) for c in componentes if c.get("dosis_mg")]
        if dosis:
            label = " + ".join(f"{v:g} mg" for v in dosis)
            return label, dosis[0], "mg"

    if grupo_via in GRUPOS_MASA:
        if cum.dosis_total_mg and cum.dosis_total_mg > 0:
            v = round(cum.dosis_total_mg, 1)
            return f"{v:g} mg", v, "mg"

    if grupo_via in GRUPOS_ML:
        if cum.concentracion_mg_ml and cum.concentracion_mg_ml > 0:
            v = round(cum.concentracion_mg_ml, 3)
            if v == int(v):
                display = f"{int(v)} mg/mL"
            elif v >= 1:
                display = f"{v:.1f} mg/mL"
            else:
                display = f"{v:.3g} mg/mL"
            return display, v, "mg/mL"
        if cum.dosis_total_mg and cum.dosis_total_mg > 0:
            v = round(cum.dosis_total_mg, 1)
            return f"{v:g} mg", v, "mg"

    if grupo_via == "TOPICO":
        if cum.concentracion_mg_ml and cum.concentracion_mg_ml > 0:
            pct = round(cum.concentracion_mg_ml / 10, 2)
            return f"{pct:g}%", pct, "%"
        if cum.dosis_total_mg and cum.dosis_total_mg > 0:
            v = round(cum.dosis_total_mg, 1)
            return f"{v:g} mg", v, "mg"

    if grupo_via == "INHALADO":
        if cum.dosis_total_mg and cum.dosis_total_mg > 0:
            v = round(cum.dosis_total_mg, 3)
            label = f"{v:g} mcg/dosis" if v < 1 else f"{v:g} mg/dosis"
            return label, v, "mg/dosis"
        if cum.concentracion_mg_ml and cum.concentracion_mg_ml > 0:
            v = round(cum.concentracion_mg_ml, 3)
            return f"{v:g} mg/mL", v, "mg/mL"

    return None, None, None


def build_dci_key(cum: CumNormalizado) -> str | None:
    principios = cum.principios_dci or []
    if not principios:
        return None
    return "||".join(sorted(principios))


# ── DeepSeek clasificacion ────────────────────────────────────────────────────

CHUNK_SIZE = 25  # max products per DeepSeek call to avoid JSON truncation

def _clasificar_chunk(dci_key: str, chunk: list[dict], existing_groups: list[dict]) -> list[dict]:
    """Single DeepSeek call for one chunk of products."""
    system_prompt = (
        "Eres un farmaceutico colombiano experto en el registro CUM-INVIMA. "
        "Dado un listado de productos farmaceuticos con datos incompletos de normalizacion, "
        "y los grupos de clasificacion ya existentes para el mismo principio activo, "
        "clasifica cada producto en el grupo mas apropiado (grupo_via + concentracion_norm). "
        "Si un producto es genuinamente unico (no existen otros con esa via/concentracion), "
        "marcalo como singleton. "
        "Los valores validos de grupo_via son: "
        "SOLIDO_ORAL, SOLIDO_ORAL_LP, ORAL_DISPERSABLE, SUBLINGUAL, INYECTABLE, "
        "INHALADO, NASAL, OFTALMICO, OTICO, TOPICO, VAGINAL, RECTAL, TRANSDERMICO, LIQUIDO_ORAL. "
        "Responde SOLO con JSON valido, sin texto adicional."
    )
    user_content = json.dumps({
        "principio_activo": dci_key,
        "productos_a_clasificar": chunk,
        "grupos_existentes": existing_groups,
        "instruccion": (
            "Para cada producto en productos_a_clasificar, determina grupo_via y concentracion_norm. "
            "Devuelve un JSON con la clave 'clasificaciones' conteniendo una lista de objetos con: "
            "cum_id, grupo_via, concentracion_norm, concentracion_valor, concentracion_unidad, "
            "es_singleton (bool), razon (string corto)."
        ),
    }, ensure_ascii=False)

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 4096,
            },
        )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    return parsed.get("clasificaciones", [])


def clasificar_con_deepseek(
    dci_key: str,
    unclassified: list[dict],
    existing_groups: list[dict],
) -> list[dict]:
    """Classifies products in chunks of CHUNK_SIZE to avoid JSON truncation on large DCIs."""
    if not DEEPSEEK_API_KEY:
        print(f"  [WARN] No DEEPSEEK_API_KEY, skipping {dci_key}")
        return []

    results: list[dict] = []
    chunks = [unclassified[i:i+CHUNK_SIZE] for i in range(0, len(unclassified), CHUNK_SIZE)]
    for idx, chunk in enumerate(chunks):
        suffix = f" chunk {idx+1}/{len(chunks)}" if len(chunks) > 1 else ""
        try:
            results.extend(_clasificar_chunk(dci_key, chunk, existing_groups))
        except Exception as exc:
            print(f"  [ERROR] DeepSeek call failed for {dci_key}{suffix}: {exc}")
    return results


# ── Pipeline principal ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Construir grupos de equivalencia farmaceutica")
    parser.add_argument("--solo-locales", action="store_true", help="No usar DeepSeek")
    parser.add_argument("--dci", type=str, default=None, help="Procesar solo este DCI")
    parser.add_argument("--fix", action="store_true", help="Guardar en DB (sin este flag: dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        _run_pipeline(db, args)
    finally:
        db.close()


def _run_pipeline(db, args):
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    print("=" * 60)
    print("CONSTRUIR GRUPOS DE EQUIVALENCIA")
    print("=" * 60)
    if not args.fix:
        print("[DRY-RUN] Usa --fix para guardar en la base de datos")
    print()

    # ── Paso 1: Cargar registros activos ──────────────────────────────────────
    query = db.query(CumNormalizado).filter(
        CumNormalizado.estado_cum.in_(["Activo", "Activo "])
    )
    if args.dci:
        # For JSON columns, load all active records and filter in Python
        dci_upper = args.dci.upper()
        activos = [
            c for c in query.all()
            if any(dci_upper in (p or "").upper() for p in (c.principios_dci or []))
        ]
    else:
        activos = query.all()

    print(f"Registros activos: {len(activos)}")

    # ── Paso 2: Agrupar por (dci_key, grupo_via, concentracion_norm) ─────────
    # groups: {(dci_key, grupo_via, cnorm): [(cum_id, cval, cunit), ...]}
    groups: dict = defaultdict(list)
    orphans: list = []        # no dci_key
    unclassified: dict = defaultdict(list)  # dci_key -> [cum records]

    for cum in activos:
        dci_key = build_dci_key(cum)
        if not dci_key:
            orphans.append(cum)
            continue

        gv = compute_grupo_via(cum)
        cnorm, cval, cunit = compute_concentracion(cum, gv)
        cum_id = f"{cum.expediente_cum}-{cum.consecutivo_cum}"

        if cnorm is None:
            unclassified[dci_key].append({
                "cum": cum,
                "gv": gv,
                "cum_id": cum_id,
            })
        else:
            groups[(dci_key, gv, cnorm)].append((cum_id, cval, cunit))

    print(f"Grupos locales (con concentracion): {len(groups)}")
    print(f"DCIs con productos no clasificados: {len(unclassified)}")
    print(f"Huerfanos (sin DCI): {len(orphans)}")

    # ── Paso 3: Clasificacion con DeepSeek para no clasificados ──────────────
    revisados_ia = 0
    ai_classifications: dict = {}  # cum_id -> {grupo_via, cnorm, cval, cunit}

    if not args.solo_locales and unclassified:
        print()
        print(f"Clasificando {sum(len(v) for v in unclassified.values())} productos con DeepSeek...")
        for dci_k, items in unclassified.items():
            if args.dci and args.dci.upper() not in dci_k.upper():
                continue

            # Build context: existing groups for this DCI
            existing = [
                {
                    "grupo_via": gv,
                    "concentracion_norm": cnorm,
                    "n_productos": len(prods),
                }
                for (dk, gv, cnorm), prods in groups.items()
                if dk == dci_k
            ]

            to_classify = [
                {
                    "cum_id": item["cum_id"],
                    "nombre_comercial_norm": item["cum"].nombre_comercial_norm or "",
                    "forma_normalizada": item["cum"].forma_normalizada or "",
                    "via_normalizada": item["cum"].via_normalizada or [],
                    "tipo_formula": item["cum"].tipo_formula or "",
                    "grupo_via_inferido": item["gv"],
                    "notas": (item["cum"].notas or "")[:200],
                }
                for item in items
            ]

            print(f"  DCI: {dci_k} ({len(to_classify)} productos)...")
            clasificaciones = clasificar_con_deepseek(dci_k, to_classify, existing)

            for cl in clasificaciones:
                cum_id = cl.get("cum_id", "")
                if not cum_id:
                    continue
                raw_cval = cl.get("concentracion_valor")
                try:
                    cval_parsed = float(raw_cval) if raw_cval is not None else None
                except (TypeError, ValueError):
                    cval_parsed = None
                ai_classifications[cum_id] = {
                    "grupo_via": cl.get("grupo_via", ""),
                    "cnorm": cl.get("concentracion_norm"),
                    "cval": cval_parsed,
                    "cunit": cl.get("concentracion_unidad"),
                    "es_singleton": cl.get("es_singleton", False),
                }
                revisados_ia += 1

        # Merge AI classifications into groups
        for dci_k, items in unclassified.items():
            for item in items:
                cum_id = item["cum_id"]
                cl = ai_classifications.get(cum_id)
                if cl and cl["grupo_via"] and not cl["es_singleton"]:
                    gv = cl["grupo_via"]
                    cnorm = cl["cnorm"]
                    cval = cl["cval"]
                    cunit = cl["cunit"]
                    groups[(dci_k, gv, cnorm)].append((cum_id, cval, cunit))
                else:
                    # Keep in unclassified group with None concentration
                    gv = item["gv"]
                    groups[(dci_k, gv, None)].append((cum_id, None, None))
    else:
        # Without DeepSeek: add unclassified as None-concentration groups
        for dci_k, items in unclassified.items():
            for item in items:
                cum_id = item["cum_id"]
                gv = item["gv"]
                groups[(dci_k, gv, None)].append((cum_id, None, None))

    total_groups = len(groups)
    dcis_covered = len({dk for (dk, _, _) in groups})
    singletons = sum(1 for prods in groups.values() if len(prods) == 1)
    unclassified_count = sum(
        1 for (_, _, cnorm), _ in groups.items() if cnorm is None
    )

    print()
    print("=" * 60)
    print("ESTADISTICAS")
    print("=" * 60)
    print(f"Total grupos         : {total_groups}")
    print(f"DCIs cubiertos       : {dcis_covered}")
    print(f"Sin concentracion    : {unclassified_count}")
    print(f"Singletons           : {singletons}")
    print(f"Revisados por IA     : {revisados_ia}")
    print(f"Huerfanos (sin DCI)  : {len(orphans)}")
    print()

    if not args.fix:
        print("[DRY-RUN] No se guardaron cambios. Agrega --fix para persistir.")
        return

    # ── Paso 4: Guardar en DB ─────────────────────────────────────────────────
    print("Guardando en base de datos...")

    # Ensure table exists
    Base.metadata.create_all(bind=engine)

    # Clear existing groups (full refresh or partial if --dci)
    if args.dci:
        dci_upper = args.dci.upper()
        deleted = (
            db.query(GrupoEquivalencia)
            .filter(GrupoEquivalencia.dci_key.ilike(f"%{dci_upper}%"))
            .delete(synchronize_session=False)
        )
        print(f"  Eliminados {deleted} grupos existentes para DCI={args.dci}")
    else:
        deleted = db.query(GrupoEquivalencia).delete(synchronize_session=False)
        print(f"  Eliminados {deleted} grupos existentes")

    # Insert new groups
    inserted = 0
    for (dci_k, gv, cnorm), prod_list in groups.items():
        cum_ids = [p[0] for p in prod_list]
        # Representative concentration value and unit (first non-None, must be float)
        cval_raw = next((p[1] for p in prod_list if p[1] is not None), None)
        try:
            cval = float(cval_raw) if cval_raw is not None else None
        except (TypeError, ValueError):
            cval = None
        cunit = next((p[2] for p in prod_list if p[2] is not None), None)

        # Check if any product in this group was AI-reviewed
        any_ai = any(p[0] in ai_classifications for p in prod_list)

        grupo = GrupoEquivalencia(
            dci_key=dci_k,
            grupo_via=gv,
            concentracion_norm=cnorm,
            concentracion_valor=cval,
            concentracion_unidad=cunit,
            cum_ids=cum_ids,
            n_productos=len(cum_ids),
            revisado_ia=any_ai,
            notas=None,
            actualizado_en=now,
        )
        db.add(grupo)
        inserted += 1

        if inserted % 500 == 0:
            db.flush()
            print(f"  ... {inserted} grupos insertados")

    db.commit()
    print(f"Guardados {inserted} grupos en grupos_equivalencia.")
    print("Listo.")


if __name__ == "__main__":
    main()
