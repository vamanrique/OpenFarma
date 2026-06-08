"""
Pipeline ETL: descarga live desde datos.gov.co → transforma → carga en DB.
No escribe CSVs intermedios — el JSON online es la única fuente.

Las alternativas NO se precomputan aquí (son 24M de pares, inmanejable en SQLite).
Se calculan on-demand via cum_live.py cuando el usuario selecciona un medicamento.

Uso:
    python -m etl.carga_cum               # carga completa
    python -m etl.carga_cum --limite 2000 # solo N registros crudos (prueba)
    python -m etl.carga_cum --solo-validar
"""
import sys
import argparse
import time
import requests
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from etl.validacion import validar, guardar_reporte
from etl.transformacion import agrupar_y_transformar

API_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
BATCH_SIZE = 5_000
DATA_DIR = Path(__file__).parent.parent / "data"


def descargar_live(limite: int = 0, verbose: bool = True) -> pd.DataFrame:
    registros: list[dict] = []
    offset = 0
    if verbose:
        print(f"Descargando CUM desde {API_URL}...", flush=True)
    while True:
        tamano = min(BATCH_SIZE, limite - offset) if limite else BATCH_SIZE
        params = {
            "$limit": tamano,
            "$offset": offset,
            "$order": "expedientecum ASC, consecutivocum ASC",
        }
        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            batch = resp.json()
        except requests.RequestException as e:
            print(f"\nError en offset {offset}: {e}", flush=True)
            break
        if not batch:
            break
        registros.extend(batch)
        offset += len(batch)
        if verbose:
            print(f"  Descargados: {offset:,}...", flush=True)
        if len(batch) < BATCH_SIZE or (limite and offset >= limite):
            break
        time.sleep(0.15)
    if verbose:
        print(f"Total: {len(registros):,} registros", flush=True)
    return pd.DataFrame(registros)


def cargar_medicamentos_en_db(meds_transformados, verbose: bool = True):
    # La tabla 'medicamentos' fue reemplazada por 'cum_normalizado'.
    # Este pipeline ahora es gestionado por auto_estandarizar.py.
    # Esta función se mantiene solo para compatibilidad de importaciones.
    if verbose:
        print("AVISO: cargar_medicamentos_en_db está deprecado. Usa auto_estandarizar.py.", flush=True)
    return

    from app.database import SessionLocal, init_db
    import app.models  # noqa

    init_db()

    db = SessionLocal()
    try:
        existentes: set = set()
        nuevos = 0

        for med in meds_transformados:
            if med.cum_id in existentes:
                continue
            principio_principal = med.principios_dci[0] if med.principios_dci else ""
            db.add(Medicamento(
                cum=med.cum_id,
                nombre_comercial=med.nombre_comercial[:300],
                nombre_generico=med.descripcion_atc[:300],
                principio_activo=principio_principal[:300],
                principios_dci=med.principios_dci,
                tipo_formula=med.tipo_formula,
                concentracion=med.concentracion_display[:300] if med.concentracion_display else None,
                forma_farmaceutica=med.forma_farmaceutica[:150],
                via_administracion=med.via_administracion[:100] if med.via_administracion else None,
                laboratorio=med.laboratorio[:300],
                registro_sanitario=med.registro_sanitario[:100],
                estado="vigente" if med.estado_registro.lower() == "vigente" else "vencido",
                estado_cum=med.estado_cum.lower(),
                codigo_atc=med.atc[:10],
                grupo_terapeutico=med.descripcion_atc[:300],
                modalidad=med.modalidad[:100] if med.modalidad else None,
            ))
            existentes.add(med.cum_id)
            nuevos += 1

            if nuevos % 2_000 == 0:
                db.commit()
                if verbose:
                    print(f"  Insertados: {nuevos:,}...", flush=True)

        db.commit()
        if verbose:
            print(f"Medicamentos nuevos insertados: {nuevos:,}", flush=True)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--solo-validar", action="store_true")
    args = parser.parse_args()

    # 1. Descarga live
    df_raw = descargar_live(limite=args.limite)

    # 2. Normalizar
    str_cols = df_raw.select_dtypes(include="str").columns
    df_raw[str_cols] = df_raw[str_cols].apply(lambda c: c.str.strip())

    # 3. Validación
    df_limpio, df_problemas = validar(df_raw, verbose=True)
    DATA_DIR.mkdir(exist_ok=True)
    guardar_reporte(df_problemas, DATA_DIR / "validacion_reporte.csv")

    if args.solo_validar:
        print("\nModo --solo-validar: sin carga en BD.", flush=True)
        return

    # 4. Transformación — agrupa por expedientecum+consecutivocum, detecta conjugados
    print("\nTransformando y agrupando principios activos...", flush=True)
    meds = agrupar_y_transformar(df_limpio)

    tipos: dict[str, int] = {}
    for m in meds:
        tipos[m.tipo_formula] = tipos.get(m.tipo_formula, 0) + 1
    print(f"  Total presentaciones unicas: {len(meds):,}", flush=True)
    for t, n in sorted(tipos.items(), key=lambda x: -x[1]):
        print(f"    {t:<20}: {n:,}", flush=True)

    # 5. Carga medicamentos en DB
    # (Alternativas: 24M pares — se calculan on-demand via API live, no se precomputan)
    print("\nCargando medicamentos en base de datos...", flush=True)
    cargar_medicamentos_en_db(meds)
    print("\nPipeline completado.", flush=True)


if __name__ == "__main__":
    main()
