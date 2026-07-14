"""
Cliente para la API Socrata del CUM (datos.gov.co).
Consulta datos.gov.co con App Token cuando está disponible; si Socrata
falla o devuelve error, cae a la base de datos local (cum_normalizado).
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
TIMEOUT = 30.0

import os as _os


def _socrata_headers() -> dict:
    token = _os.environ.get("SOCRATA_APP_TOKEN", "")
    return {"X-App-Token": token} if token else {}


async def _get(params: dict, url: str = API_URL) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_socrata_headers()) as client:
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
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_socrata_headers()) as client:
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

    # _completar_grupos fetches all rows for found expedientes without an estadocum
    # filter, so inactive variants of the same expediente can slip through. Remove them.
    if solo_activos:
        resultados = [m for m in resultados if m.estado_cum.lower() == 'activo']

    if db is not None and resultados:
        resultados = await _completar_con_grupos_db(resultados, db)

    return resultados


async def obtener_por_cum(
    expedientecum: str,
    consecutivocum: str,
    db: Optional[Session] = None,
) -> Optional[MedicamentoTransformado]:
    """Obtiene un medicamento específico desde la API (activos + renovación). Fallback a DB local."""
    params = {
        "$where": f"expedientecum='{expedientecum}' AND consecutivocum='{consecutivocum}'",
        "$limit": 50,
    }
    try:
        filas = await _get(params)
        if not filas:
            filas = await _get(params, url=RENOVACION_URL)
        if filas:
            df = pd.DataFrame(filas)
            meds = agrupar_y_transformar(df)
            if meds and not filas[0].get('estadocum'):
                meds[0].fuente = 'CUM_RENOVACION'
            return meds[0] if meds else None
    except Exception:
        pass

    if db is not None:
        return obtener_desde_db(expedientecum, consecutivocum, db)
    return None


async def _fetch_grupo_expedientes(cum_ids: list[str]) -> list[dict]:
    """Fetches all Socrata rows for the expedientes in a group's cum_ids list."""
    expedientes = list({cid.split("-")[0] for cid in cum_ids if "-" in cid})
    if not expedientes:
        return []
    BATCH = 50
    filas: list[dict] = []
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_socrata_headers()) as client:
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
    try:
        filas_atc, grupo_filas = await asyncio.gather(
            _get({
                "$where": f"atc like '{atc5}%' AND estadocum='Activo'",
                "$limit": limit_clase,
                "$order": "producto ASC",
            }),
            _fetch_grupo_expedientes(cum_ids_grupo) if cum_ids_grupo else _empty(),
        )
    except Exception:
        # Socrata unavailable — fall back to local DB
        if db is not None:
            return _alternativas_desde_db(medicamento, cum_ids_grupo, db, limit_clase)
        return [], {}

    if not filas_atc and not grupo_filas:
        if db is not None:
            return _alternativas_desde_db(medicamento, cum_ids_grupo, db, limit_clase)
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
    try:
        merged = await _completar_grupos(merged)
    except Exception:
        pass  # proceed with what we have

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


def _row_to_med(row) -> MedicamentoTransformado:
    """Converts a CumNormalizado ORM row to MedicamentoTransformado."""
    principios = row.principios_dci or []
    tipo = row.tipo_formula or "monocomponente"
    via_list = row.via_normalizada or []
    via = via_list[0] if via_list else ""

    componentes = row.componentes or []
    if componentes and len(componentes) > 1:
        partes = []
        for c in componentes:
            dci = c.get("dci", "")
            mg = c.get("dosis_mg") or c.get("concentracion_mg_ml")
            if mg:
                partes.append(f"{dci} {mg:g} mg")
            elif dci:
                partes.append(dci)
        conc_display = " + ".join(partes) if partes else ""
        concentraciones = partes
    elif row.dosis_total_mg:
        conc_display = f"{row.dosis_total_mg:g} mg"
        concentraciones = [conc_display]
    elif row.concentracion_mg_ml:
        conc_display = f"{row.concentracion_mg_ml:g} mg/mL"
        concentraciones = [conc_display]
    else:
        conc_display = ""
        concentraciones = []

    cum_id = f"{row.expediente_cum}-{row.consecutivo_cum}"
    return MedicamentoTransformado(
        cum_id=cum_id,
        expedientecum=row.expediente_cum,
        consecutivocum=row.consecutivo_cum,
        nombre_comercial=row.nombre_comercial_norm or cum_id,
        principios_activos_raw=principios,
        principios_dci=principios,
        tipo_formula=tipo,
        concentraciones=concentraciones,
        concentracion_display=conc_display,
        dosis_numerica=row.dosis_total_mg,
        presentacion="",
        forma_farmaceutica=row.forma_normalizada or "",
        via_administracion=via,
        atc=row.atc_normalizado or "",
        descripcion_atc="",
        laboratorio=row.titular_registro or "",
        registro_sanitario=row.registro_sanitario or "",
        estado_registro=row.estado_registro or "",
        estado_cum=row.estado_cum or "",
        modalidad="",
        fuente=row.fuente or "CUM_ACTIVO",
        principios_dci_llm=principios,
        dosis_total_mg=row.dosis_total_mg,
        concentracion_mg_ml=row.concentracion_mg_ml,
        volumen_ml_por_unidad=row.volumen_ml_por_unidad,
        forma_normalizada=row.forma_normalizada,
        via_normalizada=via_list,
        atc_llm=row.atc_normalizado,
        tipo_formula_llm=tipo,
        componentes_llm=componentes if componentes else None,
        notas_llm=row.notas,
    )


