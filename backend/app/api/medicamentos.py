from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional

from app.database import get_db
from app.models.medicamento import Medicamento, Alternativa
from app.schemas.medicamento import MedicamentoRead, AlternativaRead, MedicamentoLiveRead, AlternativaLiveRead
from app.services import cum_live

router = APIRouter()


@router.get("/buscar", response_model=List[MedicamentoLiveRead])
async def buscar_medicamentos(
    q: str = Query(..., min_length=2),
    solo_activos: bool = Query(True),
    limit: int = Query(20, le=100),
):
    """Busca en el JSON online de datos.gov.co en tiempo real."""
    meds = await cum_live.buscar_medicamentos(q, solo_activos=solo_activos, limit=limit * 10)
    vistos: set[str] = set()
    unicos = []
    for m in meds:
        if m.cum_id not in vistos:
            vistos.add(m.cum_id)
            unicos.append(MedicamentoLiveRead(
                cum_id=m.cum_id,
                nombre_comercial=m.nombre_comercial,
                principios_dci=m.principios_dci,
                tipo_formula=m.tipo_formula,
                concentracion_display=m.concentracion_display,
                forma_farmaceutica=m.forma_farmaceutica,
                via_administracion=m.via_administracion,
                atc=m.atc,
                descripcion_atc=m.descripcion_atc,
                laboratorio=m.laboratorio,
                registro_sanitario=m.registro_sanitario,
                estado_registro=m.estado_registro,
                estado_cum=m.estado_cum,
            ))
        if len(unicos) >= limit:
            break
    return unicos


@router.get("/{cum_id}/alternativas", response_model=List[AlternativaLiveRead])
async def obtener_alternativas_live(cum_id: str):
    """Calcula alternativas en tiempo real desde el JSON online."""
    partes = cum_id.split("-", 1)
    if len(partes) != 2:
        raise HTTPException(status_code=400, detail="Formato de CUM inválido. Use expedientecum-consecutivocum")

    med = await cum_live.obtener_por_cum(partes[0], partes[1])
    if not med:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado en la API")

    pares = await cum_live.alternativas_para(med)

    # Enriquecer con datos del medicamento destino (ya disponibles en los grupos)
    resultado: list[AlternativaLiveRead] = []
    for p in pares:
        cum_destino = p.cum_destino if p.cum_origen == cum_id else p.cum_origen
        partes_dest = cum_destino.split("-", 1)
        med_dest = None
        if len(partes_dest) == 2:
            med_dest_obj = await cum_live.obtener_por_cum(partes_dest[0], partes_dest[1])
            if med_dest_obj:
                med_dest = MedicamentoLiveRead(
                    cum_id=med_dest_obj.cum_id,
                    nombre_comercial=med_dest_obj.nombre_comercial,
                    principios_dci=med_dest_obj.principios_dci,
                    tipo_formula=med_dest_obj.tipo_formula,
                    concentracion_display=med_dest_obj.concentracion_display,
                    forma_farmaceutica=med_dest_obj.forma_farmaceutica,
                    via_administracion=med_dest_obj.via_administracion,
                    atc=med_dest_obj.atc,
                    descripcion_atc=med_dest_obj.descripcion_atc,
                    laboratorio=med_dest_obj.laboratorio,
                    registro_sanitario=med_dest_obj.registro_sanitario,
                    estado_registro=med_dest_obj.estado_registro,
                    estado_cum=med_dest_obj.estado_cum,
                )
        resultado.append(AlternativaLiveRead(
            cum_origen=p.cum_origen,
            cum_destino=p.cum_destino,
            tipo=p.tipo,
            descripcion=p.descripcion,
            componentes_compartidos=p.componentes_compartidos,
            medicamento_destino=med_dest,
        ))

    return resultado


# Endpoint de DB local (para cuando se haya cargado el ETL completo)
@router.get("/db/buscar", response_model=List[MedicamentoRead])
def buscar_en_db(
    q: str = Query(..., min_length=2),
    tipo_formula: Optional[str] = Query(None),
    solo_vigentes: bool = Query(True),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    filtros = [
        or_(
            Medicamento.nombre_comercial.ilike(f"%{q}%"),
            Medicamento.nombre_generico.ilike(f"%{q}%"),
            Medicamento.principio_activo.ilike(f"%{q}%"),
            Medicamento.cum.ilike(f"%{q}%"),
        )
    ]
    if solo_vigentes:
        filtros.append(Medicamento.estado == "vigente")
        filtros.append(Medicamento.estado_cum == "activo")
    if tipo_formula:
        filtros.append(Medicamento.tipo_formula == tipo_formula)
    return db.query(Medicamento).filter(and_(*filtros)).limit(limit).all()


@router.get("/db/{medicamento_id}/alternativas", response_model=List[AlternativaRead])
def alternativas_db(medicamento_id: int, db: Session = Depends(get_db)):
    return db.query(Alternativa).filter(Alternativa.medicamento_id == medicamento_id).all()
