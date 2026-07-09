from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from app.database import get_db
from app.models.reporte import ReporteNoDisponibilidad

router = APIRouter()


class ReportePayload(BaseModel):
    cum_id: str
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


@router.get("/dashboard")
def dashboard_alertas(db: Session = Depends(get_db)):
    """
    Dashboard de vigilancia ciudadana: medicamentos con más reportes recientes
    y detección de spikes (señal anticipada respecto al INVIMA).
    """
    ahora = datetime.now()
    hace_30d = ahora - timedelta(days=30)
    hace_7d  = ahora - timedelta(days=7)
    hace_1d  = ahora - timedelta(days=1)

    # Top 20 medicamentos con más reportes en 30 días
    top_30d = (
        db.query(
            ReporteNoDisponibilidad.cum_id,
            ReporteNoDisponibilidad.nombre_medicamento,
            func.count(ReporteNoDisponibilidad.id).label("total_30d"),
        )
        .filter(ReporteNoDisponibilidad.fecha >= hace_30d)
        .group_by(ReporteNoDisponibilidad.cum_id, ReporteNoDisponibilidad.nombre_medicamento)
        .order_by(func.count(ReporteNoDisponibilidad.id).desc())
        .limit(20)
        .all()
    )

    # Conteos últimos 7 días para calcular spike
    conteos_7d: dict[str, int] = {}
    rows_7d = (
        db.query(
            ReporteNoDisponibilidad.cum_id,
            func.count(ReporteNoDisponibilidad.id).label("c7d"),
        )
        .filter(ReporteNoDisponibilidad.fecha >= hace_7d)
        .group_by(ReporteNoDisponibilidad.cum_id)
        .all()
    )
    for r in rows_7d:
        conteos_7d[r.cum_id] = r.c7d

    # Conteos últimas 24h
    conteos_1d: dict[str, int] = {}
    rows_1d = (
        db.query(
            ReporteNoDisponibilidad.cum_id,
            func.count(ReporteNoDisponibilidad.id).label("c1d"),
        )
        .filter(ReporteNoDisponibilidad.fecha >= hace_1d)
        .group_by(ReporteNoDisponibilidad.cum_id)
        .all()
    )
    for r in rows_1d:
        conteos_1d[r.cum_id] = r.c1d

    # Cruce con INVIMA: identificar cuáles NO tienen alerta INVIMA (señal anticipada)
    from app.services import invima_service
    from app.models.cum_normalizado import CumNormalizado

    resultado = []
    for row in top_30d:
        cum = db.query(CumNormalizado).filter(
            CumNormalizado.expediente_cum == row.cum_id.split("-")[0],
            CumNormalizado.consecutivo_cum == row.cum_id.split("-")[1] if "-" in row.cum_id else "1",
        ).first()

        atc = cum.atc_normalizado if cum else None
        estado_invima = invima_service.estado_actual(atc)
        c7d = conteos_7d.get(row.cum_id, 0)
        c1d = conteos_1d.get(row.cum_id, 0)

        # Spike: reportes hoy vs promedio diario últimos 7 días
        prom_diario_7d = c7d / 7.0
        spike_ratio = round(c1d / prom_diario_7d, 1) if prom_diario_7d > 0 else (1.0 if c1d == 0 else 5.0)

        resultado.append({
            "cum_id": row.cum_id,
            "nombre_medicamento": row.nombre_medicamento,
            "total_30d": row.total_30d,
            "total_7d": c7d,
            "total_1d": c1d,
            "spike_ratio": spike_ratio,
            "tiene_alerta_invima": estado_invima is not None,
            "severidad_invima": estado_invima.to_dict() if estado_invima else None,
            "senal_anticipada": c7d >= 3 and estado_invima is None,
        })

    total_global = db.query(func.count(ReporteNoDisponibilidad.id)).scalar() or 0
    total_30d_sum = sum(r["total_30d"] for r in resultado)
    senales_anticipadas = [r for r in resultado if r["senal_anticipada"]]

    return {
        "resumen": {
            "total_reportes_historico": total_global,
            "total_reportes_30d": total_30d_sum,
            "medicamentos_con_spike": len([r for r in resultado if r["spike_ratio"] >= 2.0]),
            "senales_anticipadas": len(senales_anticipadas),
        },
        "top_reportados": resultado,
        "senales_anticipadas": senales_anticipadas[:5],
    }


