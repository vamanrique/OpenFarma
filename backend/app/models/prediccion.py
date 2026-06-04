from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, JSON, func
from sqlalchemy.orm import relationship
from app.database import Base


class PrediccionDesabastecimiento(Base):
    __tablename__ = "predicciones"

    id = Column(Integer, primary_key=True, index=True)
    medicamento_id = Column(Integer, ForeignKey("medicamentos.id"), index=True)
    region_id = Column(Integer, ForeignKey("regiones.id"), index=True)
    fecha_prediccion = Column(DateTime, server_default=func.now())
    probabilidad = Column(Float)  # 0.0 - 1.0
    nivel_riesgo = Column(String(10))  # bajo, medio, alto, critico
    horizonte_dias = Column(Integer, default=30)
    factores = Column(JSON, nullable=True)

    medicamento = relationship("Medicamento", back_populates="predicciones")
    region = relationship("Region", back_populates="predicciones")
