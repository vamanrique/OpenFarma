"""
Enriquecimiento de registros INVIMA en tramite de renovacion.

Fuente: https://www.datos.gov.co/resource/vgr4-gemg.json
Dataset: Registros sanitarios vigentes de medicamentos (en tramite renovacion)

Descarga todos los expedientes con estadoregistro='En tramite renov' y los
procesa con el mismo NormalizadorLLM que el CUM activo. Los guarda en la
misma tabla cum_normalizado con fuente='CUM_RENOVACION'.

Uso:
    python etl/enriquecer_renovacion.py --api-key sk-xxx
    python etl/enriquecer_renovacion.py --api-key sk-xxx --solo-nuevos
"""
import argparse
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

API_URL   = "https://www.datos.gov.co/resource/vgr4-gemg.json"
PAGE_SIZE = 5_000
MAX_RETRIES = 3
FUENTE    = "CUM_RENOVACION"


async def _descargar_pagina(client: httpx.AsyncClient, offset: int) -> list[dict]:
    params = {
        "$limit":  PAGE_SIZE,
        "$offset": offset,
        "$order":  "expedientecum ASC, consecutivocum ASC",
    }
    timeout = httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(API_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = attempt * 10
            print(f"[retry {attempt}/{MAX_RETRIES} en {wait}s: {exc}]", flush=True)
            await asyncio.sleep(wait)
    return []


async def descargar_todo() -> pd.DataFrame:
    todas: list[dict] = []
    offset = 0
    async with httpx.AsyncClient() as client:
        while True:
            print(f"  Descargando offset {offset}...", end=" ", flush=True)
            t0 = time.time()
            filas = await _descargar_pagina(client, offset)
            print(f"{len(filas)} filas ({time.time()-t0:.1f}s)")
            if not filas:
                break
            todas.extend(filas)
            if len(filas) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    print(f"  Total descargado: {len(todas)} filas")
    return pd.DataFrame(todas)


def main():
    parser = argparse.ArgumentParser(
        description="Enriquecimiento de registros INVIMA en tramite de renovacion"
    )
    parser.add_argument("--api-key",     required=True, help="API key de DeepSeek")
    parser.add_argument("--solo-nuevos", action="store_true",
                        help="Omitir registros ya cacheados")
    parser.add_argument("--limite-grupos", type=int, default=None,
                        help="Limitar grupos a procesar (para pruebas)")
    args = parser.parse_args()

    print("\n=== Enriquecimiento INVIMA en tramite renovacion -> LLM ===\n")

    # 1. Descarga
    print("1. Descargando registros de renovacion...")
    df = asyncio.run(descargar_todo())

    if df.empty:
        print("  No se encontraron registros.")
        return

    # Asegurar columnas minimas (mismo esquema que CUM)
    for col in ["expedientecum", "consecutivocum", "principioactivo",
                "cantidad", "unidadmedida", "unidadreferencia",
                "concentracion", "formafarmaceutica", "viaadministracion",
                "descripcioncomercial", "producto", "titular",
                "registrosanitario", "estadocum", "estadoregistro", "atc"]:
        if col not in df.columns:
            df[col] = ""

    total_filas  = len(df)
    total_grupos = df.groupby(["expedientecum", "consecutivocum"]).ngroups
    print(f"  {total_filas} filas -> {total_grupos} grupos unicos")

    # 2. Normalizar
    from app.database import SessionLocal, Base, engine
    from app.models.cum_normalizado import CumNormalizado  # noqa: F401
    Base.metadata.create_all(bind=engine)

    from etl.normalizador_llm import NormalizadorLLM
    norm = NormalizadorLLM(api_key=args.api_key)

    print(f"\n2. Normalizando{' (solo nuevos)' if args.solo_nuevos else ''}...")

    if args.solo_nuevos:
        from sqlalchemy import text
        with engine.connect() as conn:
            cached = set(conn.execute(
                text("SELECT expediente_cum || '-' || consecutivo_cum FROM cum_normalizado"
                     " WHERE fuente=:f"),
                {"f": FUENTE}
            ).scalars())
        grupos_df = df.groupby(["expedientecum", "consecutivocum"])
        ids_todos = {f"{e}-{c}" for (e, c), _ in grupos_df}
        nuevos = ids_todos - cached
        print(f"  Cacheados: {len(cached)} | Nuevos: {len(nuevos)} | Total: {total_grupos}")
        if not nuevos:
            print("  Nada nuevo que procesar.")
            return
        exps_nuevos = {k.split("-")[0] for k in nuevos}
        df = df[df["expedientecum"].isin(exps_nuevos)]

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    t_inicio = time.time()
    with SessionLocal() as db:
        norm.procesar_dataframe(df, db, limite=args.limite_grupos, fuente=FUENTE)
    elapsed = time.time() - t_inicio

    # 3. Resumen
    from sqlalchemy import text
    with engine.connect() as conn:
        total_cache = conn.execute(
            text("SELECT COUNT(*) FROM cum_normalizado WHERE fuente=:f"), {"f": FUENTE}
        ).scalar()
        con_dci = conn.execute(
            text("SELECT COUNT(*) FROM cum_normalizado WHERE fuente=:f AND principios_dci IS NOT NULL"),
            {"f": FUENTE}
        ).scalar()
        con_dosis = conn.execute(
            text("SELECT COUNT(*) FROM cum_normalizado WHERE fuente=:f AND dosis_total_mg IS NOT NULL"),
            {"f": FUENTE}
        ).scalar()
        combinados = conn.execute(
            text("SELECT COUNT(*) FROM cum_normalizado WHERE fuente=:f AND tipo_formula != 'MONO'"),
            {"f": FUENTE}
        ).scalar()

    sep = "-" * 50
    print(f"\n{sep}")
    print(f"Fuente                : {FUENTE}")
    print(f"Tiempo total          : {elapsed/60:.1f} min")
    print(f"Registros en cache    : {total_cache}")
    if total_cache:
        print(f"Con DCI extraido      : {con_dci} ({con_dci/total_cache*100:.0f}%)")
        print(f"Con dosis total       : {con_dosis} ({con_dosis/total_cache*100:.0f}%)")
        print(f"Combinados (BI+TRI+)  : {combinados}")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
