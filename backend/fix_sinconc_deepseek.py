"""
Fix final: SIN_CONCENTRACION restantes usando DeepSeek.

Estrategia:
1. Filtra grupos legítimamente SIN_CONCENTRACION (vacunas, biológicos, TPN, gases, agua)
2. Para el resto: reúne datos de cum_normalizado + nombres de productos
3. Opcionalmente consulta Socrata para productos sin datos de concentración
4. Envía a DeepSeek en batch: ¿cuál es la concentracion_norm correcta?
5. Aplica fixes en grupos_equivalencia (y actualiza cum_normalizado si aplica)

Uso:
    python fix_sinconc_deepseek.py --key sk-xxx [--dry-run] [--socrata]
"""
import argparse
import asyncio
import json
import os
import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from collections import defaultdict
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

import httpx
from openai import OpenAI

DB_PATH = "openfarma.db"
SOCRATA_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
HTTP_TIMEOUT = 25.0

# ─── Filtros: grupos legitimamente SIN_CONCENTRACION ─────────────────────────

# Palabras clave en dci_key que indican biológico/vacuna/gas/nutrición parenteral
SKIP_DCI_KEYWORDS = [
    # Vacunas / antígenos
    "VIRUS ", "VIRUS DE", "TOXOIDE", "ANTIGENO", "PROTEINA L1", "POLISACARIDO",
    "BORDETELLA", "CLOSTRIDIUM TETANI", "CORYNEBACTERIUM", "POLIOVIRUS",
    "HEMAGLUTININA", "PERTACTINA", "STREPTOCOCCUS PNEUMONIAE",
    "GLUCOPROTEINA E DEL VIRUS", "OMV||", "RP287",
    # Genes / terapia génica
    "ONASEMNOGEN", "VORETIGEN", "VELMANASA",
    # Factores de coagulación
    "FACTOR VIII", "FACTOR IX", "FACTOR VII DE COAGULACION", "FACTOR II",
    "PROTEINA C||PROTEINA S", "FIBRINOGENO HUMANO", "TROMBINA HUMANA",
    "FIBRINOGENO||", "||FIBRINOGENO", "APROTININA||",
    # Nutrición parenteral (muchos aminoácidos + aceites)
    "L-ALANINA||", "L-ARGININA||", "TRIGLICERIDOS DE CADENA MEDIA",
    "ACEITE DE OLIVA||", "ACEITE DE PESCADO", "ACEITE DE SOYA||",
    "ACIDOS GRASOS OMEGA", "LISINA||",
    # Agua y gases
    "DIOXIDO DE CARBONO", "AGUA ESTERIL PARA INYECCION",
    "OXIDO NITROSO", "HELIO||", "FOSFOLIPIDOS NATURALES",
    # Biológicos varios
    "INTERFERON BETA", "INTERFERON GAMMA", "IMIGLUCERASA", "ASPARAGINASA",
    "FOLITROPINA", "LUTROPINA ALFA", "VELAGLUCERASA", "GALSULFASA",
    "INMUNOGLOBULINA", "VASOPRESINA", "CONESTAT ALFA",
    "INHIBIDOR DE LA ESTERASA C1", "TUBERCULINA",
    "TOXINA DE CLOSTRIDIUM BOTULINUM",
    # Aislados bacterianos / probióticos complejos
    "BACILLUS CLAUSII", "LACTOBACILLUS", "BIFIDOBACTERIUM",
    "LISADOS BACTERIANOS", "LISADO LIOFILIZADO",
    # Radiofármacos
    "IOBENGUANE", "BETIATIDA", "SUCCIMERO", "TECNECIO", "CITRATO DE GALIO",
    "MOLIBDENO 99", "RADIO RA-223", "LUTECIO (177LU)", "ACIDO DIMERCAPTOSUCCINICO",
    "MACROAGREGADOS DE ALBUMINA", "YODURO DE SODIO (131I)", "IODURO SODICO(131I)",
    "IODURO DE SODIO I-131", "YODURO DE SODIO I-131", "UREA C14",
    # Oligosacaridos meningocócicos (vacuna)
    "OLIGOSACARIDO MENINGOCOCICO",
    # Vitaminas parenterales complejas (unidades mixtas)
    "COLECALCIFEROL||RETINOL", "ALFATOCOFEROL||VITAMINA A",
    "VITAMINA A||VITAMINA D", "ACEITE DE HIGADO DE BACALAO",
    "ACEITE DE RICINO",
    # Soluciones ORS / electrolitos orales con composición variable
    "CITRATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO||DEXTROSA",
    "ACIDO CITRICO||CITRATO DE POTASIO", "CITRATO TRISODICO||CLORURO",
    # Suplementos fitoterápicos (dosificación en unidades no estándar)
    "PLANTAGO OVATA", "BOLDO||", "GINKGO BILOBA",
    "GLUCOSAMINA SULFATO||CONDROITINA", "COLAGENO HIDROLIZADO",
    # Enzimas (pancreatina medida en unidades enzimáticas)
    "PANCREATINA",
    # Contrast / radiodiagnóstico
    "SULFATO DE BARIO",
    # Laxantes osmóticos complejos
    "ICODEXTRINA", "POLIETILENGLICOL 3350", "POLIETILENGLICOL 4000",
    # Elementos traza (mezclas de minerales)
    "COBRE||FLUORURO||MANGANESO", "COBRE||CROMO||FLUORURO",
    "COBRE||MANGANESO||SELENIO||YODO||ZINC",
    "BORO||CALCIO||COBRE||COLECALCIFEROL",
    "CALCIO||COBRE||COLECALCIFEROL||MAGNESIO",
    # Calcio/sodio/electrolitos sin DCI farmacológico claro
    "FOSFATO DE POTASIO DIBASICO||FOSFATO DE POTASIO MONOBASICO",
    "FOSFATO DE SODIO DIBASICO||FOSFATO DE SODIO MONOBASICO",
]

