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
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# Detecta cuando principio_activo es texto de causa INVIMA, no nombre de fármaco
_CAUSA_RE = re.compile(
    r'^(Disminuci[oó]n\b|Sin\s+respuesta\b|Pocos\s+oferentes|'
    r'Insuficientes?\s+oferentes|Escac[e]z\b|Escasez\b|Sin\s+suministro\b|'
    r'No\s+comercializaci[oó]n\b|Pocos\s+titulares\b)',
    re.IGNORECASE,
)

# Punto de corte: donde empieza la concentración o la forma farmacéutica en el texto
_CORTE_FORMA_RE = re.compile(
    r'(?:\s+)(\d|\b(?:TABLETA|C[AÁ]PSULA|SOLUCI[OÓ]N|POLVO|SUSPENSI[OÓ]N|'
    r'JARABE|AMPOLLA|VIAL|COMPRIMIDO|CREMA|UNGUENTO|GOTAS|SPRAY|PARCHE|'
    r'LIOFILIZADO|EMULSI[OÓ]N|GRANULOS|RECONSTITUIR|INYECTABLE|ORAL|'
    r'INFUSI[OÓ]N|INHALACI[OÓ]N)\b)',
    re.IGNORECASE,
)


_CONC_CONTINUACION_RE = re.compile(
    r'^(INYECTABLE|INYECCI[OÓ]N|INFUSI[OÓ]N|RECONSTITUIR)',
    re.IGNORECASE,
)


def _limpiar_entrada(pa: str, forma: str, conc: str) -> tuple[str, str, str]:
    """
    Corrige artefactos del parser PDF de INVIMA (columnas del PDF que se
    deslizan entre campos):

    1. conc empieza con "A " → es continuación de forma
       (ej. "POLVO PARA RECONSTITUIR" + "A SOLUCION INYECTABLE")
    2. forma empieza con "A " → es continuación del principio_activo
       (ej. "ALENDRONATO SODICO, EQUIVALENTE" + "A ACIDO ALENDRONICO")
    3. forma termina con "PARA" y conc es una forma farmacéutica
       (ej. "POLVO LIOFILIZADO PARA" + "INYECTABLE")
    4. principio_activo es texto de causa INVIMA, no nombre de fármaco;
       el nombre real está al inicio del campo forma.
    """
    # Fix 1: conc = continuación de forma (empieza con "A …")
    if conc and re.match(r'^A\s+', conc.strip()):
        forma = (forma.strip() + ' ' + conc.strip()).strip()
        conc = ''

    # Fix 2: forma = continuación del PA (empieza con "A …")
    if forma and re.match(r'^A\s+', forma.strip()) and not _CAUSA_RE.match(pa or ''):
        pa   = (pa.strip() + ' ' + forma.strip()).strip()
        forma = conc.strip()
        conc  = ''

    # Fix 3: forma termina con "PARA" y conc es continuación de la forma
    if (forma and forma.upper().rstrip().endswith('PARA')
            and conc and _CONC_CONTINUACION_RE.match(conc.strip())):
        forma = (forma.strip() + ' ' + conc.strip()).strip()
        conc  = ''

    # Fix 4: principio_activo es una causa INVIMA, no un nombre de fármaco
    if _CAUSA_RE.match(pa or ''):
        candidato = forma.strip()
        m = _CORTE_FORMA_RE.search(candidato)
        if m:
            candidato = candidato[:m.start()].strip()
        pa = candidato if candidato else pa

    return pa, forma, conc

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

    sin_atc = 0
    for pa, forma, conc, atc, estado, causas in rows:
        if not atc:
            sin_atc += 1
            continue
        pa, forma, conc = _limpiar_entrada(pa or "", forma or "", conc or "")
        ei = EstadoInvima(
            estado=estado,
            estado_label=LABELS_ES.get(estado, estado),
            mes=mes_max,
            anio=anio_max,
            principio_activo=pa,
            forma=forma,
            concentracion=conc,
            causas=causas or "",
            atc=atc,
        )
        cache.por_atc7.setdefault(atc, []).append(ei)
        atc5 = atc[:5]
        cache.por_atc5.setdefault(atc5, []).append(ei)
    if sin_atc:
        logger.warning("invima_cache: %d registros descartados sin ATC (mes=%d/%d)", sin_atc, mes_max, anio_max)

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
