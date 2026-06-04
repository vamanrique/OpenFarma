from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class Region(Base):
    __tablename__ = "regiones"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), index=True)
    codigo_dane = Column(String(10), unique=True, index=True)
    latitud = Column(Float)
    longitud = Column(Float)
    tipo = Column(String(20), default="departamento")  # departamento, municipio

    consultas = relationship("ConsultaRegion", back_populates="region")
    predicciones = relationship("PrediccionDesabastecimiento", back_populates="region")


class ConsultaRegion(Base):
    __tablename__ = "consultas_region"

    id = Column(Integer, primary_key=True, index=True)
    region_id = Column(Integer, ForeignKey("regiones.id"), index=True)
    medicamento_id = Column(Integer, ForeignKey("medicamentos.id"), index=True)
    fecha = Column(DateTime, server_default=func.now())
    tipo = Column(String(30))  # busqueda, reporte_no_disponibilidad, reporte_ips
    conteo = Column(Integer, default=1)

    region = relationship("Region", back_populates="consultas")
    medicamento = relationship("Medicamento", back_populates="consultas")
