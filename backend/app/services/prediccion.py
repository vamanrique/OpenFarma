"""
Servicio de predicción de desabastecimiento.
Usa cum_normalizado como fuente de verdad en lugar del viejo modelo Medicamento.
"""
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, text

from app.models.region import ConsultaRegion, Region
from app.models.prediccion import PrediccionDesabastecimiento
from app.models.cum_normalizado import CumNormalizado
from app.ml.modelo import clasificar_nivel, MODEL_PATH
from app.ml.features import FEATURE_COLS, INVIMA_SEV_SCORE

ATC_GRUPOS = list("ABCDEFGHJLMNPRSV")
_ATC_ENC = {g: i for i, g in enumerate(ATC_GRUPOS)}
TIPO_NUM = {
    "monocomponente": 1, "biconjugado": 2, "triconjugado": 3, "tetraconjugado": 4,
    "MONO": 1, "BI": 2, "TRI": 3, "TETRA": 4,
}


def _invima_features_para_atc(atc: str, db: Session) -> np.ndarray:
    """Computa las 5 features INVIMA para un ATC7 dado usando el historial en DB."""
    if not atc:
        return np.zeros(5)

    from app.services import invima_service

    # Severidad actual desde el cache en memoria (mes más reciente)
    ei = invima_service.estado_actual(atc)
    sev_actual = float(INVIMA_SEV_SCORE.get(ei.estado if ei else None, 0))

    # Historial desde DB (últimos 6 meses, ordenados desc)
    hist = db.execute(text("""
        SELECT anio*100+mes AS period,
               MAX(CASE estado
                   WHEN 'DESABASTECIDO'     THEN 5
                   WHEN 'EN_RIESGO'         THEN 4
                   WHEN 'EN_MONITORIZACION' THEN 3
                   WHEN 'NO_COMERCIALIZADO' THEN 2
                   WHEN 'DESCONTINUADO'     THEN 1
                   ELSE 0 END) AS sev
        FROM invima_seguimiento
        WHERE (atc = :atc OR atc LIKE :atc5)
        GROUP BY period
        ORDER BY period DESC
        LIMIT 17
    """), {"atc": atc, "atc5": atc[:5] + "%"}).fetchall()

    if not hist:
        return np.array([sev_actual, 0.0, 0, sev_actual, 0.0])

    sevs = [float(r[1] or 0) for r in hist]
    meses_mon = len(sevs)
    peor_hist = max(sevs)
    recent3   = sevs[:3]
    prev3     = sevs[3:6]
    sev_t3    = float(np.mean(recent3)) if recent3 else 0.0
    tendencia = float(np.mean(recent3) - np.mean(prev3)) if recent3 and prev3 else 0.0

    return np.array([sev_actual, sev_t3, meses_mon, peor_hist, tendencia])


def _features_base_para_cum(cum: CumNormalizado, db: Session) -> np.ndarray:
    """Computa las 15 features (10 CUM + 5 INVIMA) independientes de la región."""
    atc5 = (cum.atc_normalizado or "")[:5]
    if atc5:
        total_atc5 = db.query(func.count()).select_from(CumNormalizado).filter(
            CumNormalizado.atc_normalizado.like(f"{atc5}%")
        ).scalar() or 1
        inactivos_atc5 = db.query(func.count()).select_from(CumNormalizado).filter(
            CumNormalizado.atc_normalizado.like(f"{atc5}%"),
            CumNormalizado.estado_cum.ilike("inactivo"),
        ).scalar() or 0
        tasa_inactivacion = inactivos_atc5 / total_atc5
    else:
        tasa_inactivacion = 0.3

    n_competidores = 1
    if cum.forma_normalizada:
        n_competidores = db.query(func.count(distinct(CumNormalizado.titular_registro))).filter(
            CumNormalizado.forma_normalizada == cum.forma_normalizada,
            CumNormalizado.estado_cum.ilike("activo"),
        ).scalar() or 1
        n_competidores = max(1, min(int(n_competidores), 100))

    n_presentaciones = db.query(func.count()).select_from(CumNormalizado).filter(
        CumNormalizado.expediente_cum == cum.expediente_cum,
        CumNormalizado.estado_cum.ilike("activo"),
    ).scalar() or 1

    tipo_num = TIPO_NUM.get(cum.tipo_formula or "monocomponente", 1)
    atc_char = (cum.atc_normalizado or "?")[0].upper()
    grupo_atc_enc = _ATC_ENC.get(atc_char, len(ATC_GRUPOS))

    base = np.array([
        tasa_inactivacion,
        n_competidores,
        int(n_competidores > 1),
        tipo_num,
        int(tipo_num > 1),
        int(n_competidores == 1),
        grupo_atc_enc,
        n_presentaciones,
        0.0,   # busquedas_norm
        0.0,   # reportes_norm
    ])

    inv = _invima_features_para_atc(cum.atc_normalizado or "", db)
    return np.concatenate([base, inv])


