from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, JSON, func
from sqlalchemy.orm import relationship
from app.database import Base


class PrediccionDesabastecimiento(Base):
    __tablename__ = "predicciones"

    id = Column(Integer, primary_key=True, index=True)
    cum_id = Column(String(100), index=True)           # "expediente-consecutivo"
    medicamento_nombre = Column(String(300))           # denormalized
    region_id = Column(Integer, ForeignKey("regiones.id"), index=True)
    fecha_prediccion = Column(DateTime, server_default=func.now())
    probabilidad = Column(Float)
    nivel_riesgo = Column(String(10))
    horizonte_dias = Column(Integer, default=30)
    factores = Column(JSON, nullable=True)

    region = relationship("Region", back_populates="predicciones")
