#!/usr/bin/env python
"""
Pipeline autónomo de estandarización CUM.

Por cada molécula:
  1. Descarga TODOS los productos activos del Socrata
  2. Corre el pipeline de transformación
  3. Agrupa por (DCI, forma_farmacéutica)
  4. Detecta productos que deberían ser homólogos pero tienen dosis_numerica distinta
  5. Envía SOLO los dudosos a DeepSeek con sus datos crudos de Socrata
  6. DeepSeek clasifica el error y propone el fix tipificado
  7. Si --fix: aplica las correcciones directamente en transformacion.py
  8. Re-verifica: vuelve a correr el pipeline y confirma que quedó bien

Uso:
    python auto_estandarizar.py --key sk-xxx --dci ACICLOVIR AMOXICILINA
    python auto_estandarizar.py --key sk-xxx --dci ACICLOVIR --fix
    python auto_estandarizar.py --key sk-xxx --todos          # todos los grupos predefinidos
"""
import argparse
import asyncio
import importlib
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass

import httpx
import pandas as pd
from openai import OpenAI

sys.path.insert(0, os.path.dirname(__file__))
import etl.transformacion as _trans_mod
from etl.transformacion import (
    MedicamentoTransformado,
    agrupar_y_transformar,
    _grupo_forma,
    _GRUPOS_NORM_ML,
)

SOCRATA_URL   = "https://www.datos.gov.co/resource/i7cb-raxc.json"
TRANSFORMACION_PATH = os.path.join(os.path.dirname(__file__), "etl", "transformacion.py")
DEEPSEEK_BASE  = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
HTTP_TIMEOUT   = 25.0

# DCIs predefinidos para --todos, con sinónimo de búsqueda en Socrata
GRUPOS_DEFAULT: list[tuple[str, str]] = [
    ("ACICLOVIR",      "ACICLOVIR"),
    ("PARACETAMOL",    "ACETAMINOFEN"),
    ("AMOXICILINA",    "AMOXICILINA"),
    ("METFORMINA",     "METFORMINA"),
    ("CIPROFLOXACINO", "CIPROFLOXACINO"),
    ("MIDAZOLAM",      "MIDAZOLAM"),
    ("VANCOMICINA",    "VANCOMICINA"),
    ("SALBUTAMOL",     "SALBUTAMOL"),
    ("METAMIZOL",      "DIPIRONA"),
    ("NIFEDIPINO",     "NIFEDIPINA"),
    ("AMOXICILINA",    "AMOXICILINA"),
    ("IBUPROFENO",     "IBUPROFENO"),
    ("OMEPRAZOL",      "OMEPRAZOL"),
    ("LOSARTAN",       "LOSARTAN"),
    ("INSULINA",       "INSULINA"),
]

# Factores de conversión a mg-equiv para comparar dosis "esperada" desde raw
_RAW_UNIT_TO_MG: dict[str, float] = {
    "mg": 1.0, "g": 1000.0, "gr": 1000.0,
    "mcg": 0.001, "µg": 0.001, "ug": 0.001,
}

# Grupos de forma donde la dosis_numerica DEBE coincidir con la masa cruda (no se divide por volumen)
_GRUPOS_MASA_DIRECTA = frozenset({
    "SOLIDO_ORAL", "SOLIDO_ORAL_LP", "ORAL_DISPERSABLE",
    "SUBLINGUAL", "TOPICO", "VAGINAL", "RECTAL", "TRANSDERMICO", "OTICO", "NASAL",
})


# ─── Modelos de datos ────────────────────────────────────────────────────────

@dataclass
class Inconsistencia:
    forma_grupo: str
    expected_mg: float
    productos: list[tuple[MedicamentoTransformado, dict]]  # (med, raw_dict)
    descripcion: str


@dataclass
class Fix:
    tipo: str          # SINONIMO | POLVO_KEYWORD | UNIDAD_ALIAS | MANUAL
    datos: dict        # {"de": "X", "a": "Y"} | {"kw": "X"} | {"unidad": "X", "factor": 1.0}
    cum_ids: list[str]
    explicacion: str


