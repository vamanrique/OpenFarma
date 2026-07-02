from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import asyncio
import logging
import os
import shutil
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Seed DB from bundled file if Railway volume path differs ─────────────────
# The bundled farmavigia.db (committed to git) is always the canonical source.
# On Railway, DATABASE_URL points to /data/farmavigia.db (persistent volume).
# Without this step, the volume keeps an old DB and git DB fixes are never used.
_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL.startswith("sqlite:///") and _DATABASE_URL != "sqlite:///./farmavigia.db":
    _volume_path = Path(_DATABASE_URL.replace("sqlite:///", ""))
    _bundled_db  = Path(__file__).parent.parent / "farmavigia.db"
    if _bundled_db.exists() and _bundled_db.stat().st_size > 0:
        _volume_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_bundled_db), str(_volume_path))
        logger.info("DB seed: copied %s → %s (%d MB)",
                    _bundled_db, _volume_path,
                    _bundled_db.stat().st_size // 1_000_000)

import app.models  # noqa: F401 — registra todos los modelos antes de init_db
from app.database import init_db, SessionLocal
from app.api.router import api_router
from app.migrations import run_all as run_migrations

init_db()
run_migrations()


async def _loop_diario():
    """Background task: sincroniza estado_cum con Socrata cada 24 horas y reconstruye el índice."""
    from etl.actualizacion_diaria import actualizar
    from app.services import grupos_index, invima_service

    while True:
        await asyncio.sleep(24 * 60 * 60)
        db = SessionLocal()
        try:
            await actualizar(db)
            grupos_index.construir(db)
            invima_service.construir(db)
        except Exception as exc:
            logger.error("Error en actualización diaria: %s", exc)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: construir índices en memoria
    from app.services import grupos_index, invima_service
    db = SessionLocal()
    try:
        n = grupos_index.construir(db)
        logger.info("grupos_index listo: %d CUMs", n)
        n_inv = invima_service.construir(db)
        logger.info("invima_cache listo: %d entradas", n_inv)
    except Exception as exc:
        logger.error("Error construyendo índices de startup: %s", exc)
    finally:
        db.close()

    # Lanzar tarea de refresco diario en background
    task = asyncio.create_task(_loop_diario())

    yield

    task.cancel()


app = FastAPI(
    title="OpenFarma API",
    description="Alternativas farmacológicas y predicción de desabastecimiento — Colombia",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


# Sirve el frontend compilado (production). En dev esto no existe y se usa Vite.
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        file = FRONTEND_DIST / full_path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
