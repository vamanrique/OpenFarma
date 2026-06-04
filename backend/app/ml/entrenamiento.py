"""
Script de entrenamiento. Lee el CUM desde la API online, construye features y entrena.

Uso:
    python -m app.ml.entrenamiento
    python -m app.ml.entrenamiento --desde-csv   # usa cum_raw.csv si existe (más rápido)
"""
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
import pandas as pd
from app.ml.modelo import entrenar

API_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
CSV_PATH = Path(__file__).parent.parent.parent / "data" / "cum_raw.csv"


def _descargar_para_ml(limite: int = 0) -> pd.DataFrame:
    """Descarga el CUM ordenado para que los combinados queden juntos."""
    registros: list[dict] = []
    offset = 0
    batch = 5_000
    print(f"Descargando CUM desde {API_URL}...")
    while True:
        params = {
            "$limit": min(batch, limite - offset) if limite else batch,
            "$offset": offset,
            "$order": "expedientecum ASC, consecutivocum ASC",
        }
        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  Error offset {offset}: {e}")
            break
        if not data:
            break
        registros.extend(data)
        offset += len(data)
        print(f"  {offset:,} registros...", end="\r")
        if len(data) < batch or (limite and offset >= limite):
            break
        time.sleep(0.15)
    print(f"\nTotal: {offset:,} registros")
    return pd.DataFrame(registros)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--desde-csv", action="store_true",
                        help="Usa data/cum_raw.csv si existe (evita re-descargar)")
    parser.add_argument("--limite", type=int, default=0)
    args = parser.parse_args()

    if args.desde_csv and CSV_PATH.exists():
        print(f"Cargando desde {CSV_PATH}...")
        df = pd.read_csv(CSV_PATH, dtype=str)
        print(f"  {len(df):,} registros")
    else:
        df = _descargar_para_ml(args.limite)

    print("\nEntrenando modelo de prediccion de desabastecimiento...")
    metricas = entrenar(df, verbose=True)
    print("\nEntrenamiento completado.")
    return metricas


if __name__ == "__main__":
    main()
