from pydantic import BaseModel
from typing import Optional


class RegionRead(BaseModel):
    id: int
    nombre: str
    codigo_dane: str
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    tipo: str

    model_config = {"from_attributes": True}
