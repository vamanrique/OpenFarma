"""
Script de entrenamiento. Lee cum_normalizado desde la DB local y entrena el modelo.

Uso:
    python -m app.ml.entrenamiento
    python -m app.ml.entrenamiento --desde-csv   # usa data/cum_raw.csv (Socrata)
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


def _desde_db() -> pd.DataFrame:
    """Extrae datos de entrenamiento directamente desde cum_normalizado en SQLite."""
    from app.database import SessionLocal, init_db
    from app.ml.features import construir_features_desde_db

    print("Cargando cum_normalizado desde DB...")
    init_db()
    db = SessionLocal()
    try:
        df = construir_features_desde_db(db)
        print(f"  {len(df):,} registros con features construidas")
        return df
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--desde-csv", action="store_true",
                        help="Usa data/cum_raw.csv si existe (Socrata)")
    parser.add_argument("--desde-socrata", action="store_true",
                        help="Descarga desde Socrata (lento)")
    parser.add_argument("--limite", type=int, default=0)
    args = parser.parse_args()

    if args.desde_csv and CSV_PATH.exists():
        print(f"Cargando desde {CSV_PATH}...")
        df_raw = pd.read_csv(CSV_PATH, dtype=str)
        print(f"  {len(df_raw):,} registros")
        print("\nEntrenando modelo de prediccion de desabastecimiento...")
        metricas = entrenar(df_raw, verbose=True)
    elif args.desde_socrata:
        df_raw = _descargar_para_ml(args.limite)
        print("\nEntrenando modelo de prediccion de desabastecimiento...")
        metricas = entrenar(df_raw, verbose=True)
    else:
        # Modo por defecto: usar DB local (rápido, ~52k registros)
        df_feat = _desde_db()
        if df_feat.empty:
            print("ERROR: No hay datos en cum_normalizado. Ejecuta el ETL primero.")
            sys.exit(1)
        from app.ml.features import FEATURE_COLS
        from app.ml.modelo import entrenar_desde_features
        print("\nEntrenando modelo de prediccion de desabastecimiento...")
        metricas = entrenar_desde_features(df_feat, verbose=True)

    print("\nEntrenamiento completado.")
    return metricas


if __name__ == "__main__":
    main()
