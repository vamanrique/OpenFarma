"""
Cliente para la API Socrata del CUM (datos.gov.co).
Siempre consulta el JSON en línea — nunca lee archivos locales.
"""
import httpx
import pandas as pd
from typing import Optional
from etl.transformacion import agrupar_y_transformar, MedicamentoTransformado
from etl.alternativas import generar_alternativas, ParAlternativa

API_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
TIMEOUT = 20.0


async def _get(params: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(API_URL, params=params)
        resp.raise_for_status()
        return resp.json()


async def buscar_medicamentos(
    query: str,
    solo_activos: bool = True,
    limit: int = 200,
) -> list[MedicamentoTransformado]:
    """
    Busca en la API por nombre de producto o principio activo.
    Agrupa las filas por expedientecum+consecutivocum para reconstruir combinados.
    """
    q_upper = query.strip().upper()
    where_parts = [
        f"(upper(producto) like '%{q_upper}%' OR upper(principioactivo) like '%{q_upper}%')"
    ]
    if solo_activos:
        where_parts.append("estadocum='Activo'")

    params = {
        "$where": " AND ".join(where_parts),
        "$limit": limit,
        "$order": "producto ASC",
    }

    filas = await _get(params)
    if not filas:
        return []

    df = pd.DataFrame(filas)
    return agrupar_y_transformar(df)


async def obtener_por_cum(expedientecum: str, consecutivocum: str) -> Optional[MedicamentoTransformado]:
    """Obtiene un medicamento específico desde la API."""
    params = {
        "$where": f"expedientecum='{expedientecum}' AND consecutivocum='{consecutivocum}'",
        "$limit": 50,
    }
    filas = await _get(params)
    if not filas:
        return None

    df = pd.DataFrame(filas)
    meds = agrupar_y_transformar(df)
    return meds[0] if meds else None


async def alternativas_para(
    medicamento: MedicamentoTransformado,
    limit_clase: int = 500,
) -> tuple[list[ParAlternativa], dict[str, MedicamentoTransformado]]:
    """
    Busca alternativas para un medicamento dado.
    Retorna (pares_filtrados, lookup) — el lookup evita N API calls adicionales.
    """
    if not medicamento.atc or len(medicamento.atc) < 5:
        return [], {}

    atc5 = medicamento.atc[:5]
    params = {
        "$where": f"atc like '{atc5}%' AND estadocum='Activo'",
        "$limit": limit_clase,
        "$order": "producto ASC",
    }

    filas = await _get(params)
    if not filas:
        return [], {}

    df = pd.DataFrame(filas)
    todos = agrupar_y_transformar(df)
    lookup: dict[str, MedicamentoTransformado] = {m.cum_id: m for m in todos}

    pares = generar_alternativas(todos)

    cum_objetivo = medicamento.cum_id
    filtrados = [
        p for p in pares
        if p.cum_origen == cum_objetivo or p.cum_destino == cum_objetivo
    ]
    return filtrados, lookup


async def estadisticas_por_atc() -> list[dict]:
    """Conteo de medicamentos activos por grupo ATC (primer nivel)."""
    params = {
        "$select": "atc, count(distinct expedientecum||consecutivocum) as total",
        "$where": "estadocum='Activo' AND atc IS NOT NULL",
        "$group": "atc",
        "$order": "total DESC",
        "$limit": 200,
    }
    return await _get(params)
