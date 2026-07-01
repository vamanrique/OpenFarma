"""
Enriquece MedicamentoTransformado con datos normalizados de cum_normalizado y grupos_equivalencia.
Opera con una sola query para toda la lista (sin N+1).
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from etl.transformacion import MedicamentoTransformado
from app.models.cum_normalizado import CumNormalizado
from app.services import grupos_index


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

    # Índice secundario por expediente: para consecutivos no presentes en cum_normalizado,
    # usamos el DCI del primer consecutivo del mismo expediente como fallback.
    expediente_dci: dict[str, list[str]] = {}
    for (exp, _cons), norm in cache.items():
        if norm.principios_dci and exp not in expediente_dci:
            expediente_dci[exp] = norm.principios_dci

    for med in meds:
        norm = cache.get((med.expedientecum, med.consecutivocum))
        if not norm:
            # Fallback: si el mismo expediente tiene DCI conocido en cum_normalizado, usarlo
            fallback_dci = expediente_dci.get(med.expedientecum)
            if fallback_dci:
                med.principios_dci_llm = fallback_dci
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

        # Corrección de concentracion_display para sólidos orales: Socrata a veces reporta
        # "cantidad=1, unidad=U" (significa 1 g) que el ETL convierte a "1 mg" por defecto.
        # Ejemplo: VALTROIS (Valaciclovir 1g) → live="1 mg", LLM sabe "1000 mg".
        # Guard lmg > live_val: solo corregir hacia arriba (LLM con valor en gramos no sobreescribe).
        if (norm.dosis_total_mg is not None
                and med.forma_normalizada in ('TABLETA', 'CAPSULA', 'COMPRIMIDO', None)
                and med.concentracion_display
                and med.concentracion_display.endswith(' mg')
                and len(med.principios_dci) == 1):
            try:
                live_val = float(med.concentracion_display[:-3])
                lmg = float(norm.dosis_total_mg)
                if lmg > 0 and lmg > live_val and abs(lmg - live_val) / max(lmg, live_val) > 0.1:
                    corrected = f"{lmg:g} mg"
                    med.concentracion_display = corrected
                    if med.concentraciones:
                        med.concentraciones = [corrected]
            except (ValueError, TypeError):
                pass

        # Corrección de concentracion_display para líquidos orales (suspensiones/soluciones).
        # Socrata puede entregar "cantidad=5, unidad=U, ref=100 ML" para una suspensión 50 mg/mL
        # (el valor 5 son gramos de benzoato por referencia, no mg).
        # concentracion_mg_ml en cum_normalizado tiene el valor farmacológicamente correcto.
        # Guard lmg > live_val: solo corregir hacia arriba (mismo principio que sólidos).
        if (norm.concentracion_mg_ml is not None
                and med.forma_normalizada in ('SUSPENSION_ORAL', 'SOLUCION_ORAL', 'JARABE',
                                              'ELIXIR', 'LIQUIDO_ORAL')
                and med.concentracion_display
                and med.concentracion_display.endswith(' mg/mL')
                and len(med.principios_dci) == 1):
            try:
                live_val = float(med.concentracion_display[:-6])
                lmg = float(norm.concentracion_mg_ml)
                if lmg > 0 and lmg > live_val and abs(lmg - live_val) / max(lmg, live_val) > 0.1:
                    corrected = f"{lmg:g} mg/mL"
                    med.concentracion_display = corrected
                    if med.concentraciones:
                        med.concentraciones = [corrected]
            except (ValueError, TypeError):
                pass

    # Sobreescribir concentracion_display desde grupos_equivalencia (fuente canónica).
    # Corrige combos incompletos (ej. "2.5 mg" → "GLIBENCLAMIDA 2.5 mg + METFORMINA 500 mg")
    # y cualquier error de parseo live de Socrata. Se aplica al final para tener la última palabra.
    if grupos_index.esta_listo():
        for med in meds:
            ge = grupos_index.buscar(med.cum_id)
            if ge is None:
                continue
            dci_key, conc_norm, _grupo_via = ge
            if not conc_norm or conc_norm == 'SIN_CONCENTRACION':
                continue
            display = grupos_index.concentracion_display(dci_key, conc_norm)
            if display and display != med.concentracion_display:
                med.concentracion_display = display
                partes = [p.strip() for p in conc_norm.split('+')]
                med.concentraciones = partes

    return meds
