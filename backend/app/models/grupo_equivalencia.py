from datetime import datetime
from sqlalchemy import String, Float, Integer, JSON, DateTime, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class GrupoEquivalencia(Base):
    """
    Grupos de equivalencia farmacológica calculados por construir_grupos.py.

    Cada registro representa un conjunto de productos CUM que comparten:
      - el mismo/los mismos principios activos (dci_key)
      - la misma vía/forma farmacéutica normalizada (grupo_via)
      - la misma concentración normalizada (concentracion_norm)
    """
    __tablename__ = "grupos_equivalencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Clave de principio activo — monocomponente: "ACICLOVIR",
    # multicomponente: "AMOXICILINA||CLAVULANATO POTASICO" (sorted, joined with ||)
    dci_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)

    # SOLIDO_ORAL, SOLIDO_ORAL_LP, ORAL_DISPERSABLE, SUBLINGUAL, INYECTABLE,
    # INHALADO, NASAL, OFTALMICO, OTICO, TOPICO, VAGINAL, RECTAL,
    # TRANSDERMICO, LIQUIDO_ORAL
    grupo_via: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Human-readable concentration: "200 mg", "50 mg/mL", "5%", "500 mg + 125 mg"
    # None if unclassifiable
    concentracion_norm: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Numeric value for sorting (first component for combos)
    concentracion_valor: Mapped[float | None] = mapped_column(Float, nullable=True)

    # "mg", "mg/mL", "%", "mg/dosis"
    concentracion_unidad: Mapped[str | None] = mapped_column(String(15), nullable=True)

    # List of cum_ids: ["expediente-consecutivo", ...]
    cum_ids: Mapped[list | None] = mapped_column(JSON, nullable=False, default=list)

    n_productos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # True if DeepSeek reviewed this group
    revisado_ia: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_ge_dci_via", "dci_key", "grupo_via"),
    )