def obtener_desde_db(expediente: str, consecutivo: str, db: Session) -> Optional[MedicamentoTransformado]:
    """Fetch a specific product from local cum_normalizado by PK."""
    from app.models.cum_normalizado import CumNormalizado
    row = db.query(CumNormalizado).filter(
        CumNormalizado.expediente_cum == expediente,
        CumNormalizado.consecutivo_cum == consecutivo,
    ).first()
    return _row_to_med(row) if row else None


def _alternativas_desde_db(
    medicamento: MedicamentoTransformado,
    cum_ids_grupo: list[str],
    db: Session,
    limit_clase: int = 1000,
) -> tuple[list[ParAlternativa], dict[str, MedicamentoTransformado]]:
    """
    Generates alternatives using only local cum_normalizado data.
    Used as fallback when Socrata is unavailable.
    """
    from app.models.cum_normalizado import CumNormalizado

    atc_efectivo = medicamento.atc_llm or medicamento.atc
    atc5 = atc_efectivo[:5] if atc_efectivo and len(atc_efectivo) >= 5 else None

    # Load group products (A0-A3) from local DB
    grupo_meds: list[MedicamentoTransformado] = []
    if cum_ids_grupo:
        expedientes = list({cid.split("-")[0] for cid in cum_ids_grupo if "-" in cid})
        rows = db.query(CumNormalizado).filter(
            CumNormalizado.expediente_cum.in_(expedientes),
            CumNormalizado.estado_cum.ilike("activo"),
        ).all()
        exp_cons = {(cid.split("-")[0], cid.split("-")[1]) for cid in cum_ids_grupo if "-" in cid}
        grupo_meds = [_row_to_med(r) for r in rows if (r.expediente_cum, r.consecutivo_cum) in exp_cons]

    # Load ATC class products (A4-A7) from local DB
    atc_meds: list[MedicamentoTransformado] = []
    if atc5:
        rows_atc = db.query(CumNormalizado).filter(
            CumNormalizado.atc_normalizado.like(f"{atc5}%"),
            CumNormalizado.estado_cum.ilike("activo"),
        ).limit(limit_clase).all()
        atc_meds = [_row_to_med(r) for r in rows_atc]

    seen: set[str] = set()
    todos: list[MedicamentoTransformado] = []
    for m in grupo_meds + atc_meds:
        if m.cum_id not in seen:
            seen.add(m.cum_id)
            todos.append(m)

    if not todos:
        return [], {}

    lookup: dict[str, MedicamentoTransformado] = {m.cum_id: m for m in todos}
    pares = generar_alternativas(todos)
    filtrados = [p for p in pares if p.cum_origen == medicamento.cum_id or p.cum_destino == medicamento.cum_id]
    return filtrados, lookup


def buscar_desde_db(
    query: str,
    db: Session,
    solo_activos: bool = True,
    limit: int = 100,
) -> list[MedicamentoTransformado]:
    """
    Búsqueda local en cum_normalizado — fallback cuando Socrata no responde.
    Devuelve MedicamentoTransformado compatibles con el pipeline normal de enriquecimiento.
    """
    from app.models.cum_normalizado import CumNormalizado
    from sqlalchemy import or_, cast, Text, func

    q_upper = query.strip().upper()
    terms = terminos_busqueda(q_upper)

    condiciones = or_(*(
        or_(
            func.upper(CumNormalizado.nombre_comercial_norm).contains(t),
            func.upper(cast(CumNormalizado.principios_dci, Text)).contains(t),
        )
        for t in terms
    ))

    q = db.query(CumNormalizado).filter(condiciones)
    if solo_activos:
        q = q.filter(CumNormalizado.estado_cum.ilike("activo"))
    rows: list[CumNormalizado] = q.order_by(CumNormalizado.nombre_comercial_norm).limit(limit).all()

    return [_row_to_med(row) for row in rows]


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
