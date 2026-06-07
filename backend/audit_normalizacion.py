#!/usr/bin/env python
"""
Auditoría de normalización CUM con DeepSeek.

Descarga medicamentos representativos del API Socrata, corre el pipeline
y pide a DeepSeek que valide si la normalización y el agrupamiento de
homólogos es clínicamente correcto.

Uso:
    python audit_normalizacion.py --key sk-...
    python audit_normalizacion.py            # usa env DEEPSEEK_API_KEY

Salida: reporte en consola + audit_report.json
"""
import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict

import httpx
import pandas as pd
from openai import OpenAI

sys.path.insert(0, os.path.dirname(__file__))
from etl.transformacion import agrupar_y_transformar, MedicamentoTransformado

# ─── Configuración ──────────────────────────────────────────────────────────

SOCRATA_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE  = "https://api.deepseek.com"
HTTP_TIMEOUT   = 25.0

# Grupos a auditar: (dci_canónico, término_socrata, descripción_de_qué_verificar)
GRUPOS: list[tuple[str, str, str]] = [
    ("ACICLOVIR",      "ACICLOVIR",      "tableta 200/400/800mg + polvo iny 250/500mg + crema 5%"),
    ("PARACETAMOL",    "ACETAMINOFEN",   "tableta 500mg/1g + suspensión 160mg/5mL (sinónimo ACETAMINOFÉN)"),
    ("AMOXICILINA",    "AMOXICILINA",    "cápsula 500mg (algunos en g) + suspensión 250mg/5mL"),
    ("METFORMINA",     "METFORMINA",     "tableta 500/850/1000mg — prueba unidades g→mg"),
    ("CIPROFLOXACINO", "CIPROFLOXACINO", "tableta 250/500mg + inyectable 2mg/mL"),
    ("MIDAZOLAM",      "MIDAZOLAM",      "solución iny 5mg/mL en diferentes tamaños de ampolla"),
    ("VANCOMICINA",    "VANCOMICINA",    "polvo liofilizado 500mg/1g — prueba polvo vs solución"),
    ("SALBUTAMOL",     "SALBUTAMOL",     "aerosol 100mcg/dosis — inhalado y solución nebulizar"),
    ("METAMIZOL",      "DIPIRONA",       "sinónimo DIPIRONA→METAMIZOL"),
    ("NIFEDIPINO",     "NIFEDIPINA",     "sinónimo NIFEDIPINA→NIFEDIPINO"),
]

AUDIT_SYSTEM = """\
Eres farmacólogo experto en normalización de datos del CUM colombiano (INVIMA).

Recibirás un grupo de medicamentos con el mismo principio activo, incluyendo:
- Datos crudos de Socrata (campos "raw_")
- Output del pipeline de normalización de la aplicación

Tu tarea: validar que la normalización es CORRECTA para encontrar homólogos reales.

REGLAS CLÍNICAS QUE DEBES VERIFICAR:
1. Polvos/liofilizados inyectables (POLVO/LIOFILIZADO en forma):
   - concentracion_display debe ser "X mg" (masa total por vial), NO "X mg/mL".
   - El volumen del vial es el solvente de reconstitución, no el denominador.
   - "ACICLOVIR 250mg POLVO + VIAL 20mL" → debe mostrar "250 mg", NO "12.5 mg/mL".

2. Soluciones inyectables ya preparadas (SOLUCION INYECTABLE):
   - concentracion_display debe ser "X mg/mL".
   - "MIDAZOLAM 15mg/3mL" → "5 mg/mL".

3. Líquidos orales:
   - concentracion_display debe ser "X mg/mL".
   - "AMOXICILINA 250mg/5mL" → "50 mg/mL".

4. Sólidos orales (tabletas, cápsulas):
   - concentracion_display debe ser "X mg" por unidad.
   - Un tableta "0.5 g" y una "500 mg" deben tener EXACTAMENTE el mismo dosis_numerica.

5. dosis_numerica: Siempre en mg-equivalentes. "0.5 g" → 500, "500 mg" → 500, "200 mcg" → 0.2.

6. Homólogos reales: dos productos son homólogos si tienen mismo DCI, misma forma farmacéutica
   equivalente, y misma dosis (mismo dosis_numerica). Deben poder sustituirse uno por otro.

7. principios_dci: Nombre INN OMS en español, sin sales ni sufijos.
   ACETAMINOFÉN/ACETAMINOFEN → PARACETAMOL; DIPIRONA → METAMIZOL; NIFEDIPINA → NIFEDIPINO.

FORMATO DE RESPUESTA — JSON exacto:
{
  "grupo": "NOMBRE_DCI",
  "resultado": "PASS" o "FAIL",
  "errores": [
    {
      "cum_id": "EXPEDIENTE-CONSECUTIVO",
      "campo": "concentracion_display | dosis_numerica | principios_dci | tipo_formula",
      "valor_actual": "...",
      "valor_correcto": "...",
      "explicacion": "..."
    }
  ],
  "homologos_no_agrupados": [
    {
      "cum_ids": ["id_A", "id_B"],
      "razon": "misma molecula+dosis pero dosis_numerica distinto"
    }
  ],
  "resumen": "Una frase sobre qué está bien o mal."
}
"""

