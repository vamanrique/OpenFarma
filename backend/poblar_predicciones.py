"""
Pobla la tabla predicciones con medicamentos activos representativos del CUM.
Selecciona drogas de clases ATC con historial de discontinuación para mostrar
variación en el mapa de riesgo.

Uso:
    .venv/Scripts/python poblar_predicciones.py
    .venv/Scripts/python poblar_predicciones.py --batch 500
"""
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, init_db
from app.models.cum_normalizado import CumNormalizado
from app.models.prediccion import PrediccionDesabastecimiento
from app.models.region import Region
from app.services.prediccion import ServicioPrediccion

init_db()


def seleccionar_medicamentos(db, n: int = 200):
    """
    Selecciona n medicamentos activos cubriendo todas las clases ATC,
    priorizando clases con historial de discontinuación para que el mapa
    muestre variación real de riesgo.
    """
    from sqlalchemy import func, text

    # Calcular tasa de inactivación por ATC5 directamente en SQL
    from sqlalchemy import case
    atc5_stats = (
        db.query(
            func.substr(CumNormalizado.atc_normalizado, 1, 5).label("atc5"),
            func.count().label("total"),
            func.sum(case((CumNormalizado.estado_cum == "Inactivo", 1), else_=0)).label("inactivos"),
        )
        .filter(CumNormalizado.atc_normalizado.isnot(None))
        .group_by(func.substr(CumNormalizado.atc_normalizado, 1, 5))
        .subquery()
    )

    # Asignar tasa a cada CUM activo
    high_risk_atc5 = db.execute(
        text("""
            SELECT atc5, CAST(inactivos AS FLOAT)/total as tasa
            FROM (
                SELECT substr(atc_normalizado,1,5) as atc5,
                       COUNT(*) as total,
                       SUM(CASE estado_cum WHEN 'Inactivo' THEN 1 ELSE 0 END) as inactivos
                FROM cum_normalizado
                WHERE atc_normalizado IS NOT NULL AND LENGTH(atc_normalizado)>=5
                GROUP BY substr(atc_normalizado,1,5)
                HAVING total >= 5
            ) ORDER BY tasa DESC LIMIT 50
        """)
    ).fetchall()

    top_atc5 = [r[0] for r in high_risk_atc5]

    # Seleccionar medicamentos de clases de alto riesgo primero
    cums_alto_riesgo = (
        db.query(CumNormalizado)
        .filter(
            CumNormalizado.estado_cum.ilike("activo"),
            CumNormalizado.atc_normalizado.isnot(None),
            CumNormalizado.tipo_formula == "MONO",
        )
        .filter(func.substr(CumNormalizado.atc_normalizado, 1, 5).in_(top_atc5[:20]))
        .order_by(CumNormalizado.expediente_cum)
        .limit(n // 2)
        .all()
    )

    # Completar con medicamentos variados de otras clases ATC
    ya_seleccionados = {f"{c.expediente_cum}-{c.consecutivo_cum}" for c in cums_alto_riesgo}
    n_restantes = n - len(cums_alto_riesgo)

    cums_resto = (
        db.query(CumNormalizado)
        .filter(
            CumNormalizado.estado_cum.ilike("activo"),
            CumNormalizado.atc_normalizado.isnot(None),
            CumNormalizado.tipo_formula == "MONO",
        )
        .filter(~func.substr(CumNormalizado.atc_normalizado, 1, 5).in_(top_atc5[:20]))
        .order_by(CumNormalizado.expediente_cum)
        .limit(n_restantes * 2)
        .all()
    )

    # Deduplicar y combinar
    vistos = set(ya_seleccionados)
    cums_finales = list(cums_alto_riesgo)
    for c in cums_resto:
        key = f"{c.expediente_cum}-{c.consecutivo_cum}"
        if key not in vistos:
            vistos.add(key)
            cums_finales.append(c)
        if len(cums_finales) >= n:
            break

    return cums_finales


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args()

    db = SessionLocal()

    existing = db.query(PrediccionDesabastecimiento).count()
    if existing > 0:
        print(f"Limpiando {existing} predicciones previas...")
        db.query(PrediccionDesabastecimiento).delete()
        db.commit()

    print(f"Seleccionando {args.batch} medicamentos (prioridad: clases ATC de alto riesgo)...")
    cums = seleccionar_medicamentos(db, args.batch)
    print(f"  -> {len(cums)} medicamentos seleccionados")

    n_regiones = db.query(Region).count()
    print(f"Calculando predicciones para {len(cums)} medicamentos × {n_regiones} regiones...")
    servicio = ServicioPrediccion(db)

    t0 = time.time()
    for i, cum in enumerate(cums, 1):
        servicio._predecir_para_cum(cum)
        if i % 20 == 0:
            elapsed = time.time() - t0
            eta = elapsed / i * (len(cums) - i)
            nombre = cum.nombre_comercial_norm or f"{cum.expediente_cum}-{cum.consecutivo_cum}"
            print(f"  {i}/{len(cums)} — {nombre[:40]:<40} ETA: {eta:.0f}s")

    total = db.query(PrediccionDesabastecimiento).count()
    print(f"\nDone. {total:,} predicciones guardadas ({len(cums)} meds × {n_regiones} regiones).")

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
