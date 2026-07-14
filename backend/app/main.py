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
# The bundled openfarma.db (committed to git) is always the canonical source.
# On Railway, DATABASE_URL points to /data/openfarma.db (persistent volume).
# Without this step, the volume keeps an old DB and git DB fixes are never used.
_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL.startswith("sqlite:///") and _DATABASE_URL != "sqlite:///./openfarma.db":
    _volume_path = Path(_DATABASE_URL.replace("sqlite:///", ""))
    _bundled_db  = Path(__file__).parent.parent / "openfarma.db"
    if _bundled_db.exists() and _bundled_db.stat().st_size > 0:
        if _bundled_db.resolve() != _volume_path.resolve():
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


async def _loop_viernes_invima():
    """
    Background task: comprueba cada 6 horas si hay nuevos PDFs INVIMA.
    Solo descarga e inserta cuando detecta un PDF con mes/año nuevo.
    En producción corre los viernes; fuera de viernes el scrape es rápido (solo HTML).
    """
    import datetime
    from etl.invima_scraper import verificar_y_actualizar
    from app.services import invima_service

    _ultima_ejecucion: datetime.date | None = None

    while True:
        await asyncio.sleep(6 * 60 * 60)   # revisar cada 6 horas

        hoy = datetime.date.today()
        es_viernes = hoy.weekday() == 4    # 4 = viernes

        # Ejecutar siempre los viernes (una vez por día) y también al arrancar si hay datos pendientes
        if not es_viernes or _ultima_ejecucion == hoy:
            continue

        _ultima_ejecucion = hoy
        logger.info("Viernes — verificando nuevos PDFs INVIMA...")

        db_path = Path(__file__).parent.parent / "openfarma.db"
        _db_env = os.getenv("DATABASE_URL", "")
        if _db_env.startswith("sqlite:///") and _db_env != "sqlite:///./openfarma.db":
            db_path = Path(_db_env.replace("sqlite:///", ""))

        try:
            res = await asyncio.get_event_loop().run_in_executor(
                None, lambda: verificar_y_actualizar(db_path)
            )
            logger.info(
                "INVIMA update: %d nuevos PDFs, %d insertados, %d errores",
                res["pdfs_procesados"], res["registros_insertados"], res["errores"],
            )
            if res["pdfs_procesados"] > 0:
                # Reconstruir cache en memoria con los nuevos datos
                db = SessionLocal()
                try:
                    invima_service.construir(db)
                    logger.info("invima_cache reconstruido tras update semanal")
                finally:
                    db.close()
        except Exception as exc:
            logger.error("Error en actualización semanal INVIMA: %s", exc)


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

    # Lanzar tareas de refresco en background
    task_diario  = asyncio.create_task(_loop_diario())
    task_invima  = asyncio.create_task(_loop_viernes_invima())

    yield

    task_diario.cancel()
    task_invima.cancel()


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
