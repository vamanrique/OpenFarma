from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class ReporteNoDisponibilidad(Base):
    __tablename__ = "reportes_no_disponibilidad"

    id = Column(Integer, primary_key=True, index=True)
    cum_id = Column(String(100), index=True)
    nombre_medicamento = Column(String(200))
    region_id = Column(Integer, ForeignKey("regiones.id"), index=True)
    tipo_reporte = Column(String(50), default="sin_stock")  # sin_stock, precio_alto, sin_suministro
    descripcion = Column(String(500), nullable=True)
    fecha = Column(DateTime, server_default=func.now())

    region = relationship("Region")
