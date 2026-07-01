"""
Sincronización diaria del estado de CUMs desde Socrata → cum_normalizado.

Descarga todos los CUMs activos de datos.gov.co y actualiza el campo
estado_cum en cum_normalizado para reflejar qué productos siguen activos.
Se llama desde main.py en background cada 24 horas.
"""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

API_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
TIMEOUT = 60.0
BATCH_SIZE = 5000

logger = logging.getLogger(__name__)


async def _fetch_cum_activos() -> set[tuple[str, str]]:
    """Descarga (expedientecum, consecutivocum) de todos los registros activos en Socrata."""
    activos: set[tuple[str, str]] = set()
    offset = 0
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            resp = await client.get(API_URL, params={
                "$select": "expedientecum, consecutivocum",
                "$where": "estadocum='Activo'",
                "$limit": BATCH_SIZE,
                "$offset": offset,
            })
            resp.raise_for_status()
            lote: list[dict] = resp.json()
            if not lote:
                break
            for f in lote:
                exp = f.get('expedientecum', '').strip()
                cons = f.get('consecutivocum', '').strip()
                if exp and cons:
                    activos.add((exp, cons))
            if len(lote) < BATCH_SIZE:
                break
            offset += BATCH_SIZE
    return activos


def _actualizar_estados(db: Session, activos: set[tuple[str, str]]) -> tuple[int, int]:
    """
    Marca en cum_normalizado qué CUMs pasaron de Activo→Inactivo o vice versa.
    Retorna (activados, desactivados).
    """
    existentes = db.execute(text(
        "SELECT expediente_cum, consecutivo_cum, estado_cum FROM cum_normalizado"
    )).fetchall()

    activados = desactivados = 0
    for exp, cons, estado_actual in existentes:
        en_socrata = (exp, cons) in activos
        if en_socrata and estado_actual != 'Activo':
            db.execute(text(
                "UPDATE cum_normalizado SET estado_cum='Activo' "
                "WHERE expediente_cum=:e AND consecutivo_cum=:c"
            ), {"e": exp, "c": cons})
            activados += 1
        elif not en_socrata and estado_actual == 'Activo':
            db.execute(text(
                "UPDATE cum_normalizado SET estado_cum='Inactivo' "
                "WHERE expediente_cum=:e AND consecutivo_cum=:c"
            ), {"e": exp, "c": cons})
            desactivados += 1

    db.commit()
    return activados, desactivados


async def actualizar(db: Session) -> dict:
    """
    Punto de entrada principal. Sincroniza estado_cum con Socrata.
    Retorna stats del resultado.
    """
    inicio = datetime.now(timezone.utc)
    logger.info("Actualización diaria iniciada: %s", inicio.isoformat())

    try:
        activos = await _fetch_cum_activos()
        logger.info("Socrata: %d CUMs activos descargados", len(activos))
    except Exception as exc:
        logger.error("Error descargando CUMs de Socrata: %s", exc)
        return {"error": str(exc)}

    activados, desactivados = _actualizar_estados(db, activos)
    duracion = (datetime.now(timezone.utc) - inicio).total_seconds()

    stats = {
        "total_socrata": len(activos),
        "activados": activados,
        "desactivados": desactivados,
        "duracion_seg": round(duracion, 1),
        "ejecutado_en": inicio.isoformat(),
    }
    logger.info("Actualización diaria completada: %s", stats)
    return stats