# Nombres de productos que indican legítimamente SIN_CONCENTRACION
SKIP_PRODUCT_KEYWORDS = [
    "VACUNA", "VACCINE", "VITALIPID", "SURVANTA", "TISSEEL", "HAEMATE",
    "PROQUAD", "SMOFKABIVEN", "OLIMEL", "NUTRIFLEX", "PERIOLIMEL",
    "OMEGAVEN", "CAPD", "DPCA",
    "EMULSION DE SCOTT",  # Scott's emulsion
    "DOMEBORO",  # astringent compress powder
]

# DCI exactos que son siempre SIN_CONCENTRACION
SKIP_DCI_EXACT = {
    "AGUA", "AGUA ESTERIL PARA INYECCION", "DIOXIDO DE CARBONO",
    "ONASEMNOGEN ABEPARVOVEC", "VORETIGEN NEPARVOVEC", "VELMANASA ALFA",
    "IMIGLUCERASA", "ASPARAGINASA", "GLUCAGON", "HEPARINA",
    "TOXINA BOTULINICA TIPO A", "EPOETINA ALFA",
    "ACIDOS GRASOS LIBRES||FOSFATIDILCOLINA DISATURADA||TRIGLICERIDOS",
    "OMV||RP287-953||RP936-741||RP961C",
    "IOBENGUANE (I 131)", "BETIATIDA", "SUCCIMERO",
    # Gases médicos
    "OXIGENO", "AIRE COMPRIMIDO", "NITROGENO||OXIGENO",
    # Productos con composición variable o no expresable en mg
    "BICARBONATO DE SODIO",  # polvo doméstico, conc n/a
    "PETROLATO BLANCO",      # excipiente puro
    "AGUA",                  # agua estéril
    "PROMESTRIENO",          # crema vaginal de baja dosis, % propietaria
    # Inmunoglobulinas y antivenenos
    "INMUNOGLOBULINA HUMANA ANTICITOMEGALOVIRUS",
    "INMUNOGLOBULINA HUMANA ANTI-D",
    "INMUNOGLOBULINA ANTIVENENO BOTHROPS||INMUNOGLOBULINA ANTIVENENO CROTALUS",
    # Electrolito alcalinizante / laxante osmótico
    "ACIDO ASCORBICO||ASCORBATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO||MACROGOL 3350||SULFATO DE SODIO ANHIDRO",
    "BICARBONATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO||POLIETILENGLICOL 3350||SULFATO DE SODIO ANHIDRO",
    "MAGNESIO SULFATO||POTASIO SULFATO||SODIO SULFATO",
    "ACIDO TARTARICO||BICARBONATO DE SODIO",
    # Electrolitos IV sin DCI farmacológico claro
    "ACETATO DE SODIO||CLORURO DE POTASIO||CLORURO DE SODIO||DEXTROSA",
    "CLORURO DE CALCIO||CLORURO DE POTASIO||CLORURO DE SODIO",
    "CLORURO DE CALCIO||CLORURO DE MAGNESIO||CLORURO DE SODIO||DEXTROSA||LACTATO DE SODIO",
    "ACETATO DE SODIO||ACIDO MALICO||CLORURO DE CALCIO||CLORURO DE MAGNESIO||CLORURO DE POTASIO||CLORURO DE SODIO",
    "CALCIO||POTASIO||SODIO",
}


