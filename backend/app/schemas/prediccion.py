from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class PrediccionRead(BaseModel):
    id: int
    cum_id: str
    medicamento_nombre: Optional[str] = None
    fecha_prediccion: datetime
    probabilidad: float
    nivel_riesgo: str
    horizonte_dias: int
    factores: Optional[Any] = None

    model_config = {"from_attributes": True}
