"""
Servicio de consulta de estado INVIMA de abastecimiento.

Mantiene un cache en memoria del mes más reciente indexado por:
  - código ATC (exacto, 7 chars)
  - ATC de 5 chars (clase)

Provee:
  - estado_actual(atc) → EstadoInvima | None
  - historico(atc)     → list[EstadoInvima]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ORDEN_SEVERIDAD = {
    "DESABASTECIDO": 5,
    "EN_RIESGO": 4,
    "EN_MONITORIZACION": 3,
    "NO_COMERCIALIZADO": 2,
    "DESCONTINUADO": 1,
    "NO_DESABASTECIDO": 0,
    None: -1,
}

LABELS_ES = {
    "DESABASTECIDO": "Desabastecido",
    "EN_RIESGO": "En riesgo de desabastecimiento",
    "EN_MONITORIZACION": "En monitorización",
    "NO_COMERCIALIZADO": "No comercializado",
    "DESCONTINUADO": "Descontinuado",
    "NO_DESABASTECIDO": "No desabastecido",
}


@dataclass
class EstadoInvima:
    estado: str
    estado_label: str
    mes: int
    anio: int
    principio_activo: str
    forma: str
    concentracion: str
    causas: str
    atc: Optional[str] = None

    @property
    def severidad(self) -> int:
        return ORDEN_SEVERIDAD.get(self.estado, -1)

    def to_dict(self) -> dict:
        return {
            "estado": self.estado,
            "estado_label": self.estado_label,
            "mes": self.mes,
            "anio": self.anio,
            "principio_activo": self.principio_activo,
            "forma": self.forma,
            "concentracion": self.concentracion,
            "causas": self.causas,
            "atc": self.atc,
        }


@dataclass
class _Cache:
    # {atc7: [EstadoInvima]}  — mes+anio más reciente
    por_atc7: dict[str, list[EstadoInvima]] = field(default_factory=dict)
    # {atc5: [EstadoInvima]}
    por_atc5: dict[str, list[EstadoInvima]] = field(default_factory=dict)
    mes: int = 0
    anio: int = 0
    listo: bool = False


_cache = _Cache()


def construir(db: Session) -> int:
    """Carga el cache desde DB. Llama al inicio de la app y después de cada actualización."""
    global _cache

    # Mes y año más reciente con datos
    row = db.execute(
        text("SELECT anio, mes FROM invima_seguimiento ORDER BY anio DESC, mes DESC LIMIT 1")
    ).fetchone()
    if not row:
        logger.warning("invima_seguimiento vacía — cache no construido")
        return 0

    anio_max, mes_max = row

    rows = db.execute(
        text("""
            SELECT principio_activo, forma, concentracion, atc, estado, causas
            FROM invima_seguimiento
            WHERE anio = :a AND mes = :m
              AND estado IS NOT NULL
              AND estado NOT IN ('NO_DESABASTECIDO')
        """),
        {"a": anio_max, "m": mes_max},
    ).fetchall()

    cache = _Cache(mes=mes_max, anio=anio_max)

    for pa, forma, conc, atc, estado, causas in rows:
        ei = EstadoInvima(
            estado=estado,
            estado_label=LABELS_ES.get(estado, estado),
            mes=mes_max,
            anio=anio_max,
            principio_activo=pa or "",
            forma=forma or "",
            concentracion=conc or "",
            causas=causas or "",
            atc=atc,
        )
        if atc:
            cache.por_atc7.setdefault(atc, []).append(ei)
            atc5 = atc[:5]
            cache.por_atc5.setdefault(atc5, []).append(ei)

    cache.listo = True
    _cache = cache
    n = sum(len(v) for v in cache.por_atc7.values())
    logger.info(
        "invima_cache: %d entradas cargadas (mes=%d/%d)", n, mes_max, anio_max
    )
    return n


def esta_listo() -> bool:
    return _cache.listo


def estado_actual(atc: Optional[str]) -> Optional[EstadoInvima]:
    """
    Retorna el estado más severo de monitoreo para el ATC dado (del mes más reciente).
    Busca primero por ATC completo (7 chars), luego por clase (5 chars).
    """
    if not _cache.listo or not atc:
        return None

    candidatos: list[EstadoInvima] = []

    # Buscar por ATC exacto
    for ei in _cache.por_atc7.get(atc, []):
        candidatos.append(ei)

    # Si no hay nada exacto, buscar por clase ATC-5
    if not candidatos and len(atc) >= 5:
        for ei in _cache.por_atc5.get(atc[:5], []):
            candidatos.append(ei)

    if not candidatos:
        return None

    # Retornar el estado más severo
    return max(candidatos, key=lambda e: e.severidad)


def estados_por_atc(atc: Optional[str]) -> list[EstadoInvima]:
    """Todos los estados vigentes para el ATC (puede ser > 1 si hay varias formas)."""
    if not _cache.listo or not atc:
        return []
    exactos = _cache.por_atc7.get(atc, [])
    if exactos:
        return exactos
    if len(atc) >= 5:
        return _cache.por_atc5.get(atc[:5], [])
    return []


def historico_desde_db(
    atc: str,
    db: Session,
    limite_meses: int = 17,
) -> list[dict]:
    """
    Devuelve el historial mensual de estados para un ATC desde la DB.
    """
    rows = db.execute(
        text("""
            SELECT anio, mes, estado, principio_activo, forma, concentracion, causas
            FROM invima_seguimiento
            WHERE atc = :atc OR atc LIKE :atc5
            ORDER BY anio DESC, mes DESC
            LIMIT :lim
        """),
        {"atc": atc, "atc5": atc[:5] + "%", "lim": limite_meses * 10},
    ).fetchall()

    # Consolidar: por (anio, mes) tomar el más severo
    per_month: dict[tuple, dict] = {}
    for anio, mes, estado, pa, forma, conc, causas in rows:
        key = (anio, mes)
        sev = ORDEN_SEVERIDAD.get(estado, -1)
        if key not in per_month or sev > ORDEN_SEVERIDAD.get(per_month[key]["estado"], -1):
            per_month[key] = {
                "anio": anio,
                "mes": mes,
                "estado": estado,
                "estado_label": LABELS_ES.get(estado, estado),
                "principio_activo": pa,
                "forma": forma,
                "concentracion": conc,
                "causas": causas,
            }

    return sorted(per_month.values(), key=lambda x: (x["anio"], x["mes"]))
