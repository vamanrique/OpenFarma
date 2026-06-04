from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.prediccion import PrediccionDesabastecimiento
from app.schemas.prediccion import PrediccionRead
from app.services.prediccion import ServicioPrediccion

router = APIRouter()


@router.get("/mapa")
def mapa_riesgo(
    nivel_riesgo: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(PrediccionDesabastecimiento)
    if nivel_riesgo:
        query = query.filter(PrediccionDesabastecimiento.nivel_riesgo == nivel_riesgo)

    return [
        {
            "region_id": p.region_id,
            "medicamento_id": p.medicamento_id,
            "probabilidad": p.probabilidad,
            "nivel_riesgo": p.nivel_riesgo,
            "latitud": p.region.latitud if p.region else None,
            "longitud": p.region.longitud if p.region else None,
            "region_nombre": p.region.nombre if p.region else None,
            "medicamento_nombre": p.medicamento.nombre_generico if p.medicamento else None,
        }
        for p in query.all()
    ]


@router.get("/mapa/resumen")
def resumen_mapa(db: Session = Depends(get_db)):
    """Conteo de predicciones por nivel de riesgo para el dashboard."""
    from sqlalchemy import func
    rows = (
        db.query(
            PrediccionDesabastecimiento.nivel_riesgo,
            func.count(PrediccionDesabastecimiento.id).label("total"),
            func.avg(PrediccionDesabastecimiento.probabilidad).label("prob_media"),
        )
        .group_by(PrediccionDesabastecimiento.nivel_riesgo)
        .all()
    )
    return [{"nivel": r.nivel_riesgo, "total": r.total, "prob_media": round(r.prob_media, 3)} for r in rows]


@router.get("/medicamento/{medicamento_id}", response_model=list[PrediccionRead])
def predicciones_por_medicamento(medicamento_id: int, db: Session = Depends(get_db)):
    return (
        db.query(PrediccionDesabastecimiento)
        .filter(PrediccionDesabastecimiento.medicamento_id == medicamento_id)
        .all()
    )


@router.post("/calcular/{medicamento_id}")
def calcular_prediccion(medicamento_id: int, db: Session = Depends(get_db)):
    servicio = ServicioPrediccion(db)
    return servicio.predecir(medicamento_id)


@router.post("/calcular-todos")
def calcular_todos(db: Session = Depends(get_db)):
    """Corre el modelo para todos los medicamentos en la DB."""
    from app.models.medicamento import Medicamento
    meds = db.query(Medicamento.id).filter(Medicamento.estado == "vigente").limit(500).all()
    servicio = ServicioPrediccion(db)
    total = 0
    for (med_id,) in meds:
        servicio.predecir(med_id)
        total += 1
    return {"mensaje": f"Predicciones calculadas para {total} medicamentos"}


@router.get("/modelo/info")
def info_modelo():
    """Expone métricas y feature importances del modelo entrenado."""
    from app.ml.modelo import MODEL_PATH
    if not MODEL_PATH.exists():
        raise HTTPException(status_code=404, detail="Modelo no entrenado aún. Ejecuta el entrenamiento.")
    from app.ml.modelo import cargar_modelo, FEATURE_COLS
    artefacto = cargar_modelo()
    metricas = artefacto.get("metricas", {})

    importancias = []
    try:
        base_rf = artefacto["modelo"].calibrated_classifiers_[0].estimator
        for feat, imp in sorted(
            zip(FEATURE_COLS, base_rf.feature_importances_), key=lambda x: -x[1]
        ):
            importancias.append({"feature": feat, "importancia": round(float(imp), 4)})
    except Exception:
        pass

    return {
        "roc_auc": metricas.get("roc_auc"),
        "avg_precision": metricas.get("avg_precision"),
        "n_train": metricas.get("n_train"),
        "tasa_positivos": metricas.get("pos_rate_train"),
        "importancia_features": importancias,
    }
