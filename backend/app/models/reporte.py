from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class ReporteNoDisponibilidad(Base):
    __tablename__ = "reportes_no_disponibilidad"

    id = Column(Integer, primary_key=True, index=True)
    cum_id = Column(String(100), index=True)
    nombre_medicamento = Column(String(200))
    tipo_reporte = Column(String(50), default="sin_stock")
    descripcion = Column(String(500), nullable=True)
    fecha = Column(DateTime, server_default=func.now())
