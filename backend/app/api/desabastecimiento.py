"""
Endpoints para datos INVIMA de seguimiento de abastecimiento.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.medicamento import EstadoInvimaRead
from app.services import invima_service

router = APIRouter()


@router.get("/actual", response_model=List[EstadoInvimaRead])
def listado_actual(
    estado: Optional[str] = Query(None, description="Filtrar por estado: DESABASTECIDO, EN_RIESGO, EN_MONITORIZACION, NO_COMERCIALIZADO, DESCONTINUADO"),
    db: Session = Depends(get_db),
):
    """Listado de medicamentos bajo seguimiento INVIMA (mes más reciente)."""
    from sqlalchemy import text
    cache = invima_service._cache
    if not cache.listo:
        return []

    estados_filtro = {estado} if estado else {
        "DESABASTECIDO", "EN_RIESGO", "EN_MONITORIZACION",
        "NO_COMERCIALIZADO", "DESCONTINUADO",
    }

    seen: set[str] = set()
    resultado: list[EstadoInvimaRead] = []
    for eis in cache.por_atc7.values():
        for ei in eis:
            if ei.estado not in estados_filtro:
                continue
            key = f"{ei.principio_activo}|{ei.forma}|{ei.concentracion}"
            if key in seen:
                continue
            seen.add(key)
            resultado.append(EstadoInvimaRead(**ei.to_dict()))

    resultado.sort(key=lambda x: (-invima_service.ORDEN_SEVERIDAD.get(x.estado, 0), x.principio_activo))
    return resultado


@router.get("/historico", response_model=List[dict])
def historico_atc(
    atc: str = Query(..., min_length=5, description="Código ATC (mínimo 5 chars)"),
    db: Session = Depends(get_db),
):
    """Historial mensual de estados INVIMA para un código ATC."""
    return invima_service.historico_desde_db(atc, db)


@router.get("/resumen")
def resumen_actual():
    """Resumen estadístico del mes más reciente."""
    cache = invima_service._cache
    if not cache.listo:
        return {"disponible": False}

    counts: dict[str, int] = {}
    for eis in cache.por_atc7.values():
        for ei in eis:
            counts[ei.estado] = counts.get(ei.estado, 0) + 1

    return {
        "disponible": True,
        "mes": cache.mes,
        "anio": cache.anio,
        "por_estado": counts,
        "total": sum(counts.values()),
    }