# ─── Socrata ──────────────────────────────────────────────────────────────────

async def fetch_termino(termino: str, limit: int = 300) -> list[dict]:
    params = {
        "$where": (
            f"(upper(producto) like '%{termino}%' OR upper(principioactivo) like '%{termino}%')"
            " AND estadocum='Activo'"
        ),
        "$limit": limit, "$order": "producto ASC",
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
        r = await c.get(SOCRATA_URL, params=params)
        r.raise_for_status()
        filas = r.json()

    # Completar filas de expedientes (para combinados)
    expedientes = list({f["expedientecum"] for f in filas if f.get("expedientecum")})
    extra: list[dict] = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
        for i in range(0, len(expedientes), 50):
            lote = expedientes[i:i+50]
            ids  = ", ".join(f"'{e}'" for e in lote)
            r = await c.get(SOCRATA_URL, params={"$where": f"expedientecum IN ({ids})", "$limit": 2000})
            r.raise_for_status()
            extra.extend(r.json())

    dedup = {
        (f["expedientecum"], f.get("consecutivocum",""), f.get("principioactivo","")): f
        for f in filas + extra
    }
    return list(dedup.values())


# ─── Detección de inconsistencias ───────────────────────────────────────────

def _expected_mg(raw: dict) -> float | None:
    """Masa esperada en mg desde los campos crudos (sin dividir por volumen)."""
    try:
        qty = float(str(raw.get("cantidad", "")).replace(",", "."))
    except (ValueError, TypeError):
        return None
    unidad = (str(raw.get("unidadmedida", "")).strip()
              or str(raw.get("unidad", "")).strip()).lower()
    factor = _RAW_UNIT_TO_MG.get(unidad)
    return round(qty * factor, 6) if factor is not None else None


def detectar(
    meds: list[MedicamentoTransformado],
    raw_idx: dict[str, dict],
) -> list[Inconsistencia]:
    """
    Agrupa productos por (dci, forma_grupo).
    Dentro de cada grupo, busca productos con la misma masa cruda esperada
    pero diferente dosis_numerica en el pipeline → son homólogos mal normalizados.
    """
    inconsistencias: list[Inconsistencia] = []

    # Agrupar por (dci_tuple, forma_grupo)
    por_forma: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)
    for m in meds:
        if not m.principios_dci:
            continue
        dci_key   = tuple(sorted(m.principios_dci))
        forma_grp = _grupo_forma(m.forma_farmaceutica, m.via_administracion)

        # Solo analizamos grupos donde dosis_numerica debe igual masa cruda
        es_polvo_iny = (
            forma_grp == "INYECTABLE"
            and any(kw in m.forma_farmaceutica.upper() for kw in ("POLVO", "LIOFILIZADO"))
        )
        if forma_grp not in _GRUPOS_MASA_DIRECTA and not es_polvo_iny:
            continue

        por_forma[(dci_key, forma_grp)].append(m)

    for (dci_key, forma_grp), grupo in por_forma.items():
        # Bucket por expected_mg redondeado → productos que deberían ser homólogos
        buckets: dict[float, list[tuple[MedicamentoTransformado, dict]]] = defaultdict(list)
        for m in grupo:
            raw = raw_idx.get(m.cum_id, {})
            exp = _expected_mg(raw)
            if exp is None or exp <= 0:
                continue
            buckets[round(exp, 1)].append((m, raw))

        for exp_mg, pares in buckets.items():
            # Ignorar singleton sin dosis — no hay nada que comparar
            dosis_vals = {round(p[0].dosis_numerica, 3)
                          for p in pares if p[0].dosis_numerica is not None}

            # Caso 1: múltiples dosis_numerica para la misma masa esperada
            if len(dosis_vals) > 1:
                inconsistencias.append(Inconsistencia(
                    forma_grupo=forma_grp,
                    expected_mg=exp_mg,
                    productos=pares,
                    descripcion=(
                        f"Homólogos con masa_esperada={exp_mg}mg tienen "
                        f"dosis_numerica distintos: {sorted(dosis_vals)}"
                    ),
                ))
            # Caso 2: dosis_numerica consistente pero distinto de masa esperada
            elif len(dosis_vals) == 1:
                actual = list(dosis_vals)[0]
                if abs(actual - exp_mg) / max(exp_mg, 0.001) > 0.02:  # >2% diff
                    inconsistencias.append(Inconsistencia(
                        forma_grupo=forma_grp,
                        expected_mg=exp_mg,
                        productos=pares,
                        descripcion=(
                            f"dosis_numerica={actual} pero masa_cruda_esperada={exp_mg}mg"
                        ),
                    ))
            # Caso 3: dosis_numerica es None cuando esperábamos valor
            elif len(dosis_vals) == 0 and len(pares) > 0:
                inconsistencias.append(Inconsistencia(
                    forma_grupo=forma_grp,
                    expected_mg=exp_mg,
                    productos=pares,
                    descripcion=f"dosis_numerica=None pero masa_cruda_esperada={exp_mg}mg",
                ))

    return inconsistencias


