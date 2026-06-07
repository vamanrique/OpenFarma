"""
Enriquecimiento masivo de todos los registros activos del CUM.

Descarga todos los expedientecum activos en páginas y los procesa a través
del normalizador LLM. Usa el caché interno: solo envía al LLM lo que no
está guardado o cuyo hash cambió.

Uso:
    python etl/enriquecer_todo.py --api-key sk-xxx
    python etl/enriquecer_todo.py --api-key sk-xxx --solo-nuevos
    python etl/enriquecer_todo.py --api-key sk-xxx --pagina-inicio 5
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

API_URL    = "https://www.datos.gov.co/resource/i7cb-raxc.json"
PAGE_SIZE  = 10_000   # filas por página (páginas pequeñas = menos timeout en Socrata)
MAX_RETRIES = 3


async def _descargar_pagina(client: httpx.AsyncClient, offset: int, solo_activos: bool) -> list[dict]:
    where = "estadocum='Activo'" if solo_activos else None
    params = {
        "$limit":  PAGE_SIZE,
        "$offset": offset,
        "$order":  "expedientecum ASC, consecutivocum ASC",
    }
    if where:
        params["$where"] = where
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
    return []  # unreachable


async def descargar_todo(solo_activos: bool = True, offset_inicio: int = 0) -> pd.DataFrame:
    """Descarga paginada de todos los registros del CUM."""
    todas: list[dict] = []
    offset = offset_inicio
    async with httpx.AsyncClient() as client:
        while True:
            print(f"  Descargando offset {offset}...", end=" ", flush=True)
            t0 = time.time()
            filas = await _descargar_pagina(client, offset, solo_activos)
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
    parser = argparse.ArgumentParser(description="Enriquecimiento masivo del CUM con LLM")
    parser.add_argument("--api-key",      required=True, help="API key de DeepSeek")
    parser.add_argument("--solo-nuevos",  action="store_true",
                        help="Omitir registros ya cacheados (más rápido para reejecutar)")
    parser.add_argument("--solo-activos", action="store_true", default=True,
                        help="Solo registros con estadocum=Activo (default: True)")
    parser.add_argument("--pagina-inicio", dest="pagina_inicio", type=int, default=0,
                        help=f"Empezar desde este numero de pagina (cada pagina={PAGE_SIZE} filas)")
    parser.add_argument("--limite-grupos", type=int, default=None,
                        help="Limitar total de grupos a procesar (útil para pruebas)")
    args = parser.parse_args()

    print("\n=== Enriquecimiento masivo CUM -> LLM ===\n")

    # 1. Descarga paginada
    offset_inicio = args.pagina_inicio * PAGE_SIZE
    print(f"1. Descargando registros del CUM (offset_inicio={offset_inicio})...")
    df = asyncio.run(descargar_todo(solo_activos=args.solo_activos, offset_inicio=offset_inicio))

    if df.empty:
        print("  No se encontraron registros.")
        return

    # Asegurar columnas mínimas
    for col in ["expedientecum", "consecutivocum", "principioactivo",
                "cantidad", "unidadmedida", "unidadreferencia",
                "concentracion", "formafarmaceutica", "viaadministracion",
                "descripcioncomercial", "producto"]:
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
        # Filtrar expedientecum que ya están en caché con hash correcto
        # (procesar_dataframe ya hace esto internamente, pero al mostrar el progreso
        #  conviene saberlo de antemano)
        from sqlalchemy import text
        with engine.connect() as conn:
            cached = set(conn.execute(
                text("SELECT expediente_cum || '-' || consecutivo_cum FROM cum_normalizado")
            ).scalars())
        grupos_df = df.groupby(["expedientecum", "consecutivocum"])
        ids_todos = {f"{e}-{c}" for (e, c), _ in grupos_df}
        nuevos = ids_todos - cached
        print(f"  Cacheados: {len(cached)} | Nuevos: {len(nuevos)} | Total: {total_grupos}")
        if not nuevos:
            print("  Nada nuevo que procesar.")
            return
        # Filtrar el dataframe a los nuevos expedientecum (como proxy)
        exps_nuevos = {k.split("-")[0] for k in nuevos}
        df = df[df["expedientecum"].isin(exps_nuevos)]

    limite = args.limite_grupos
    t_inicio = time.time()

    # Checkpoint: mostrar progreso cada 500 grupos procesados
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )

    with SessionLocal() as db:
        norm.procesar_dataframe(df, db, limite=limite)

    elapsed = time.time() - t_inicio

    # 3. Resumen final
    from sqlalchemy import text
    with engine.connect() as conn:
        total_cache = conn.execute(text("SELECT COUNT(*) FROM cum_normalizado")).scalar()
        con_dci     = conn.execute(text("SELECT COUNT(*) FROM cum_normalizado WHERE principios_dci IS NOT NULL")).scalar()
        con_dosis   = conn.execute(text("SELECT COUNT(*) FROM cum_normalizado WHERE dosis_total_mg IS NOT NULL")).scalar()
        combinados  = conn.execute(text("SELECT COUNT(*) FROM cum_normalizado WHERE tipo_formula != 'MONO'")).scalar()

    sep = "-" * 50
    print(f"\n{sep}")
    print(f"Tiempo total          : {elapsed/60:.1f} min")
    print(f"Registros en caché    : {total_cache}")
    print(f"Con DCI extraido      : {con_dci} ({con_dci/total_cache*100:.0f}%)")
    print(f"Con dosis total       : {con_dosis} ({con_dosis/total_cache*100:.0f}%)")
    print(f"Combinados (BI+TRI+)  : {combinados}")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
