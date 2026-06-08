"""
Genera datos de demostración para consultas_region.
Simula reportes ciudadanos por región para mostrar variación en el mapa de riesgo.

Uso:
    .venv/Scripts/python seed_demo.py
"""
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, init_db
from app.models.region import Region, ConsultaRegion
from app.models.prediccion import PrediccionDesabastecimiento
from app.models.cum_normalizado import CumNormalizado

init_db()

# Departamentos con mayor densidad poblacional (más ciudadanos → más reportes)
REGION_ACTIVIDAD = {
    "Bogotá D.C.": 0.9,
    "Antioquia": 0.8,
    "Valle del Cauca": 0.7,
    "Cundinamarca": 0.6,
    "Santander": 0.5,
    "Atlántico": 0.5,
    "Bolívar": 0.4,
    "Nariño": 0.35,
    "Córdoba": 0.3,
    "Tolima": 0.3,
    "Cauca": 0.25,
    "Meta": 0.2,
    "Huila": 0.2,
    "Caldas": 0.2,
}


def seed_consultas():
    db = SessionLocal()
    rng = np.random.default_rng(seed=42)

    # Limpiar datos de demo previos
    existing = db.query(ConsultaRegion).count()
    if existing > 0:
        print(f"Limpiando {existing} consultas previas...")
        db.query(ConsultaRegion).delete()
        db.commit()

    regiones = db.query(Region).all()
    region_map = {r.nombre: r for r in regiones}

    # Obtener predicciones actuales (top 40 por probabilidad — los más en riesgo)
    top_preds = (
        db.query(
            PrediccionDesabastecimiento.cum_id,
            PrediccionDesabastecimiento.medicamento_nombre,
            PrediccionDesabastecimiento.probabilidad,
        )
        .distinct(PrediccionDesabastecimiento.cum_id)
        .order_by(PrediccionDesabastecimiento.probabilidad.desc())
        .limit(40)
        .all()
    )

    if not top_preds:
        print("No hay predicciones. Ejecuta poblar_predicciones.py primero.")
        db.close()
        return

    print(f"Generando señales demo para {len(top_preds)} medicamentos × {len(regiones)} regiones...")
    n_insertados = 0

    for pred in top_preds:
        cum_id = pred.cum_id
        proba_base = pred.probabilidad

        for region in regiones:
            actividad_region = REGION_ACTIVIDAD.get(region.nombre, 0.1)

            # Búsquedas: mayor en regiones más activas + algo aleatorio
            n_busquedas = int(
                rng.poisson(lam=max(1, actividad_region * 15 * (1 + proba_base * 5)))
            )

            # Reportes de no disponibilidad: correlacionados con riesgo base + región
            tasa_reporte = proba_base * actividad_region * 0.5
            n_reportes = int(rng.poisson(lam=max(0, tasa_reporte * 8)))

            if n_busquedas > 0:
                db.add(ConsultaRegion(
                    cum_id=cum_id,
                    region_id=region.id,
                    tipo="busqueda",
                    conteo=n_busquedas,
                ))
                n_insertados += 1

            if n_reportes > 0:
                db.add(ConsultaRegion(
                    cum_id=cum_id,
                    region_id=region.id,
                    tipo="reporte_no_disponibilidad",
                    conteo=n_reportes,
                ))
                n_insertados += 1

    db.commit()
    print(f"OK: {n_insertados} registros de consultas demo insertados.")
    print("\nAhora ejecuta poblar_predicciones.py para recalcular con las señales regionales.")
    db.close()


if __name__ == "__main__":
    seed_consultas()