# ─── DeepSeek diagnóstico ────────────────────────────────────────────────────

DIAGNOSE_SYSTEM = """\
Eres farmacólogo experto en CUM colombiano. Recibes un grupo de productos con la MISMA molécula
y forma farmacéutica, donde el pipeline de normalización produjo valores inconsistentes.

Tu tarea: identificar QUÉ está fallando en la normalización y qué tipo de corrección necesita.

TIPOS DE FIX DISPONIBLES:
- SINONIMO: el campo principioactivo_raw usa un nombre no canónico no registrado en el diccionario.
  fix_datos: {"de": "NOMBRE_RAW", "a": "NOMBRE_CANONICO_OMS"}
- POLVO_KEYWORD: la forma farmacéutica indica reconstitución pero la palabra clave no está detectada.
  fix_datos: {"kw": "PALABRA_CLAVE_A_AGREGAR"}
- UNIDAD_ALIAS: la unidad de medida usa un alias no reconocido (ej. "GR" en vez de "g").
  fix_datos: {"unidad": "ALIAS", "factor": 1.0}
- CORRECTO: el pipeline está bien, la inconsistencia es por variación legítima (distinto producto real).
- MANUAL: error complejo que requiere revisión humana (datos Socrata incorrectos, regex nuevo, etc.).

Devuelve JSON exacto:
{
  "veredicto": "INCONSISTENCIA_REAL" | "VARIACION_LEGITIMA",
  "fixes": [
    {
      "tipo": "SINONIMO" | "POLVO_KEYWORD" | "UNIDAD_ALIAS" | "MANUAL",
      "cum_ids_afectados": ["expediente-consecutivo", ...],
      "fix_datos": { ... },
      "concentracion_correcta": "250 mg",
      "dosis_correcta_mg": 250.0,
      "explicacion": "..."
    }
  ],
  "resumen": "..."
}
Si es VARIACION_LEGITIMA, fixes = [].
"""


