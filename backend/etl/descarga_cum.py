"""
Descarga el CUM desde la API Socrata de datos.gov.co con paginación completa.
Guarda el resultado crudo en data/cum_raw.csv para auditoría.
"""
import requests
import pandas as pd
import os
import time
from pathlib import Path

API_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_FILE = DATA_DIR / "cum_raw.csv"

BATCH_SIZE = 5_000
MAX_REGISTROS = int(os.getenv("CUM_MAX_REGISTROS", "0"))  # 0 = sin límite


def descargar_cum(verbose: bool = True) -> pd.DataFrame:
    DATA_DIR.mkdir(exist_ok=True)
    registros: list[dict] = []
    offset = 0

    if verbose:
        print(f"Descargando CUM desde {API_URL}...")

    while True:
        params = {
            "$limit": BATCH_SIZE,
            "$offset": offset,
            "$order": "expedientecum ASC",
        }
        if MAX_REGISTROS and offset >= MAX_REGISTROS:
            break

        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            batch = resp.json()
        except requests.RequestException as e:
            print(f"  ERROR en offset {offset}: {e}")
            break

        if not batch:
            break

        registros.extend(batch)
        offset += len(batch)

        if verbose:
            print(f"  Descargados: {offset:,} registros...", end="\r")

        if len(batch) < BATCH_SIZE:
            break

        time.sleep(0.2)

    if verbose:
        print(f"\nTotal descargado: {len(registros):,} registros")

    df = pd.DataFrame(registros)
    df.to_csv(RAW_FILE, index=False, encoding="utf-8-sig")
    if verbose:
        print(f"Guardado en: {RAW_FILE}")
    return df


if __name__ == "__main__":
    descargar_cum()
