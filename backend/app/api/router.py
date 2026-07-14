from fastapi import APIRouter
from .medicamentos import router as medicamentos_router
from .predicciones import router as predicciones_router
from .reportes import router as reportes_router
from .admin import router as admin_router
from .grupos import router as grupos_router
from .desabastecimiento import router as desabastecimiento_router

api_router = APIRouter()
api_router.include_router(medicamentos_router, prefix="/medicamentos", tags=["medicamentos"])
api_router.include_router(predicciones_router, prefix="/predicciones", tags=["predicciones"])
api_router.include_router(reportes_router, prefix="/reportes", tags=["reportes"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(grupos_router, prefix="/grupos", tags=["grupos"])
api_router.include_router(desabastecimiento_router, prefix="/desabastecimiento", tags=["desabastecimiento"])