def is_legitimate_sin_conc(dci_key: str, product_names: list[str]) -> bool:
    """Retorna True si el grupo es legítimamente SIN_CONCENTRACION."""
    dci_up = dci_key.upper()
    if dci_key in SKIP_DCI_EXACT:
        return True
    for kw in SKIP_DCI_KEYWORDS:
        if kw in dci_up:
            return True
    all_names = " ".join(product_names).upper()
    for kw in SKIP_PRODUCT_KEYWORDS:
        if kw in all_names:
            return True
    return False


# ─── Construcción de concentración desde cum_normalizado ─────────────────────

def fmt_mg(val: float) -> str:
    """Formatea un valor en mg, eliminando ceros innecesarios."""
    if val == int(val):
        return f"{int(val)} mg"
    return f"{val:g} mg"


def fmt_pct(mg_per_g: float) -> str:
    """Convierte mg/g a % con formato limpio."""
    pct = mg_per_g / 10.0  # 10 mg/g = 1%
    if pct == int(pct):
        return f"{int(pct)}%"
    return f"{pct:g}%"


def inferir_conc_directa(grupo_via: str, samples: list[dict]) -> str | None:
    """
    Intenta calcular concentracion_norm directamente desde cum_normalizado.
    Retorna la cadena o None si no se puede.
    """
    # Para cada sample, obtener componentes
    comp_sets = []
    for s in samples:
        comps = s.get("componentes", [])
        if not comps:
            continue
        dosis_vals = {}
        conc_vals = {}
        for c in comps:
            dci = c.get("dci", "")
            dosis = c.get("dosis_mg")
            conc = c.get("concentracion_mg_ml")
            if dosis and dosis > 0:
                dosis_vals[dci] = dosis
            if conc and conc > 0:
                conc_vals[dci] = conc
        if dosis_vals or conc_vals:
            comp_sets.append({"dosis": dosis_vals, "conc": conc_vals})

    if not comp_sets:
        return None

    # Usar el primer sample con datos
    first = comp_sets[0]

    if grupo_via in ("SOLIDO_ORAL", "SOLIDO_ORAL_LP", "SUBLINGUAL", "RECTAL", "VAGINAL"):
        # Usar dosis_mg: formato "X mg" o "X mg + Y mg"
        dosis = first.get("dosis", {})
        if dosis:
            parts = [fmt_mg(v) for v in dosis.values()]
            if len(parts) == 1:
                return parts[0]
            return " + ".join(parts)

    elif grupo_via in ("LIQUIDO_ORAL", "INYECTABLE", "OFTALMICO", "NASAL", "OTICO", "INHALADO"):
        # Usar concentracion_mg_ml: formato "X mg/mL" o "X mg/mL + Y mg/mL"
        conc = first.get("conc", {})
        if conc:
            parts = [f"{v:g} mg/mL" for v in conc.values()]
            return " + ".join(parts)
        # Fallback a dosis
        dosis = first.get("dosis", {})
        if dosis:
            parts = [fmt_mg(v) for v in dosis.values()]
            return " + ".join(parts)

    elif grupo_via == "TOPICO":
        # Usar concentracion_mg_ml → convertir a %
        conc = first.get("conc", {})
        if conc:
            parts = [fmt_pct(v) for v in conc.values()]
            return " + ".join(parts)
        # Fallback dosis
        dosis = first.get("dosis", {})
        if dosis and len(dosis) == 1:
            v = list(dosis.values())[0]
            if v > 100:  # probablemente en mg/dosis, no tiene sentido sin unidad de referencia
                return None
            return fmt_mg(v)

    return None


# ─── Consulta a Socrata ───────────────────────────────────────────────────────

