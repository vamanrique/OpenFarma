"""
Servicio de predicción que usa el modelo ML entrenado.
Cuando el modelo no existe, devuelve predicciones heurísticas como fallback.
"""
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.models.region import ConsultaRegion, Region
from app.models.prediccion import PrediccionDesabastecimiento
from app.ml.modelo import clasificar_nivel, MODEL_PATH
from app.ml.features import FEATURE_COLS


def _features_para_medicamento(medicamento_id: int, region_id: int, db: Session) -> np.ndarray:
    """Construye el vector de features para un (medicamento, región) desde la DB."""
    from app.models.medicamento import Medicamento

    med = db.query(Medicamento).filter(Medicamento.id == medicamento_id).first()
    if not med:
        return np.zeros((1, len(FEATURE_COLS)))

    busquedas = (
        db.query(func.count(ConsultaRegion.id))
        .filter(
            ConsultaRegion.medicamento_id == medicamento_id,
            ConsultaRegion.region_id == region_id,
            ConsultaRegion.tipo == "busqueda",
        )
        .scalar() or 0
    )
    reportes = (
        db.query(func.count(ConsultaRegion.id))
        .filter(
            ConsultaRegion.medicamento_id == medicamento_id,
            ConsultaRegion.region_id == region_id,
            ConsultaRegion.tipo == "reporte_no_disponibilidad",
        )
        .scalar() or 0
    )

    tipo_num = {"monocomponente": 1, "biconjugado": 2, "triconjugado": 3, "tetraconjugado": 4}
    ATC_GRUPOS = list("ABCDEFGHJLMNPRSV")
    atc_enc = ATC_GRUPOS.index(med.codigo_atc[0]) if med.codigo_atc and med.codigo_atc[0] in ATC_GRUPOS else len(ATC_GRUPOS)

    n_alternativas = (
        db.query(func.count())
        .select_from(__import__("app.models.medicamento", fromlist=["Alternativa"]).Alternativa)
        .filter_by(medicamento_id=medicamento_id)
        .scalar() or 0
    )

    features = np.array([[
        0.3,                                                    # tasa_inactivacion_atc5 (sin DB completa)
        max(1, n_alternativas),                                 # num_competidores proxy
        int(n_alternativas > 0),                                # tiene_alternativas
        tipo_num.get(med.tipo_formula or "monocomponente", 1),  # tipo_formula_num
        int((med.tipo_formula or "mono") != "monocomponente"),  # es_combinado
        int(n_alternativas == 0),                               # monopolio
        atc_enc,                                                # grupo_atc_enc
        1,                                                      # num_presentaciones_activas
        min(busquedas / 100.0, 1.0),                            # busquedas_norm
        min(reportes / 10.0, 1.0),                              # reportes_norm
    ]])
    return features


class ServicioPrediccion:
    def __init__(self, db: Session):
        self.db = db
        self._modelo = None

    def _obtener_modelo(self):
        if self._modelo is None and MODEL_PATH.exists():
            from app.ml.modelo import cargar_modelo
            self._modelo = cargar_modelo()
        return self._modelo

    def predecir(self, medicamento_id: int) -> list[dict]:
        regiones = self.db.query(Region).all()
        modelo = self._obtener_modelo()
        resultados = []

        for region in regiones:
            features = _features_para_medicamento(medicamento_id, region.id, self.db)

            if modelo:
                proba = float(modelo["modelo"].predict_proba(features)[0, 1])
            else:
                # Heurística fallback cuando el modelo aún no está entrenado
                busquedas = float(features[0, 8]) * 100
                reportes = float(features[0, 9]) * 10
                proba = min((reportes * 0.4 + busquedas * 0.005) / 10, 1.0)

            nivel = clasificar_nivel(proba)

            pred = PrediccionDesabastecimiento(
                medicamento_id=medicamento_id,
                region_id=region.id,
                probabilidad=proba,
                nivel_riesgo=nivel,
                horizonte_dias=30,
                factores={
                    "modelo_activo": modelo is not None,
                    "busquedas": int(float(features[0, 8]) * 100),
                    "reportes": int(float(features[0, 9]) * 10),
                },
                fecha_prediccion=datetime.now(),
            )
            self.db.add(pred)
            resultados.append({"region_id": region.id, "probabilidad": proba, "nivel": nivel})

        self.db.commit()
        return resultados
