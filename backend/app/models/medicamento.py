from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class Medicamento(Base):
    __tablename__ = "medicamentos"

    id = Column(Integer, primary_key=True, index=True)
    cum = Column(String(50), unique=True, index=True)       # expedientecum-consecutivocum
    nombre_comercial = Column(String(300), index=True)
    nombre_generico = Column(String(300), index=True)       # descripcionatc
    principio_activo = Column(String(300), index=True)      # DCI del primer componente
    principios_dci = Column(JSON)                           # lista de DCIs normalizados
    tipo_formula = Column(String(20), index=True)           # monocomponente|biconjugado|triconjugado|tetraconjugado
    concentracion = Column(String(300))                     # concentración real construida
    forma_farmaceutica = Column(String(150))
    via_administracion = Column(String(100), nullable=True)
    laboratorio = Column(String(300))
    registro_sanitario = Column(String(100))
    estado = Column(String(20), default="vigente", index=True)
    estado_cum = Column(String(20), default="activo")
    codigo_atc = Column(String(10), index=True)
    grupo_terapeutico = Column(String(300))
    modalidad = Column(String(100), nullable=True)
    precio_maximo = Column(Float, nullable=True)
    requiere_formula = Column(Boolean, default=False)

    alternativas_origen = relationship(
        "Alternativa", foreign_keys="Alternativa.medicamento_id", back_populates="medicamento"
    )
    alternativas_destino = relationship(
        "Alternativa", foreign_keys="Alternativa.alternativa_id", back_populates="alternativa"
    )
    predicciones = relationship("PrediccionDesabastecimiento", back_populates="medicamento")
    consultas = relationship("ConsultaRegion", back_populates="medicamento")


class Alternativa(Base):
    __tablename__ = "alternativas"

    id = Column(Integer, primary_key=True, index=True)
    medicamento_id = Column(Integer, ForeignKey("medicamentos.id"), index=True)
    alternativa_id = Column(Integer, ForeignKey("medicamentos.id"), index=True)
    tipo = Column(String(40), index=True)
    observaciones = Column(Text, nullable=True)
    componentes_compartidos = Column(JSON, nullable=True)   # DCIs en común

    medicamento = relationship("Medicamento", foreign_keys=[medicamento_id], back_populates="alternativas_origen")
    alternativa = relationship("Medicamento", foreign_keys=[alternativa_id], back_populates="alternativas_destino")