async def fetch_expediente(expediente: str) -> list[dict]:
    params = {
        "$where": f"expedientecum='{expediente}' AND estadocum='Activo'",
        "$limit": 100,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
        r = await c.get(SOCRATA_URL, params=params)
        r.raise_for_status()
        return r.json()


async def fetch_socrata_for_group(cum_ids: list[str]) -> list[dict]:
    """Trae los datos crudos de Socrata para un grupo de CUM IDs."""
    expedientes = list({cid.split("-")[0] for cid in cum_ids if "-" in cid})
    results = []
    tasks = [fetch_expediente(exp) for exp in expedientes[:3]]  # max 3 expedientes
    done = await asyncio.gather(*tasks, return_exceptions=True)
    for r in done:
        if isinstance(r, list):
            results.extend(r)
    return results


# ─── DeepSeek: determinar concentracion_norm ─────────────────────────────────

SYSTEM_PROMPT = """\
Eres farmacólogo experto en el CUM colombiano (INVIMA).

Recibes grupos de medicamentos con concentracion_norm='SIN_CONCENTRACION' que posiblemente
deberían tener una concentración específica.

Para cada grupo, determina:
1. Si es LEGITIMO_SIN_CONC: la concentración no aplica (vacuna, biológico, gas, agua, TPN,
   factor de coagulación, radiofármaco, producto con composición variable entre presentaciones)
2. Si tiene CONCENTRACION_FIJA: cuál es la concentracion_norm correcta

REGLAS DE FORMATO concentracion_norm:
- SOLIDO_ORAL/TABLETA/CAPSULA: "X mg" o "X mg + Y mg" (por unidad posológica)
- LIQUIDO_ORAL/SOLUCION: "X mg/mL" (concentración en solución)
- INYECTABLE polvo/liofilizado: "X mg" (masa por vial, NO mg/mL)
- INYECTABLE solución ya preparada: "X mg/mL"
- TOPICO (cremas, ungüentos): "X%" (porcentaje)
- OFTALMICO: "X mg/mL"
- OTICO: "X mg/mL"
- INHALADO aerosol: "X mcg/dosis"
- Para multicomponentes: "X mg + Y mg" en orden dado por los componentes

Devuelve JSON exacto:
{
  "grupos": [
    {
      "id": 123,
      "dci_key": "...",
      "decision": "LEGITIMO_SIN_CONC" | "TIENE_CONCENTRACION",
      "concentracion_norm": "600 mg",  // null si LEGITIMO_SIN_CONC
      "razon": "breve explicacion"
    }
  ]
}
"""


def batch_deepseek(client: OpenAI, grupos_payload: list[dict]) -> list[dict]:
    """Envía un batch de grupos a DeepSeek y retorna las decisiones."""
    payload = json.dumps({"grupos": grupos_payload}, ensure_ascii=False)
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4096,
    )
    out = json.loads(resp.choices[0].message.content)
    return out.get("grupos", [])


# ─── Aplicar fixes ────────────────────────────────────────────────────────────

def apply_fix(cur: sqlite3.Cursor, grupo_id: int, concentracion_norm: str, dry_run: bool) -> None:
    if dry_run:
        print(f"    [DRY-RUN] UPDATE grupos_equivalencia SET concentracion_norm='{concentracion_norm}' WHERE id={grupo_id}")
        return
    cur.execute(
        "UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?",
        (concentracion_norm, grupo_id),
    )


# ─── Pipeline principal ───────────────────────────────────────────────────────

def load_sin_conc_groups(con: sqlite3.Connection) -> list[dict]:
    """Carga todos los grupos SIN_CONCENTRACION con sus datos de cum_normalizado."""
    cur = con.cursor()
    cur.execute("""
        SELECT id, dci_key, grupo_via, n_productos, cum_ids
        FROM grupos_equivalencia
        WHERE concentracion_norm='SIN_CONCENTRACION'
        ORDER BY grupo_via, n_productos DESC
    """)
    grupos = cur.fetchall()
    result = []
    for gid, dci_key, grupo_via, n_prod, cum_ids_str in grupos:
        cum_ids = json.loads(cum_ids_str or "[]")
        # Obtener datos de cum_normalizado
        samples = []
        product_names = []
        for cid in cum_ids[:4]:  # max 4 samples
            parts = cid.split("-", 1)
            if len(parts) != 2:
                continue
            cur.execute("""
                SELECT nombre_comercial_norm, dosis_total_mg, concentracion_mg_ml, componentes, forma_normalizada
                FROM cum_normalizado
                WHERE expediente_cum=? AND consecutivo_cum=?
            """, (parts[0], parts[1]))
            row = cur.fetchone()
            if row:
                name = row[0] or ""
                if name and name not in product_names:
                    product_names.append(name)
                comps = json.loads(row[3]) if row[3] else []
                samples.append({
                    "cum_id": cid,
                    "nombre": name,
                    "dosis_total_mg": row[1],
                    "concentracion_mg_ml": row[2],
                    "componentes": comps,
                    "forma": row[4],
                })
        result.append({
            "id": gid,
            "dci_key": dci_key,
            "grupo_via": grupo_via,
            "n_productos": n_prod,
            "cum_ids": cum_ids,
            "product_names": product_names,
            "samples": samples,
        })
    return result


