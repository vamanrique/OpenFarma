from pydantic import BaseModel
from typing import Optional, Any


# DTO para resultados del servicio live (no pasan por DB)
class MedicamentoLiveRead(BaseModel):
    cum_id: str
    nombre_comercial: str
    principios_dci: list[str]
    tipo_formula: str
    concentracion_display: str
    presentacion: str = ""
    forma_farmaceutica: str
    via_administracion: str
    atc: str
    descripcion_atc: str
    laboratorio: str
    registro_sanitario: str
    estado_registro: str
    estado_cum: str
    # Fuente del registro
    fuente:                str                = 'CUM_ACTIVO'  # CUM_ACTIVO | CUM_RENOVACION
    # Campos enriquecidos por LLM — presentes si el CUM ya fue procesado
    dosis_total_mg:        Optional[float]     = None
    concentracion_mg_ml:   Optional[float]     = None
    volumen_ml_por_unidad: Optional[float]     = None
    forma_normalizada:     Optional[str]       = None
    via_normalizada:       Optional[list[str]] = None
    tipo_formula_llm:      Optional[str]       = None   # MONO, BI, TRI, TETRA
    componentes:           Optional[list]      = None   # [{"dci","concentracion_mg_ml","dosis_mg"}]
    notas_llm:             Optional[str]       = None


class AlternativaLiveRead(BaseModel):
    cum_origen: str
    cum_destino: str
    tipo: str
    descripcion: str
    componentes_compartidos: list[str]
    medicamento_destino: Optional[MedicamentoLiveRead] = None