def diagnosticar(client: OpenAI, dci: str, incons: list[Inconsistencia]) -> list[Fix]:
    """Envía los grupos dudosos a DeepSeek y retorna fixes tipificados."""
    payload_items = []
    for inc in incons:
        for m, raw in inc.productos:
            payload_items.append({
                "cum_id":                m.cum_id,
                "nombre_comercial":      m.nombre_comercial,
                "principios_dci":        m.principios_dci,
                "concentracion_display": m.concentracion_display,
                "dosis_numerica":        m.dosis_numerica,
                "forma_farmaceutica":    m.forma_farmaceutica,
                "forma_grupo":           inc.forma_grupo,
                "masa_esperada_mg":      inc.expected_mg,
                "inconsistencia":        inc.descripcion,
                # Datos crudos Socrata
                "raw_principioactivo":   raw.get("principioactivo", ""),
                "raw_cantidad":          raw.get("cantidad", ""),
                "raw_unidad":            raw.get("unidadmedida") or raw.get("unidad", ""),
                "raw_unidadreferencia":  raw.get("unidadreferencia", ""),
                "raw_forma":             raw.get("formafarmaceutica", ""),
            })

    if not payload_items:
        return []

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": DIAGNOSE_SYSTEM},
            {"role": "user",   "content": json.dumps({"dci": dci, "dudosos": payload_items}, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4096,
    )
    raw_out = json.loads(resp.choices[0].message.content)

    if raw_out.get("veredicto") == "VARIACION_LEGITIMA":
        return []

    fixes: list[Fix] = []
    for f in raw_out.get("fixes", []):
        tipo = f.get("tipo", "MANUAL")
        if tipo in ("SINONIMO", "POLVO_KEYWORD", "UNIDAD_ALIAS", "MANUAL"):
            fixes.append(Fix(
                tipo=tipo,
                datos=f.get("fix_datos", {}),
                cum_ids=f.get("cum_ids_afectados", []),
                explicacion=f.get("explicacion", ""),
            ))
    return fixes


# ─── Aplicar fixes a transformacion.py ────────────────────────────────────────

def _leer_transformacion() -> str:
    with open(TRANSFORMACION_PATH, encoding="utf-8") as f:
        return f.read()


def _escribir_transformacion(src: str) -> None:
    with open(TRANSFORMACION_PATH, "w", encoding="utf-8") as f:
        f.write(src)


def aplicar_sinonimo(de: str, a: str) -> bool:
    """Agrega 'de' → 'a' al dict _SINONIMOS. Retorna True si se aplicó."""
    src = _leer_transformacion()
    de_upper = de.strip().upper()
    a_upper  = a.strip().upper()

    # No duplicar si ya existe
    if f'"{de_upper}"' in src and f'"{a_upper}"' in src:
        # Check if the exact mapping is already there
        if re.search(rf'"{re.escape(de_upper)}"\s*:\s*"{re.escape(a_upper)}"', src):
            return False

    # Insertar antes de la línea que cierra _SINONIMOS (línea con solo "}")
    # Busca el patrón: la llave de cierre del dict _SINONIMOS seguida de 2 newlines
    pattern = r'(_SINONIMOS: dict\[str, str\] = \{.*?)(^\})'
    match = re.search(pattern, src, re.DOTALL | re.MULTILINE)
    if not match:
        return False

    insertion = f'    "{de_upper}":       "{a_upper}",\n'
    new_src = src[:match.start(2)] + insertion + src[match.start(2):]
    _escribir_transformacion(new_src)
    return True


def aplicar_polvo_keyword(kw: str) -> bool:
    """Agrega una keyword a _FORMAS_POLVO. Retorna True si se aplicó."""
    src = _leer_transformacion()
    kw_upper = kw.strip().upper()
    if f'"{kw_upper}"' in src:
        return False
    new_src = src.replace(
        '_FORMAS_POLVO = ("POLVO", "LIOFILIZADO")',
        f'_FORMAS_POLVO = ("POLVO", "LIOFILIZADO", "{kw_upper}")',
    )
    if new_src == src:
        return False
    _escribir_transformacion(new_src)
    return True


def aplicar_unidad_alias(unidad: str, factor: float) -> bool:
    """Agrega alias de unidad a _UNIT_TO_MG. Retorna True si se aplicó."""
    src = _leer_transformacion()
    u_lower = unidad.strip().lower()
    if f'"{u_lower}"' in src:
        return False
    # Insertar antes del cierre del dict _UNIT_TO_MG
    pattern = r'(_UNIT_TO_MG: dict\[str, float\] = \{.*?)(^\})'
    match = re.search(pattern, src, re.DOTALL | re.MULTILINE)
    if not match:
        return False
    insertion = f'    "{u_lower}": {factor},\n'
    new_src = src[:match.start(2)] + insertion + src[match.start(2):]
    _escribir_transformacion(new_src)
    return True


def recargar_pipeline():
    """Recarga transformacion.py en memoria después de editar."""
    importlib.reload(_trans_mod)


# ─── Verificación post-fix ───────────────────────────────────────────────────

def verificar(
    filas: list[dict],
    inconsistencias_originales: list[Inconsistencia],
) -> tuple[int, int]:
    """Recorre el pipeline con el módulo recargado y cuenta cuántas inconsistencias persisten."""
    df = pd.DataFrame(filas)
    meds = agrupar_y_transformar(df)
    raw_idx = {
        f"{r['expedientecum']}-{r.get('consecutivocum','')}": r
        for r in filas
    }
    nuevas = detectar(meds, raw_idx)
    orig_count = len(inconsistencias_originales)
    new_count  = len(nuevas)
    return orig_count, new_count


# ─── Loop principal ──────────────────────────────────────────────────────────

async def procesar_dci(
    dci: str,
    termino: str,
    client: OpenAI | None,
    aplicar_fixes: bool,
    verbose: bool,
) -> dict:
    print(f"\n{'─'*60}")
    print(f"  DCI: {dci}  (búsqueda: '{termino}')")
    print(f"{'─'*60}")

    # 1. Descargar
    print("  [1/4] Descargando del Socrata…", end=" ", flush=True)
    try:
        filas = await fetch_termino(termino)
    except Exception as e:
        print(f"ERROR: {e}")
        return {"dci": dci, "status": "ERROR_FETCH", "error": str(e)}

    df = pd.DataFrame(filas)
    if df.empty:
        print("sin datos")
        return {"dci": dci, "status": "SIN_DATOS"}
    print(f"{len(filas)} filas → ", end="")

    # 2. Pipeline
    meds = agrupar_y_transformar(df)
    print(f"{len(meds)} productos")

    raw_idx: dict[str, dict] = {}
    for _, grp in df.groupby(["expedientecum", "consecutivocum"], sort=False):
        primera = grp.iloc[0].to_dict()
        cid = f"{primera['expedientecum']}-{primera.get('consecutivocum','')}"
        raw_idx[cid] = primera

    # 3. Detectar inconsistencias
    print("  [2/4] Detectando inconsistencias…", end=" ", flush=True)
    incons = detectar(meds, raw_idx)

    if not incons:
        print("✓ ninguna detectada")
        return {"dci": dci, "status": "OK", "n_productos": len(meds)}

    print(f"⚠ {len(incons)} grupos dudosos")
    for inc in incons:
        print(f"    • [{inc.forma_grupo}] {inc.descripcion}")
        if verbose:
            for m, _ in inc.productos:
                print(f"      · {m.cum_id}  conc={m.concentracion_display}  dosis={m.dosis_numerica}  raw={raw_idx.get(m.cum_id,{}).get('cantidad','')} {raw_idx.get(m.cum_id,{}).get('unidadmedida','')}")

    if client is None:
        return {"dci": dci, "status": "INCONSISTENCIAS_SIN_DIAGNOSTICO", "n_incons": len(incons)}

    # 4. Diagnóstico DeepSeek
    print("  [3/4] Diagnóstico DeepSeek…", end=" ", flush=True)
    try:
        fixes = diagnosticar(client, dci, incons)
    except Exception as e:
        print(f"ERROR: {e}")
        return {"dci": dci, "status": "ERROR_DEEPSEEK", "error": str(e)}

    if not fixes:
        print("→ variación legítima, sin correcciones necesarias")
        return {"dci": dci, "status": "VARIACION_LEGITIMA", "n_incons": len(incons)}

    print(f"→ {len(fixes)} fix(es) sugeridos")
    for fix in fixes:
        print(f"    • [{fix.tipo}] {fix.datos}  —  {fix.explicacion[:80]}")

    # 5. Aplicar
    aplicados: list[str] = []
    manuales:  list[str] = []

    if aplicar_fixes:
        print("  [4/4] Aplicando fixes…", end=" ", flush=True)
        for fix in fixes:
            ok = False
            if fix.tipo == "SINONIMO":
                ok = aplicar_sinonimo(fix.datos.get("de",""), fix.datos.get("a",""))
            elif fix.tipo == "POLVO_KEYWORD":
                ok = aplicar_polvo_keyword(fix.datos.get("kw",""))
            elif fix.tipo == "UNIDAD_ALIAS":
                ok = aplicar_unidad_alias(fix.datos.get("unidad",""), float(fix.datos.get("factor", 1.0)))
            if ok:
                aplicados.append(f"{fix.tipo}:{fix.datos}")
            elif fix.tipo == "MANUAL":
                manuales.append(fix.explicacion)

        if aplicados:
            recargar_pipeline()
            orig_n, new_n = verificar(filas, incons)
            resueltos = orig_n - new_n
            print(f"{len(aplicados)} aplicados — inconsistencias: {orig_n}→{new_n} ({resueltos} resueltas)")
        else:
            print("ninguno aplicado")
    else:
        print("  [4/4] Modo diagnóstico (use --fix para aplicar)")
        aplicados = []
        manuales  = [f"{f.tipo}:{f.datos}" for f in fixes if f.tipo == "MANUAL"]

    return {
        "dci": dci, "status": "PROCESADO",
        "n_productos": len(meds),
        "n_incons": len(incons),
        "fixes_sugeridos": [{"tipo": f.tipo, "datos": f.datos, "explicacion": f.explicacion} for f in fixes],
        "fixes_aplicados": aplicados,
        "fixes_manuales": manuales,
    }


async def main_async(args):
    client = None
    if args.key:
        client = OpenAI(api_key=args.key, base_url=DEEPSEEK_BASE)

    if args.todos:
        grupos = GRUPOS_DEFAULT
    else:
        grupos = [(d.upper(), d.upper()) for d in args.dci]

    resultados = []
    for dci, termino in grupos:
        r = await procesar_dci(dci, termino, client, args.fix, args.verbose)
        resultados.append(r)

    # Resumen final
    print(f"\n{'='*60}")
    n_ok    = sum(1 for r in resultados if r["status"] in ("OK", "VARIACION_LEGITIMA"))
    n_fix   = sum(1 for r in resultados if r.get("fixes_aplicados"))
    n_pend  = sum(1 for r in resultados if r.get("fixes_manuales"))
    n_err   = sum(1 for r in resultados if r["status"].startswith("ERROR"))
    print(f"RESUMEN: {n_ok} OK | {n_fix} corregidos | {n_pend} pendientes manual | {n_err} errores")
    print(f"{'='*60}")

    with open("estandarizacion_report.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\nReporte guardado en estandarizacion_report.json")

    if args.fix and n_fix > 0:
        print("\n⚠ transformacion.py fue modificado. Considera hacer commit:")
        print("    git add backend/etl/transformacion.py && git commit -m 'fix: synonyms/units from auto_estandarizar'")


def main():
    p = argparse.ArgumentParser(description="Auto-estandarización CUM con DeepSeek")
    p.add_argument("--key",     default=os.getenv("DEEPSEEK_API_KEY"), help="API key DeepSeek")
    p.add_argument("--dci",     nargs="+", help="DCIs a procesar (ej. ACICLOVIR AMOXICILINA)")
    p.add_argument("--todos",   action="store_true",  help="Procesar todos los DCIs predefinidos")
    p.add_argument("--fix",     action="store_true",  help="Aplicar fixes en transformacion.py")
    p.add_argument("--verbose", action="store_true",  help="Mostrar detalle de cada producto")
    args = p.parse_args()

    if not args.dci and not args.todos:
        p.error("Especifica --dci NOMBRE ... o --todos")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