async def main_async(args):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    client = OpenAI(api_key=args.key, base_url=DEEPSEEK_BASE) if args.key else None

    print("Cargando grupos SIN_CONCENTRACION...")
    grupos = load_sin_conc_groups(con)
    print(f"  Total: {len(grupos)} grupos")

    # ── Paso 1: filtrar legítimos ────────────────────────────────────────────
    a_procesar = []
    skipped_legit = []
    for g in grupos:
        if is_legitimate_sin_conc(g["dci_key"], g["product_names"]):
            skipped_legit.append(g)
        else:
            a_procesar.append(g)

    print(f"  Legítimos (skip): {len(skipped_legit)}")
    print(f"  A procesar: {len(a_procesar)}")

    # ── Paso 2: inferencia directa desde DB ─────────────────────────────────
    fixes_directos = {}
    pendientes = []
    for g in a_procesar:
        conc = inferir_conc_directa(g["grupo_via"], g["samples"])
        if conc:
            fixes_directos[g["id"]] = (g, conc)
        else:
            pendientes.append(g)

    print(f"\n[Paso 2] Inferencia directa: {len(fixes_directos)} grupos")
    for gid, (g, conc) in fixes_directos.items():
        print(f"  id={gid} [{g['grupo_via']}] {g['dci_key']} → '{conc}'")

    # ── Paso 3: fetch Socrata para grupos sin datos ─────────────────────────
    if args.socrata and pendientes:
        print(f"\n[Paso 3] Fetching Socrata para {len(pendientes)} grupos...")
        for g in pendientes:
            print(f"  Fetching {g['dci_key']}...", end=" ", flush=True)
            try:
                filas = await fetch_socrata_for_group(g["cum_ids"])
                # Añadir datos crudos de Socrata a los samples
                raw_by_consec = {}
                for row in filas:
                    key = f"{row.get('expedientecum', '')}-{row.get('consecutivocum', '')}"
                    raw_by_consec[key] = row
                socrata_samples = []
                for cid in g["cum_ids"][:3]:
                    raw = raw_by_consec.get(cid, {})
                    if raw:
                        socrata_samples.append({
                            "cum_id": cid,
                            "producto": raw.get("producto", ""),
                            "principioactivo": raw.get("principioactivo", ""),
                            "cantidad": raw.get("cantidad", ""),
                            "unidadmedida": raw.get("unidadmedida", "") or raw.get("unidad", ""),
                            "unidadreferencia": raw.get("unidadreferencia", ""),
                            "formafarmaceutica": raw.get("formafarmaceutica", ""),
                        })
                g["socrata_samples"] = socrata_samples
                print(f"{len(filas)} filas")
            except Exception as e:
                print(f"ERROR: {e}")
                g["socrata_samples"] = []

    # ── Paso 4: DeepSeek batch ───────────────────────────────────────────────
    fixes_deepseek = {}
    still_unknown = []

    if pendientes and client:
        print(f"\n[Paso 4] DeepSeek para {len(pendientes)} grupos...")

        # Construir payload
        batch = []
        for g in pendientes:
            item = {
                "id": g["id"],
                "dci_key": g["dci_key"],
                "grupo_via": g["grupo_via"],
                "n_productos": g["n_productos"],
                "nombres_comerciales": g["product_names"][:3],
                "samples": [
                    {
                        "cum_id": s["cum_id"],
                        "nombre": s["nombre"],
                        "dosis_total_mg": s["dosis_total_mg"],
                        "forma": s["forma"],
                        "componentes": [
                            {"dci": c.get("dci"), "dosis_mg": c.get("dosis_mg"), "conc_mg_ml": c.get("concentracion_mg_ml")}
                            for c in s["componentes"][:5]
                        ],
                    }
                    for s in g["samples"][:2]
                ],
            }
            if "socrata_samples" in g and g["socrata_samples"]:
                item["socrata_raw"] = g["socrata_samples"][:2]
            batch.append(item)

        # Enviar en lotes de 15 grupos (para no exceder el contexto de DeepSeek)
        BATCH_SIZE = 15
        all_decisions = []
        for i in range(0, len(batch), BATCH_SIZE):
            lote = batch[i:i + BATCH_SIZE]
            print(f"  Lote {i // BATCH_SIZE + 1}: {len(lote)} grupos...", end=" ", flush=True)
            try:
                decisions = batch_deepseek(client, lote)
                all_decisions.extend(decisions)
                n_fix = sum(1 for d in decisions if d.get("decision") == "TIENE_CONCENTRACION")
                n_skip = sum(1 for d in decisions if d.get("decision") == "LEGITIMO_SIN_CONC")
                print(f"→ {n_fix} fixes, {n_skip} legítimos")
            except Exception as e:
                print(f"ERROR: {e}")

        # Mapear decisiones
        dec_by_id = {d["id"]: d for d in all_decisions}
        for g in pendientes:
            dec = dec_by_id.get(g["id"])
            if dec and dec.get("decision") == "TIENE_CONCENTRACION" and dec.get("concentracion_norm"):
                fixes_deepseek[g["id"]] = (g, dec["concentracion_norm"], dec.get("razon", ""))
            elif dec and dec.get("decision") == "LEGITIMO_SIN_CONC":
                skipped_legit.append(g)
            else:
                still_unknown.append(g)

    elif pendientes:
        print(f"\n[Paso 4] Sin clave DeepSeek — {len(pendientes)} grupos pendientes sin diagnosticar")
        still_unknown = pendientes

    # ── Paso 5: Aplicar fixes ────────────────────────────────────────────────
    print(f"\n[Paso 5] Aplicando fixes...")

    total_fixes = 0

    # Fixes directos
    for gid, (g, conc) in fixes_directos.items():
        print(f"  [DIRECTO] id={gid} {g['dci_key']} → '{conc}'")
        apply_fix(cur, gid, conc, args.dry_run)
        total_fixes += 1

    # Fixes DeepSeek
    for gid, (g, conc, razon) in fixes_deepseek.items():
        print(f"  [DEEPSEEK] id={gid} {g['dci_key']} → '{conc}' ({razon[:60]})")
        apply_fix(cur, gid, conc, args.dry_run)
        total_fixes += 1

    if not args.dry_run and total_fixes > 0:
        con.commit()
        print(f"\n✓ {total_fixes} grupos actualizados en grupos_equivalencia")
    elif args.dry_run:
        print(f"\n[DRY-RUN] {total_fixes} fixes pendientes (no aplicados)")

    # ── Resumen final ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESUMEN:")
    print(f"  Legítimos SIN_CONCENTRACION (sin cambio): {len(skipped_legit)}")
    print(f"  Fixes directos desde DB: {len(fixes_directos)}")
    print(f"  Fixes desde DeepSeek: {len(fixes_deepseek)}")
    print(f"  Sin diagnosticar: {len(still_unknown)}")
    print(f"{'='*60}")

    if still_unknown:
        print(f"\nGrupos sin diagnosticar ({len(still_unknown)}):")
        for g in still_unknown:
            print(f"  id={g['id']} [{g['grupo_via']}] {g['dci_key']} (n={g['n_productos']})")

    # Guardar reporte
    reporte = {
        "legit_sin_conc": [{"id": g["id"], "dci_key": g["dci_key"]} for g in skipped_legit],
        "fixes_directos": [{"id": gid, "dci_key": g["dci_key"], "conc": conc} for gid, (g, conc) in fixes_directos.items()],
        "fixes_deepseek": [{"id": gid, "dci_key": g["dci_key"], "conc": conc, "razon": razon} for gid, (g, conc, razon) in fixes_deepseek.items()],
        "sin_diagnosticar": [{"id": g["id"], "dci_key": g["dci_key"], "via": g["grupo_via"]} for g in still_unknown],
    }
    with open("sinconc_fix_report.json", "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2)
    print(f"\nReporte guardado en sinconc_fix_report.json")

    con.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--key", default=os.getenv("DEEPSEEK_API_KEY"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--socrata", action="store_true", help="Fetch Socrata data for groups with null components")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
