from datetime import datetime
from sqlalchemy import String, Float, Integer, JSON, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CumNormalizado(Base):
    """
    Caché de normalización LLM por (expediente_cum, consecutivo_cum).
    Se actualiza solo cuando el hash de los campos raw cambia.
    """
    __tablename__ = "cum_normalizado"

    # Clave primaria compuesta
    expediente_cum:  Mapped[str] = mapped_column(String(50), primary_key=True)
    consecutivo_cum: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Hash de los campos raw — detecta cambios para invalidar caché
    data_hash: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── Salida LLM ──────────────────────────────────────────────────────────
    nombre_comercial_norm:  Mapped[str | None]  = mapped_column(String(300))
    principios_dci:         Mapped[list | None]  = mapped_column(JSON)       # ["MIDAZOLAM"]
    sinonimos_resueltos:    Mapped[dict | None]  = mapped_column(JSON)       # {"ACETAMINOFÉN": "PARACETAMOL"}
    concentracion_mg_ml:    Mapped[float | None] = mapped_column(Float)      # mg/mL normalizado
    volumen_ml_por_unidad:  Mapped[float | None] = mapped_column(Float)      # mL por ampolla/vial/frasco
    dosis_total_mg:         Mapped[float | None] = mapped_column(Float)      # mg totales por unidad dispensada
    unidades_por_envase:    Mapped[int | None]   = mapped_column(Integer)    # tabletas/ampollas por caja
    forma_normalizada:      Mapped[str | None]   = mapped_column(String(50)) # TABLETA, INYECTABLE, etc.
    via_normalizada:        Mapped[list | None]  = mapped_column(JSON)       # ["INTRAVENOSA","RECTAL"]
    atc_normalizado:        Mapped[str | None]   = mapped_column(String(10)) # A10BF01
    tipo_formula:           Mapped[str | None]   = mapped_column(String(10)) # MONO, BI, TRI, TETRA
    componentes:            Mapped[list | None]  = mapped_column(JSON)       # [{"dci":"X","concentracion_mg_ml":5.0,"dosis_mg":15.0}]
    notas:                  Mapped[str | None]   = mapped_column(Text)

    # ── Passthrough del CUM (sin pasar por LLM) ─────────────────────────────
    titular_registro:    Mapped[str | None] = mapped_column(String(300))
    registro_sanitario:  Mapped[str | None] = mapped_column(String(100))
    estado_cum:          Mapped[str | None] = mapped_column(String(20))
    estado_registro:     Mapped[str | None] = mapped_column(String(20))

    # ── Metadata del procesamiento ───────────────────────────────────────────
    fuente:       Mapped[str | None]      = mapped_column(String(30), default='CUM_ACTIVO')
    procesado_en: Mapped[datetime | None] = mapped_column(DateTime)
    modelo:       Mapped[str | None]      = mapped_column(String(50))
    intentos:     Mapped[int]             = mapped_column(Integer, default=0)
