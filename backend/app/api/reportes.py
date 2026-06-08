from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models.region import ConsultaRegion
from app.models.reporte import ReporteNoDisponibilidad

router = APIRouter()


class ReportePayload(BaseModel):
    cum_id: str
    region_id: int
    tipo_reporte: str = "sin_stock"  # sin_stock, precio_alto, sin_suministro
    descripcion: Optional[str] = None


@router.post("/no-disponibilidad")
def reportar_no_disponibilidad(reporte: ReportePayload, db: Session = Depends(get_db)):
    from app.models.cum_normalizado import CumNormalizado

    partes = reporte.cum_id.split("-", 1)
    nombre = reporte.cum_id
    if len(partes) == 2:
        cache = db.query(CumNormalizado).filter(
            CumNormalizado.expediente_cum == partes[0],
            CumNormalizado.consecutivo_cum == partes[1],
        ).first()
        if cache:
            nombre = cache.nombre_comercial

    registro = ReporteNoDisponibilidad(
        cum_id=reporte.cum_id,
        nombre_medicamento=nombre,
        region_id=reporte.region_id,
        tipo_reporte=reporte.tipo_reporte,
        descripcion=reporte.descripcion,
        fecha=datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return {"mensaje": "Reporte registrado exitosamente", "id": registro.id}


@router.get("/recientes")
def reportes_recientes(limit: int = 10, db: Session = Depends(get_db)):
    rows = (
        db.query(ReporteNoDisponibilidad)
        .order_by(ReporteNoDisponibilidad.fecha.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "cum_id": r.cum_id,
            "nombre_medicamento": r.nombre_medicamento,
            "region_nombre": r.region.nombre if r.region else str(r.region_id),
            "tipo_reporte": r.tipo_reporte,
            "descripcion": r.descripcion,
            "fecha": r.fecha.isoformat() if r.fecha else None,
        }
        for r in rows
    ]


@router.get("/total")
def total_reportes(db: Session = Depends(get_db)):
    total = db.query(func.count(ReporteNoDisponibilidad.id)).scalar() or 0
    por_tipo = (
        db.query(ReporteNoDisponibilidad.tipo_reporte, func.count(ReporteNoDisponibilidad.id))
        .group_by(ReporteNoDisponibilidad.tipo_reporte)
        .all()
    )
    return {"total": total, "por_tipo": {t: c for t, c in por_tipo}}


@router.get("/estadisticas/{region_id}")
def estadisticas_region(region_id: int, db: Session = Depends(get_db)):
    stats = (
        db.query(
            ConsultaRegion.cum_id,
            ConsultaRegion.tipo,
            func.count(ConsultaRegion.id).label("total"),
        )
        .filter(ConsultaRegion.region_id == region_id)
        .group_by(ConsultaRegion.cum_id, ConsultaRegion.tipo)
        .all()
    )
    return [{"cum_id": s.cum_id, "tipo": s.tipo, "total": s.total} for s in stats]
