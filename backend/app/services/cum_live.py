"""
Cliente para la API Socrata del CUM (datos.gov.co).
Siempre consulta el JSON en línea — nunca lee archivos locales.
"""
import asyncio
import json
import httpx
import pandas as pd
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
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


async def _completar_con_grupos_db(
    resultados: list[MedicamentoTransformado],
    db: Session,
) -> list[MedicamentoTransformado]:
    """
    Fetch representatives from DB groups not yet covered by Socrata results.
    Prevents high-frequency drugs (paracetamol) from losing vías when the
    Socrata $limit returns only the first N alphabetical products.
    """
    dci_keys: set[str] = set()
    for m in resultados:
        dcis = m.principios_dci or []
        if dcis:
            dci_keys.add("||".join(sorted(dcis)))

    if not dci_keys:
        return resultados

    ks = "','".join(k.replace("'", "''") for k in dci_keys)
    rows = db.execute(
        text(f"SELECT cum_ids FROM grupos_equivalencia WHERE dci_key IN ('{ks}')")
    ).fetchall()

    fetched_exp = {m.cum_id.split('-')[0] for m in resultados if m.cum_id and '-' in m.cum_id}

    missing: list[str] = []
    for (cum_ids_json,) in rows:
        cum_ids: list[str] = json.loads(cum_ids_json) if cum_ids_json else []
        group_exps = {cid.split('-')[0] for cid in cum_ids if '-' in cid}
        if not group_exps & fetched_exp and cum_ids:
            missing.append(cum_ids[0])

    if not missing:
        return resultados

    filas_extra = await _fetch_grupo_expedientes(missing)
    if not filas_extra:
        return resultados

    df_extra = pd.DataFrame(filas_extra)
    meds_extra = agrupar_y_transformar(df_extra)
    return resultados + meds_extra


async def buscar_medicamentos(
    query: str,
    solo_activos: bool = True,
    limit: int = 200,
    db: Optional[Session] = None,
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
    resultados = agrupar_y_transformar(df)

    if db is not None and resultados:
        resultados = await _completar_con_grupos_db(resultados, db)

    return resultados


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


async def _fetch_grupo_expedientes(cum_ids: list[str]) -> list[dict]:
    """Fetches all Socrata rows for the expedientes in a group's cum_ids list."""
    expedientes = list({cid.split("-")[0] for cid in cum_ids if "-" in cid})
    if not expedientes:
        return []
    BATCH = 50
    filas: list[dict] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for i in range(0, len(expedientes), BATCH):
            lote = expedientes[i:i + BATCH]
            ids = ', '.join(f"'{e}'" for e in lote)
            resp = await client.get(API_URL, params={
                "$where": f"expedientecum IN ({ids}) AND estadocum='Activo'",
                "$limit": 2000,
            })
            resp.raise_for_status()
            filas.extend(resp.json())
    return filas


async def alternativas_para(
    medicamento: MedicamentoTransformado,
    db: Optional[Session] = None,
    limit_clase: int = 1000,
) -> tuple[list[ParAlternativa], dict[str, MedicamentoTransformado]]:
    """
    Busca alternativas para un medicamento dado.
    Retorna (pares_filtrados, lookup) — el lookup evita N API calls adicionales.

    Si se provee db, carga los productos del grupo de equivalencia directamente
    desde grupos_equivalencia (A0-A3), evitando el corte por limit en la query ATC.
    La query ATC solo aporta A4-A7 (equivalentes de clase).
    """
    # Use corrected LLM ATC if available (fixes Socrata ATC errors like A01AB17 for oral metronidazol)
    atc_efectivo = medicamento.atc_llm or medicamento.atc
    if not atc_efectivo or len(atc_efectivo) < 5:
        return [], {}

    atc5 = atc_efectivo[:5]

    # Resolve group members from grupos_equivalencia (synchronous DB lookup)
    cum_ids_grupo: list[str] = []
    if db is not None:
        row = db.execute(
            text("SELECT cum_ids FROM grupos_equivalencia WHERE cum_ids LIKE :pat LIMIT 1"),
            {"pat": f'%"{medicamento.cum_id}"%'},
        ).fetchone()
        if row:
            cum_ids_grupo = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or [])

    async def _empty() -> list[dict]:
        return []

    # Fetch ATC class (A4-A7) and group expedientes (A0-A3) in parallel
    filas_atc, grupo_filas = await asyncio.gather(
        _get({
            "$where": f"atc like '{atc5}%' AND estadocum='Activo'",
            "$limit": limit_clase,
            "$order": "producto ASC",
        }),
        _fetch_grupo_expedientes(cum_ids_grupo) if cum_ids_grupo else _empty(),
    )
    if not filas_atc and not grupo_filas:
        return [], {}

    # Merge: group products take precedence (already active-filtered), ATC adds A4-A7 context
    seen: set[tuple] = set()
    merged: list[dict] = []
    for f in grupo_filas + filas_atc:
        k = (f.get('expedientecum'), f.get('consecutivocum'), f.get('principioactivo', ''))
        if k not in seen:
            seen.add(k)
            merged.append(f)

    # Complete combination products whose components have different ATCs
    merged = await _completar_grupos(merged)

    df = pd.DataFrame(merged)
    todos_raw = agrupar_y_transformar(df)
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
