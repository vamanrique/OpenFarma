from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.region import Region
from app.schemas.region import RegionRead

router = APIRouter()


@router.get("/", response_model=List[RegionRead])
def listar_regiones(db: Session = Depends(get_db)):
    return db.query(Region).order_by(Region.nombre).all()


@router.get("/{region_id}", response_model=RegionRead)
def obtener_region(region_id: int, db: Session = Depends(get_db)):
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Región no encontrada")
    return region
