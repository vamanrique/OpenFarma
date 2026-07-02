"""
actualizar_invima.py — Orquestador manual para actualizar datos INVIMA.

Uso:
    python actualizar_invima.py                    # busca y procesa todos los PDFs nuevos
    python actualizar_invima.py --anio 2026        # solo PDFs de 2026
    python actualizar_invima.py --retrain          # también reentrenar el modelo tras insertar
    python actualizar_invima.py --check-only       # solo listar URLs sin descargar
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Asegurar que el directorio padre (backend/) esté en el path
sys.path.insert(0, str(Path(__file__).parent))

from etl.invima_scraper import verificar_y_actualizar, scrape_urls_invima, meses_en_db


def main():
    parser = argparse.ArgumentParser(description="Actualización manual de datos INVIMA")
    parser.add_argument(
        "--db", type=Path,
        default=Path(__file__).parent / "farmavigia.db",
        help="Ruta a farmavigia.db (default: backend/farmavigia.db)",
    )
    parser.add_argument("--anio", type=int, default=None, help="Filtrar por año (ej: 2026)")
    parser.add_argument("--retrain", action="store_true",
                        help="Reentrenar el modelo de predicción tras insertar datos nuevos")
    parser.add_argument("--check-only", action="store_true",
                        help="Solo listar PDFs disponibles en la web, sin descargar")
    args = parser.parse_args()

    if args.check_only:
        pdfs = scrape_urls_invima()
        ya   = meses_en_db(args.db)
        print(f"\nPDFs encontrados en INVIMA.gov.co: {len(pdfs)}")
        print(f"Meses ya en DB: {sorted(ya)}\n")
        for p in pdfs:
            print(f"  {p['filename']}")
            print(f"    URL: {p['url']}")
        return

    print("\n" + "="*60)
    print("  Actualización INVIMA — descarga e inserción de PDFs nuevos")
    print("="*60)

    res = verificar_y_actualizar(args.db, solo_anio=args.anio)

    print(f"\nResultado:")
    print(f"  PDFs encontrados    : {res['pdfs_encontrados']}")
    print(f"  PDFs procesados     : {res['pdfs_procesados']}")
    print(f"  PDFs saltados       : {res['pdfs_saltados']}")
    print(f"  Registros insertados: {res['registros_insertados']}")
    print(f"  Registros actlz.    : {res['registros_actualizados']}")
    print(f"  Errores             : {res['errores']}")
    if res["meses_nuevos"]:
        print(f"  Meses nuevos        : {res['meses_nuevos']}")

    if res["pdfs_procesados"] > 0 and args.retrain:
        print("\nReentrenando modelo con datos actualizados...")
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "retrain_invima.py"),
                 "--db", str(args.db)],
                capture_output=True, text=True, check=True,
            )
            print(result.stdout)
        except Exception as exc:
            logger.error("Error reentrenando modelo: %s", exc)
    elif res["pdfs_procesados"] > 0:
        print("\nTip: usa --retrain para reentrenar el modelo con los nuevos datos.")


if __name__ == "__main__":
    main()
