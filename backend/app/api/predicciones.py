from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter()


@router.get("/modelo/info")
def info_modelo():
    from app.ml.modelo import MODEL_PATH
    if not MODEL_PATH.exists():
        raise HTTPException(status_code=404, detail="Modelo no entrenado aún. Ejecuta el entrenamiento.")
    from app.ml.modelo import cargar_modelo
    try:
        artefacto = cargar_modelo()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error cargando el modelo: {exc}")
    metricas = artefacto.get("metricas", {})

    importancias = []
    try:
        base_rf = artefacto["modelo"].calibrated_classifiers_[0].estimator
        from app.ml.features import FEATURE_COLS
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


@router.get("/{cum_id:path}")
def prediccion_medicamento(cum_id: str, db: Session = Depends(get_db)):
    """Predicción nacional de riesgo de desabastecimiento para un medicamento (mes siguiente)."""
    from app.services.prediccion import predecir_nacional
    result = predecir_nacional(cum_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado en el CUM")
    return result