# ─── Socrata fetch ──────────────────────────────────────────────────────────

async def fetch_dci(client: httpx.AsyncClient, termino: str, limit: int = 200) -> list[dict]:
    """Descarga registros del CUM activo para un término de búsqueda."""
    params = {
        "$where": f"(upper(producto) like '%{termino}%' OR upper(principioactivo) like '%{termino}%') AND estadocum='Activo'",
        "$limit": limit,
        "$order": "producto ASC",
    }
    r = await client.get(SOCRATA_URL, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


async def completar_grupos(client: httpx.AsyncClient, filas: list[dict]) -> list[dict]:
    """Recupera todas las filas de los expedientes encontrados (para combinados)."""
    expedientes = list({f["expedientecum"] for f in filas if f.get("expedientecum")})
    if not expedientes:
        return filas
    extra: list[dict] = []
    for i in range(0, len(expedientes), 50):
        lote = expedientes[i:i+50]
        ids  = ", ".join(f"'{e}'" for e in lote)
        r = await client.get(SOCRATA_URL, params={"$where": f"expedientecum IN ({ids})", "$limit": 2000}, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        extra.extend(r.json())
    dedup = {(f["expedientecum"], f.get("consecutivocum",""), f.get("principioactivo","")): f
             for f in filas + extra}
    return list(dedup.values())


# ─── Serialización del output del pipeline ──────────────────────────────────

def med_a_dict(m: MedicamentoTransformado, raw_primera: dict) -> dict:
    """Compacta un MedicamentoTransformado + la fila raw para enviar a DeepSeek."""
    return {
        "cum_id":               m.cum_id,
        "nombre_comercial":     m.nombre_comercial,
        # Output pipeline
        "principios_dci":       m.principios_dci,
        "tipo_formula":         m.tipo_formula,
        "concentracion_display":m.concentracion_display,
        "dosis_numerica":       m.dosis_numerica,
        "presentacion":         m.presentacion,
        "forma_farmaceutica":   m.forma_farmaceutica,
        "via_administracion":   m.via_administracion,
        # Datos crudos clave para verificar
        "raw_principioactivo":  raw_primera.get("principioactivo", ""),
        "raw_cantidad":         raw_primera.get("cantidad", ""),
        "raw_unidad":           raw_primera.get("unidad", "") or raw_primera.get("unidadmedida", ""),
        "raw_unidadreferencia": raw_primera.get("unidadreferencia", ""),
        "raw_forma":            raw_primera.get("formafarmaceutica", ""),
    }


# ─── Llamada a DeepSeek ─────────────────────────────────────────────────────

def auditar_grupo_deepseek(
    client: OpenAI,
    dci: str,
    meds: list[dict],
    descripcion: str,
) -> dict:
    """Envía un grupo de medicamentos a DeepSeek para validación."""
    payload = json.dumps({
        "grupo_dci": dci,
        "descripcion_esperada": descripcion,
        "productos": meds,
    }, ensure_ascii=False)

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": AUDIT_SYSTEM},
            {"role": "user",   "content": payload},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4096,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError as e:
        return {"grupo": dci, "resultado": "ERROR", "resumen": f"JSON inválido: {e}"}


# ─── Pipeline principal ─────────────────────────────────────────────────────

async def descargar_todos(grupos: list[tuple]) -> dict[str, tuple[list[MedicamentoTransformado], dict[str, dict]]]:
    """Descarga y transforma todos los grupos en paralelo."""
    resultados: dict[str, tuple[list[MedicamentoTransformado], dict[str, dict]]] = {}
    async with httpx.AsyncClient() as client:
        tareas = {dci: fetch_dci(client, termino) for dci, termino, _ in grupos}
        for dci, tarea in tareas.items():
            termino = next(t for d, t, _ in grupos if d == dci)
            print(f"  Descargando {dci} ({termino})…", end=" ", flush=True)
            try:
                filas = await tarea
                filas = await completar_grupos(client, filas)
                df = pd.DataFrame(filas)
                if df.empty:
                    print("sin datos")
                    continue
                meds = agrupar_y_transformar(df)
                # Índice raw por cum_id para poder enviar los datos crudos también
                raw_idx: dict[str, dict] = {}
                for _, grp in df.groupby(["expedientecum", "consecutivocum"]):
                    primera = grp.iloc[0].to_dict()
                    cid = f"{primera['expedientecum']}-{primera['consecutivocum']}"
                    raw_idx[cid] = primera
                resultados[dci] = (meds, raw_idx)
                print(f"{len(meds)} presentaciones")
            except Exception as e:
                print(f"ERROR: {e}")
    return resultados


def main():
    parser = argparse.ArgumentParser(description="Auditoría de normalización CUM con DeepSeek")
    parser.add_argument("--key", default=os.getenv("DEEPSEEK_API_KEY"), help="API key de DeepSeek")
    parser.add_argument("--grupos", nargs="*", help="Filtrar grupos por DCI (ej. ACICLOVIR MIDAZOLAM)")
    parser.add_argument("--output", default="audit_report.json", help="Archivo de salida JSON")
    args = parser.parse_args()

    if not args.key:
        print("ERROR: falta API key de DeepSeek. Pásala con --key o DEEPSEEK_API_KEY env.")
        sys.exit(1)

    grupos_activos = [g for g in GRUPOS if not args.grupos or g[0] in args.grupos]
    if not grupos_activos:
        print(f"No se encontraron grupos. Opciones: {[g[0] for g in GRUPOS]}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Auditoría CUM — {len(grupos_activos)} grupos")
    print(f"{'='*60}")

    # 1. Descargar y transformar
    print("\n[1/3] Descargando datos del Socrata CUM…")
    datos = asyncio.run(descargar_todos(grupos_activos))

    if not datos:
        print("No se pudo descargar ningún grupo. Verifica conexión a datos.gov.co")
        sys.exit(1)

    # 2. Preparar payload para DeepSeek
    print("\n[2/3] Enviando a DeepSeek para validación…")
    deepseek = OpenAI(api_key=args.key, base_url=DEEPSEEK_BASE)
    reportes: list[dict] = []
    n_pass = n_fail = n_err = 0

    for dci, termino, descripcion in grupos_activos:
        if dci not in datos:
            continue
        meds, raw_idx = datos[dci]

        # Limitar a 40 productos para no explotar el contexto de DeepSeek
        meds_muestra = meds[:40]
        payload_meds = [
            med_a_dict(m, raw_idx.get(m.cum_id, {}))
            for m in meds_muestra
        ]

        print(f"  → {dci} ({len(meds_muestra)} productos)…", end=" ", flush=True)
        try:
            reporte = auditar_grupo_deepseek(deepseek, dci, payload_meds, descripcion)
        except Exception as e:
            reporte = {"grupo": dci, "resultado": "ERROR", "resumen": str(e), "errores": [], "homologos_no_agrupados": []}

        reporte["n_productos"] = len(meds)
        reporte["n_muestra"]   = len(meds_muestra)
        reportes.append(reporte)

        resultado = reporte.get("resultado", "?")
        if resultado == "PASS":
            n_pass += 1
            print("✓ PASS")
        elif resultado == "FAIL":
            n_fail += 1
            n_err_grupo = len(reporte.get("errores", []))
            print(f"✗ FAIL ({n_err_grupo} errores)")
        else:
            n_err += 1
            print(f"? {resultado}")

    # 3. Guardar y mostrar resumen
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(reportes, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"RESUMEN: {n_pass} PASS | {n_fail} FAIL | {n_err} ERROR")
    print(f"{'='*60}")

    for r in reportes:
        grupo   = r.get("grupo", "?")
        result  = r.get("resultado", "?")
        resumen = r.get("resumen", "")
        icon    = "✓" if result == "PASS" else ("✗" if result == "FAIL" else "?")
        print(f"\n{icon} {grupo}: {resumen}")

        for e in r.get("errores", []):
            print(f"  ├─ [{e.get('campo','?')}] {e.get('cum_id','?')}")
            print(f"  │   actual:   {e.get('valor_actual','?')}")
            print(f"  │   correcto: {e.get('valor_correcto','?')}")
            print(f"  │   nota:     {e.get('explicacion','')}")

        for h in r.get("homologos_no_agrupados", []):
            ids = " + ".join(h.get("cum_ids", []))
            print(f"  ├─ [homólogos no agrupados] {ids}")
            print(f"  │   {h.get('razon','')}")

    print(f"\nReporte completo guardado en: {args.output}")

    if n_fail > 0:
        print(f"\nHay {n_fail} grupos con errores. Revisa {args.output} para el detalle.")
        sys.exit(2)


if __name__ == "__main__":
    main()
