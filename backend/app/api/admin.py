from fastapi import APIRouter
from pathlib import Path
import csv

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent / "data"


@router.get("/validacion/reporte")
def reporte_validacion():
    ruta = DATA_DIR / "validacion_reporte.csv"
    if not ruta.exists():
        return {"mensaje": "Reporte no disponible. Ejecuta el ETL primero.", "registros": []}

    registros = []
    with open(ruta, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            registros.append(row)

    resumen: dict[str, dict] = {}
    for r in registros:
        regla = r["regla"]
        if regla not in resumen:
            resumen[regla] = {"regla": regla, "severidad": r["severidad"], "descripcion": r["descripcion"], "total": 0}
        resumen[regla]["total"] += 1

    return {
        "total_problemas": len(registros),
        "resumen_por_regla": list(resumen.values()),
        "detalle": registros[:200],
    }


@router.get("/estadisticas/db")
def estadisticas_db():
    from app.database import SessionLocal
    from app.models.medicamento import Medicamento, Alternativa
    from app.models.region import Region

    db = SessionLocal()
    try:
        return {
            "medicamentos": db.query(Medicamento).count(),
            "medicamentos_vigentes": db.query(Medicamento).filter(Medicamento.estado == "vigente").count(),
            "alternativas": db.query(Alternativa).count(),
            "regiones": db.query(Region).count(),
        }
    finally:
        db.close()
