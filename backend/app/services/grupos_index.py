"""
Índice en memoria: cum_id → (dci_key, concentracion_norm, grupo_via)

Construido al inicio desde grupos_equivalencia para que cada búsqueda live
obtenga DCIs y concentraciones desde la base normalizada, no desde Socrata raw.
Se reconstruye tras cada actualización diaria del ETL.
"""
import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

_index: dict[str, tuple[str, str, str]] = {}


def construir(db: Session) -> int:
    """Construye el índice desde grupos_equivalencia. Retorna número de CUMs indexados."""
    global _index
    rows = db.execute(text(
        "SELECT dci_key, concentracion_norm, grupo_via, cum_ids FROM grupos_equivalencia"
    )).fetchall()

    nuevo: dict[str, tuple[str, str, str]] = {}
    for dci_key, conc_norm, grupo_via, cum_ids_json in rows:
        try:
            cum_ids: list[str] = (
                json.loads(cum_ids_json) if isinstance(cum_ids_json, str) else (cum_ids_json or [])
            )
        except (json.JSONDecodeError, TypeError):
            continue
        entry = (dci_key or '', conc_norm or '', grupo_via or '')
        for cum_id in cum_ids:
            nuevo[cum_id] = entry

    _index = nuevo
    logger.info("grupos_index: %d CUMs indexados desde %d grupos", len(_index), len(rows))
    return len(_index)


def buscar(cum_id: str) -> tuple[str, str, str] | None:
    """Retorna (dci_key, concentracion_norm, grupo_via) o None si no encontrado."""
    return _index.get(cum_id)


def esta_listo() -> bool:
    return bool(_index)


def concentracion_display(dci_key: str, concentracion_norm: str) -> str:
    """
    Reconstruye concentracion_display a partir de dci_key y concentracion_norm.

    Mono:  "PARACETAMOL" + "500 mg"         → "500 mg"
    Combo: "GLIBENCLAMIDA||METFORMINA" +
           "2.5 mg + 500 mg"                → "GLIBENCLAMIDA 2.5 mg + METFORMINA 500 mg"

    El formato DCI-prefijado activa isComboDCI en el frontend,
    que muestra "2.5 mg · 500 mg" (separador bullet, más claro).
    """
    if not concentracion_norm or concentracion_norm == 'SIN_CONCENTRACION':
        return ''

    dcis = dci_key.split('||') if '||' in dci_key else [dci_key]

    if len(dcis) <= 1:
        return concentracion_norm

    partes_conc = [p.strip() for p in concentracion_norm.split('+')]
    if len(partes_conc) != len(dcis):
        # Mismatch inesperado: devolver la concentración tal como está
        return concentracion_norm

    return ' + '.join(f"{d} {c}" for d, c in zip(dcis, partes_conc))
