"""
Servicio de predicción de desabastecimiento.
Usa cum_normalizado como fuente de verdad en lugar del viejo modelo Medicamento.
"""
import numpy as np
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, text

from app.models.cum_normalizado import CumNormalizado
from app.models.reporte import ReporteNoDisponibilidad
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

    cum_key = f"{cum.expediente_cum}-{cum.consecutivo_cum}"
    n_reportes = db.query(func.count(ReporteNoDisponibilidad.id)).filter(
        ReporteNoDisponibilidad.cum_id == cum_key
    ).scalar() or 0
    reportes_norm = min(float(n_reportes) / 20.0, 1.0)

    try:
        n_busquedas = db.execute(text(
            "SELECT COUNT(*) FROM busquedas_log "
            "WHERE cum_id=:cid AND fecha > datetime('now', '-30 days')"
        ), {"cid": cum_key}).scalar() or 0
    except Exception:
        n_busquedas = 0
    busquedas_norm = min(float(n_busquedas) / 100.0, 1.0)

    base = np.array([
        tasa_inactivacion,
        n_competidores,
        int(n_competidores > 1),
        tipo_num,
        int(tipo_num > 1),
        int(n_competidores == 1),
        grupo_atc_enc,
        n_presentaciones,
        busquedas_norm,
        reportes_norm,
    ])

    inv = _invima_features_para_atc(cum.atc_normalizado or "", db)
    return np.concatenate([base, inv])


_NIVEL_NUM = {"bajo": 1, "medio": 2, "alto": 3, "critico": 4}
_NIVEL_LABEL = {"bajo": "Bajo", "medio": "Medio", "alto": "Alto", "critico": "Crítico"}


def predecir_nacional(cum_id: str, db: Session) -> dict | None:
    """Predicción a nivel nacional (sin dimensión regional) para un CUM dado."""
    partes = cum_id.split("-", 1)
    if len(partes) != 2:
        return None
    cum = db.query(CumNormalizado).filter(
        CumNormalizado.expediente_cum == partes[0],
        CumNormalizado.consecutivo_cum == partes[1],
    ).first()
    if not cum:
        return None

    features = _features_base_para_cum(cum, db)

    prob: float
    if MODEL_PATH.exists():
        from app.ml.modelo import cargar_modelo
        artefacto = cargar_modelo()
        modelo = artefacto.get("modelo")
        if modelo:
            prob = float(modelo.predict_proba([features])[0][1])
        else:
            prob = min(float(features[0]) * 0.5 + float(features[9]) * 0.05, 1.0)
    else:
        prob = min(float(features[0]) * 0.5 + float(features[9]) * 0.05, 1.0)

    nivel_raw = clasificar_nivel(prob)
    features_dict = {col: round(float(features[i]), 4) for i, col in enumerate(FEATURE_COLS)}

    return {
        "cum_id": cum_id,
        "probabilidad": round(prob, 4),
        "nivel_riesgo": _NIVEL_LABEL.get(nivel_raw, nivel_raw.capitalize()),
        "nivel_num": _NIVEL_NUM.get(nivel_raw, 0),
        "features_principales": {
            k: v for k, v in sorted(features_dict.items(), key=lambda x: -abs(x[1]))[:5]
        },
        "modelo_version": "1.0.0",
        "fecha_prediccion": datetime.now().strftime("%Y-%m-%d"),
    }
