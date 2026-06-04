"""
Pobla la tabla predicciones_desabastecimiento para los medicamentos más relevantes.
Corre con: .venv/Scripts/python poblar_predicciones.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, init_db
from app.models.medicamento import Medicamento
from app.services.prediccion import ServicioPrediccion
from app.models.prediccion import PrediccionDesabastecimiento

init_db()

BATCH = 200  # medicamentos a procesar

def main():
    db = SessionLocal()

    # Limpiar predicciones previas
    existing = db.query(PrediccionDesabastecimiento).count()
    if existing > 0:
        print(f"Limpiando {existing} predicciones previas...")
        db.query(PrediccionDesabastecimiento).delete()
        db.commit()

    meds = (
        db.query(Medicamento.id, Medicamento.nombre_comercial)
        .filter(Medicamento.estado == "vigente")
        .order_by(Medicamento.id)
        .limit(BATCH)
        .all()
    )

    print(f"Calculando predicciones para {len(meds)} medicamentos × 33 regiones...")
    servicio = ServicioPrediccion(db)

    t0 = time.time()
    for i, (med_id, nombre) in enumerate(meds, 1):
        servicio.predecir(med_id)
        if i % 20 == 0:
            elapsed = time.time() - t0
            eta = elapsed / i * (len(meds) - i)
            print(f"  {i}/{len(meds)} — {nombre[:40]:<40} ETA: {eta:.0f}s")

    total = db.query(PrediccionDesabastecimiento).count()
    print(f"\nDone. {total:,} predicciones guardadas ({len(meds)} meds × 33 regiones).")

    # Resumen por nivel
    from sqlalchemy import func
    rows = (
        db.query(PrediccionDesabastecimiento.nivel_riesgo, func.count().label("n"))
        .group_by(PrediccionDesabastecimiento.nivel_riesgo)
        .all()
    )
    for nivel, n in sorted(rows, key=lambda x: x[1], reverse=True):
        print(f"  {nivel:<10} {n:>6,}")

    db.close()

if __name__ == "__main__":
    main()
