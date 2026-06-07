"""
Cliente para la API Socrata del CUM (datos.gov.co).
Siempre consulta el JSON en línea — nunca lee archivos locales.
"""
import httpx
import pandas as pd
from typing import Optional
from etl.transformacion import agrupar_y_transformar, MedicamentoTransformado, terminos_busqueda
from etl.alternativas import generar_alternativas, ParAlternativa

API_URL        = "https://www.datos.gov.co/resource/i7cb-raxc.json"
RENOVACION_URL = "https://www.datos.gov.co/resource/vgr4-gemg.json"
TIMEOUT = 20.0


async def _get(params: dict, url: str = API_URL) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _completar_grupos(filas: list[dict], url: str = API_URL) -> list[dict]:
    """
    Obtiene todas las filas de los expedientes encontrados para no omitir
    los componentes de productos combinados que no coinciden con la búsqueda.
    """
    expedientes = list({f['expedientecum'] for f in filas if f.get('expedientecum')})
    if not expedientes:
        return filas
    BATCH = 50
    filas_extra: list[dict] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for i in range(0, len(expedientes), BATCH):
            lote = expedientes[i:i + BATCH]
            ids  = ', '.join(f"'{e}'" for e in lote)
            resp = await client.get(url, params={"$where": f"expedientecum IN ({ids})", "$limit": 2000})
            resp.raise_for_status()
            filas_extra.extend(resp.json())
    todas: dict[tuple, dict] = {
        (f['expedientecum'], f.get('consecutivocum', ''), f.get('principioactivo', '')): f
        for f in filas + filas_extra
    }
    return list(todas.values())


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
    # Ampliar la búsqueda con sinónimos conocidos (ej. NIFEDIPINO → también NIFEDIPINA)
    terms = terminos_busqueda(q_upper)
    cond_terms = " OR ".join(
        f"(upper(producto) like '%{t}%' OR upper(principioactivo) like '%{t}%')"
        for t in terms
    )
    where_parts = [f"({cond_terms})"]
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

    filas = await _completar_grupos(filas)
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

    # Recuperar todas las filas del expediente para reconstruir correctamente
    # los productos combinados cuyos componentes tienen ATCs distintos
    # (ej. DOLEX: PARACETAMOL N02BE51 + CAFEINA N06BC01 — la cafeína no
    # aparece en la query by ATC y sin ella el biconjugado se arma mal).
    filas = await _completar_grupos(filas)

    df = pd.DataFrame(filas)
    todos_raw = agrupar_y_transformar(df)
    # Solo productos con registro sanitario vigente como posibles alternativas
    todos = [m for m in todos_raw if m.estado_registro.lower() in ('vigente', '')]
    lookup: dict[str, MedicamentoTransformado] = {m.cum_id: m for m in todos}

    pares = generar_alternativas(todos)

    cum_objetivo = medicamento.cum_id
    filtrados = [
        p for p in pares
        if p.cum_origen == cum_objetivo or p.cum_destino == cum_objetivo
    ]
    return filtrados, lookup


async def buscar_en_renovacion(
    query: str,
    limit: int = 200,
) -> list[MedicamentoTransformado]:
    """
    Busca en el dataset de registros en tramite de renovacion (vgr4-gemg.json).
    Retorna MedicamentoTransformado con fuente='CUM_RENOVACION'.
    """
    q_upper = query.strip().upper()
    terms = terminos_busqueda(q_upper)
    cond_terms = " OR ".join(
        f"(upper(producto) like '%{t}%' OR upper(principioactivo) like '%{t}%')"
        for t in terms
    )
    params = {
        "$where": cond_terms,
        "$limit": limit,
        "$order": "producto ASC",
    }
    filas = await _get(params, url=RENOVACION_URL)
    if not filas:
        return []
    filas = await _completar_grupos(filas, url=RENOVACION_URL)
    df = pd.DataFrame(filas)
    meds = agrupar_y_transformar(df)
    for m in meds:
        m.fuente = 'CUM_RENOVACION'
    return meds


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