def _features_con_region(base: np.ndarray, cum_key: str, region_id: int, db: Session) -> np.ndarray:
    """Añade señales regionales a las features base. Rápido si no hay consultas."""
    busquedas = (
        db.query(func.sum(ConsultaRegion.conteo))
        .filter(ConsultaRegion.cum_id == cum_key, ConsultaRegion.region_id == region_id,
                ConsultaRegion.tipo == "busqueda")
        .scalar() or 0
    )
    reportes = (
        db.query(func.sum(ConsultaRegion.conteo))
        .filter(ConsultaRegion.cum_id == cum_key, ConsultaRegion.region_id == region_id,
                ConsultaRegion.tipo == "reporte_no_disponibilidad")
        .scalar() or 0
    )
    row = base.copy()
    row[8] = min(float(busquedas) / 100.0, 1.0)
    row[9] = min(float(reportes) / 10.0, 1.0)
    return row


class ServicioPrediccion:
    def __init__(self, db: Session):
        self.db = db
        self._modelo = None

    def _obtener_modelo(self):
        if self._modelo is None and MODEL_PATH.exists():
            from app.ml.modelo import cargar_modelo
            self._modelo = cargar_modelo()
        return self._modelo

    def predecir_cum(self, cum_id: str) -> list[dict]:
        partes = cum_id.split("-", 1)
        if len(partes) != 2:
            return []
        cum = self.db.query(CumNormalizado).filter(
            CumNormalizado.expediente_cum == partes[0],
            CumNormalizado.consecutivo_cum == partes[1],
        ).first()
        if not cum:
            return []
        return self._predecir_para_cum(cum)

    def _predecir_para_cum(self, cum: CumNormalizado) -> list[dict]:
        regiones = self.db.query(Region).all()
        modelo = self._obtener_modelo()
        cum_id = f"{cum.expediente_cum}-{cum.consecutivo_cum}"
        nombre = cum.nombre_comercial_norm or cum_id

        # Pre-computar features base (independientes de región)
        base = _features_base_para_cum(cum, self.db)

        # Construir matriz (n_regiones × n_features) para un solo predict_proba batch
        features_matrix = np.array([
            _features_con_region(base, cum_id, region.id, self.db)
            for region in regiones
        ])

        if modelo:
            probas = modelo["modelo"].predict_proba(features_matrix)[:, 1]
        else:
            tasa = float(base[0])
            probas = np.array([
                min(tasa * 0.5 + float(features_matrix[i, 9]) * 0.05, 1.0)
                for i in range(len(regiones))
            ])

        self.db.query(PrediccionDesabastecimiento).filter(
            PrediccionDesabastecimiento.cum_id == cum_id
        ).delete()

        resultados = []
        for i, region in enumerate(regiones):
            proba = float(probas[i])
            nivel = clasificar_nivel(proba)
            pred = PrediccionDesabastecimiento(
                cum_id=cum_id,
                medicamento_nombre=nombre,
                region_id=region.id,
                probabilidad=proba,
                nivel_riesgo=nivel,
                horizonte_dias=30,
            )
            self.db.add(pred)
            resultados.append({"cum_id": cum_id, "region_id": region.id,
                                "probabilidad": proba, "nivel_riesgo": nivel})

        self.db.commit()
        return resultados
