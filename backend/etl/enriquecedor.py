"""
Enriquece MedicamentoTransformado con datos normalizados por LLM del caché cum_normalizado.
Opera con una sola query para toda la lista (sin N+1).
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from etl.transformacion import MedicamentoTransformado
from app.models.cum_normalizado import CumNormalizado


def enriquecer_con_llm(
    meds: list[MedicamentoTransformado],
    db: Session,
) -> list[MedicamentoTransformado]:
    if not meds:
        return meds

    pares = [(m.expedientecum, m.consecutivocum) for m in meds]
    conditions = or_(*[
        and_(CumNormalizado.expediente_cum == e, CumNormalizado.consecutivo_cum == c)
        for e, c in pares
    ])
    rows = db.query(CumNormalizado).filter(conditions).all()
    cache: dict[tuple[str, str], CumNormalizado] = {
        (r.expediente_cum, r.consecutivo_cum): r for r in rows
    }

    for med in meds:
        norm = cache.get((med.expedientecum, med.consecutivocum))
        if not norm:
            continue
        if norm.principios_dci:
            med.principios_dci_llm = norm.principios_dci
        med.dosis_total_mg         = norm.dosis_total_mg
        med.concentracion_mg_ml    = norm.concentracion_mg_ml
        med.volumen_ml_por_unidad  = norm.volumen_ml_por_unidad
        med.forma_normalizada      = norm.forma_normalizada
        med.via_normalizada        = norm.via_normalizada
        med.atc_llm                = norm.atc_normalizado
        med.tipo_formula_llm       = norm.tipo_formula
        med.componentes_llm        = norm.componentes or []
        med.notas_llm              = norm.notas

    return meds
