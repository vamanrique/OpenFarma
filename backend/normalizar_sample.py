"""
Script de validación del normalizador LLM.

Uso:
    python normalizar_sample.py --api-key sk-xxx --query midazolam --limite 50
    python normalizar_sample.py --api-key sk-xxx --query acetaminofen --limite 30
    python normalizar_sample.py --api-key sk-xxx --query metronidazol --limite 80

Muestra una tabla comparativa: campo raw vs campo normalizado por LLM.
"""
import argparse
import asyncio
import sys
import os

# Asegurar que el directorio backend esté en el path
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()


async def _descargar(query: str) -> pd.DataFrame:
    import httpx
    API_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
    q = query.upper()
    where = f"(upper(producto) like '%{q}%' OR upper(principioactivo) like '%{q}%')"
    params = {"$where": where, "$limit": 500, "$order": "expedientecum ASC"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(API_URL, params=params)
        resp.raise_for_status()
        filas = resp.json()
        print(f"  {len(filas)} filas descargadas del CUM para '{query}'")

        # Segunda pasada: completar filas faltantes de productos combinados.
        # Una búsqueda por nombre puede traer solo las filas del componente que
        # coincide, omitiendo los demás componentes del mismo expediente.
        expedientes = list({f['expedientecum'] for f in filas if f.get('expedientecum')})
        BATCH = 50  # máximo de expedientes por query IN
        filas_extra: list[dict] = []
        for i in range(0, len(expedientes), BATCH):
            lote = expedientes[i:i + BATCH]
            ids  = ', '.join(f"'{e}'" for e in lote)
            where2 = f"expedientecum IN ({ids})"
            r2 = await client.get(API_URL, params={"$where": where2, "$limit": 2000})
            r2.raise_for_status()
            filas_extra.extend(r2.json())

    # Fusionar y deduplicar por clave natural
    todas = {(f['expedientecum'], f.get('consecutivocum',''), f.get('principioactivo','')): f
             for f in filas + filas_extra}
    print(f"  {len(todas)} filas únicas tras completar grupos combinados")
    return pd.DataFrame(list(todas.values()))


def _mostrar_resultados(df_norm: pd.DataFrame, limite: int):
    """Muestra comparativa raw vs normalizado para los primeros N grupos."""
    grupos = df_norm.groupby(['expedientecum', 'consecutivocum'], sort=False)
    sep = '-' * 80
    print(f"\n{sep}")
    print(f"{'EXP-CONS':<18} {'PRINCIPIO RAW':<35} {'DCI NORMALIZADO':<30}")
    print(f"{'':18} {'CONCENTRACION RAW':<35} {'mg/mL | Vol | Total':<30}")
    print(sep)

    for n, ((exp, cons), g) in enumerate(grupos):
        if n >= limite:
            break
        primera = g.iloc[0]
        principios_raw = ' + '.join(g['principioactivo'].dropna().unique().tolist())
        conc_raw       = str(primera.get('concentracion', '')).strip()
        forma_raw      = str(primera.get('formafarmaceutica', '')).strip()
        dci_norm       = primera.get('llm_principios_dci') or []
        conc_mg        = primera.get('llm_concentracion_mg_ml')
        vol            = primera.get('llm_volumen_ml_por_unidad')
        total          = primera.get('llm_dosis_total_mg')
        forma_norm     = primera.get('llm_forma_normalizada', '')
        notas          = primera.get('llm_notas', '')

        tipo         = primera.get('llm_tipo_formula') or ''
        componentes  = primera.get('llm_componentes') or []

        dci_str   = ', '.join(dci_norm) if dci_norm else '—'
        conc_str  = f"{conc_mg} mg/mL | {vol} mL | {total} mg" if conc_mg else f"— | — | {total} mg" if total else "—"
        tipo_tag  = f" [{tipo}]" if tipo else ''

        print(f"{exp[:8]}-{cons:<8}  {principios_raw[:34]:<35} {dci_str[:29]:<30}{tipo_tag}")
        print(f"  {conc_raw[:34]:<35} {conc_str[:29]:<30}")
        # Para combinados, mostrar detalle por componente
        if len(componentes) > 1:
            for c in componentes:
                dci_c  = c.get('dci', '?')
                mg_ml  = c.get('concentracion_mg_ml')
                dosis  = c.get('dosis_mg')
                c_str  = f"{mg_ml} mg/mL" if mg_ml else (f"{dosis} mg" if dosis else '—')
                print(f"    {dci_c:<20} {c_str}")
        if notas and isinstance(notas, str):
            print(f"  [!] {notas[:70]}")
        if forma_raw.upper() != forma_norm:
            print(f"  Forma: {forma_raw} -> {forma_norm}")
        print()


def main():
    parser = argparse.ArgumentParser(description='Validar normalizador LLM con muestra del CUM')
    parser.add_argument('--api-key', required=True,  help='API key de DeepSeek')
    parser.add_argument('--query',   required=True,  help='Término de búsqueda (ej: midazolam)')
    parser.add_argument('--limite',  type=int, default=50, help='Máximo de grupos a procesar (default: 50)')
    args = parser.parse_args()

    print(f"\n=== Normalizador LLM — muestra: '{args.query}' (límite: {args.limite} grupos) ===\n")

    # 1. Descargar datos
    print("1. Descargando datos del CUM...")
    df_raw = asyncio.run(_descargar(args.query))
    if df_raw.empty:
        print("  No se encontraron registros.")
        return

    # Asegurar columnas mínimas
    for col in ['expedientecum', 'consecutivocum', 'principioactivo',
                'concentracion', 'formafarmaceutica', 'viaadministracion',
                'presentacion', 'producto']:
        if col not in df_raw.columns:
            df_raw[col] = ''

    # 2. Normalizar
    print(f"2. Normalizando (máx {args.limite} grupos)...")
    from app.database import SessionLocal, Base, engine
    from app.models.cum_normalizado import CumNormalizado  # noqa: F401 — registra tabla

    # Crear tabla si no existe
    Base.metadata.create_all(bind=engine)

    from etl.normalizador_llm import NormalizadorLLM
    norm = NormalizadorLLM(api_key=args.api_key)
    with SessionLocal() as db:
        df_norm = norm.procesar_dataframe(df_raw, db, limite=args.limite)

    # 3. Mostrar resultados
    print(f"3. Resultados (primeros {min(args.limite, 30)} grupos):\n")
    _mostrar_resultados(df_norm, min(args.limite, 30))

    # 4. Resumen
    grupos = df_norm.groupby(['expedientecum', 'consecutivocum'])
    total  = len(grupos)
    con_dci   = sum(1 for _, g in grupos if g.iloc[0].get('llm_principios_dci'))
    con_total = sum(1 for _, g in grupos if g.iloc[0].get('llm_dosis_total_mg'))
    con_notas = sum(1 for _, g in grupos if g.iloc[0].get('llm_notas'))

    sep2 = '-' * 50
    print(sep2)
    print(f"Grupos procesados : {total}")
    print(f"Con DCI extraido  : {con_dci} ({con_dci/total*100:.0f}%)")
    print(f"Con dosis total   : {con_total} ({con_total/total*100:.0f}%)")
    print(f"Con notas/alertas : {con_notas} ({con_notas/total*100:.0f}%)")
    print(f"{sep2}\n")


if __name__ == '__main__':
    main()
