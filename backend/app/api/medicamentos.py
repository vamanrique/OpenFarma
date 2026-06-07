import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional

from app.database import get_db
from app.models.medicamento import Medicamento, Alternativa
from app.schemas.medicamento import MedicamentoRead, AlternativaRead, MedicamentoLiveRead, AlternativaLiveRead
from app.services import cum_live
from etl.enriquecedor import enriquecer_con_llm
from etl.transformacion import MedicamentoTransformado

router = APIRouter()


def _to_live_read(m: MedicamentoTransformado) -> MedicamentoLiveRead:
    return MedicamentoLiveRead(
        cum_id=m.cum_id,
        nombre_comercial=m.nombre_comercial,
        principios_dci=m.principios_dci_llm or m.principios_dci,
        tipo_formula=m.tipo_formula,
        concentracion_display=m.concentracion_display,
        presentacion=m.presentacion,
        forma_farmaceutica=m.forma_farmaceutica,
        via_administracion=m.via_administracion,
        atc=m.atc_llm or m.atc,
        descripcion_atc=m.descripcion_atc,
        laboratorio=m.laboratorio,
        registro_sanitario=m.registro_sanitario,
        estado_registro=m.estado_registro,
        estado_cum=m.estado_cum,
        fuente=m.fuente,
        dosis_total_mg=m.dosis_total_mg,
        concentracion_mg_ml=m.concentracion_mg_ml,
        volumen_ml_por_unidad=m.volumen_ml_por_unidad,
        forma_normalizada=m.forma_normalizada,
        via_normalizada=m.via_normalizada,
        tipo_formula_llm=m.tipo_formula_llm,
        componentes=m.componentes_llm,
        notas_llm=m.notas_llm,
    )


def _deduplicar(meds: list[MedicamentoTransformado], limit: int) -> list[MedicamentoLiveRead]:
    vistos: set[str] = set()
    unicos: list[MedicamentoLiveRead] = []
    for m in meds:
        conc = (m.concentracion_display or '').upper().strip()
        # Renovacion tiene namespace propio para no suprimir duplicados cross-fuente
        key = f"{m.fuente}|{m.nombre_comercial.upper().strip()}|{m.forma_farmaceutica.upper().strip()}|{conc}"
        if key not in vistos:
            vistos.add(key)
            unicos.append(_to_live_read(m))
        if len(unicos) >= limit:
            break
    return unicos


@router.get("/buscar", response_model=List[MedicamentoLiveRead])
async def buscar_medicamentos(
    q: str = Query(..., min_length=2),
    solo_activos: bool = Query(True),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Busca en tiempo real: CUM activos + registros en tramite de renovacion."""
    meds_activo, meds_renov = await asyncio.gather(
        cum_live.buscar_medicamentos(q, solo_activos=solo_activos, limit=limit * 10),
        cum_live.buscar_en_renovacion(q, limit=limit * 5),
    )
    todos = meds_activo + meds_renov
    enriquecer_con_llm(todos, db)
    return _deduplicar(todos, limit)


@router.get("/{cum_id}/alternativas", response_model=List[AlternativaLiveRead])
async def obtener_alternativas_live(cum_id: str, db: Session = Depends(get_db)):
    """Calcula alternativas en tiempo real desde el JSON online."""
    partes = cum_id.split("-", 1)
    if len(partes) != 2:
        raise HTTPException(status_code=400, detail="Formato de CUM inválido. Use expedientecum-consecutivocum")

    med = await cum_live.obtener_por_cum(partes[0], partes[1])
    if not med:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado en la API")

    # Una sola query ATC-5 devuelve pares + lookup (sin N llamadas adicionales)
    pares, lookup = await cum_live.alternativas_para(med)

    # Enriquecer con LLM: med objetivo + todos los del lookup en una sola query
    todos_meds = [med] + list(lookup.values())
    enriquecer_con_llm(todos_meds, db)

    vistos: set[str] = set()
    resultado: list[AlternativaLiveRead] = []
    for p in pares:
        cum_destino = p.cum_destino if p.cum_origen == cum_id else p.cum_origen
        med_dest_obj = lookup.get(cum_destino)
        med_dest = None
        if med_dest_obj:
            med_dest = _to_live_read(med_dest_obj)

        # Deduplicar por (tipo, nombre, concentración, laboratorio)
        if med_dest:
            conc = (med_dest.concentracion_display or '').upper().strip()
            lab  = (med_dest.laboratorio or '').upper().strip()
            key  = f"{p.tipo}|{med_dest.nombre_comercial.upper().strip()}|{conc}|{lab}"
        else:
            key = f"{p.tipo}|{cum_destino}"
        if key in vistos:
            continue
        vistos.add(key)

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
