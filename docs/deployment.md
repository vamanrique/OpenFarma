# Guía de Despliegue — OpenFarma

## Entornos

| Entorno | URL | Trigger |
|---------|-----|---------|
| Producción | https://openfarma-production.up.railway.app | Push a `main` |
| Local | http://localhost:8000 (API) · http://localhost:5173 (UI) | Manual |

---

## Deploy en Railway (producción)

### Cómo funciona

1. El push a `main` activa Railway vía GitHub webhook.
2. **nixpacks.toml** (raíz): Railway instala Python + Node 20, ejecuta `pip install -r requirements.txt` y `npm ci && npm run build` en `frontend/`.
3. **start.sh**: al arrancar el contenedor, copia `backend/openfarma.db` → `/data/openfarma.db` y arranca uvicorn.
4. La app lee de `/data/openfarma.db` (volumen persistente). Los reportes ciudadanos sobreviven entre deploys.

### Variables de entorno en Railway

| Variable | Valor en producción | Obligatoria |
|----------|--------------------|----|
| `DATABASE_URL` | `sqlite:////data/openfarma.db` | Sí |
| `SECRET_KEY` | (genera con `secrets.token_hex(32)`) | Sí |
| `ENVIRONMENT` | `production` | Sí |
| `CORS_ORIGINS` | `https://openfarma-production.up.railway.app` | Sí |
| `DEEPSEEK_API_KEY` | (clave DeepSeek) | Solo para ETL |

### Actualizar la base de datos en Railway

La base de datos vive en git (`backend/openfarma.db`). Para propagar cambios:

```bash
# 1. Checkpoint WAL obligatorio antes de commitear
python -c "import sqlite3; c=sqlite3.connect('backend/openfarma.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()"
# O con Make:
make checkpoint

# 2. Commitear y pushear
git add backend/openfarma.db
git commit -m "data: descripción del cambio"
git push
```

Railway re-despliega automáticamente y en `start.sh` la DB actualizada reemplaza el volumen.

> **Importante:** Si solo cambia código (sin cambios en `openfarma.db`), Railway no copia la DB de nuevo — el volumen conserva los reportes ciudadanos acumulados.

---

## Desarrollo local

### Prerequisitos

- Python 3.11+
- Node.js 20+

### Con Make (recomendado)

```bash
make backend     # crea venv, instala deps, arranca API en :8000
make frontend    # instala deps Node, arranca frontend en :5173
make test        # corre la suite de tests
```

### Manual

```bash
# Backend
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edita .env con tus valores (DEEPSEEK_API_KEY opcional para desarrollo)
uvicorn app.main:app --reload

# Frontend (otra terminal)
cd frontend
npm install
npm run dev
```

---

## Reentrenar el modelo

```bash
# Desde la raíz del repositorio
make retrain

# Equivalente manual
.venv/Scripts/python.exe retrain_invima.py --db openfarma.db
```

El script entrena `CalibratedClassifierCV + RandomForestClassifier` con los datos actuales en `openfarma.db` y reemplaza `backend/data/modelo_rf.pkl`. Commitear el `.pkl` actualizado para que Railway lo use en producción.

---

## Troubleshooting

### La API devuelve 500 en `/medicamentos/buscar`

- Verifica que `DATABASE_URL` apunte al archivo correcto.
- En Railway, el path del volumen es `/data/openfarma.db` — diferente al path local.

### `PermissionError [WinError 32]` al arrancar en Windows

Ocurre si `DATABASE_URL` apunta al mismo archivo que el startup intenta copiar. Asegúrate de que `.env` local tenga `DATABASE_URL=sqlite:///./openfarma.db` (relativo, no absoluto).

### Frontend no conecta al backend

Verifica `CORS_ORIGINS` en `.env` o variables de Railway. El proxy `/api` en Vite solo aplica en desarrollo local (ver `frontend/vite.config.ts`).

### Tests fallan con `ModuleNotFoundError`

Asegúrate de que `PYTHONPATH` incluya el directorio `backend/`:

```bash
PYTHONPATH=backend pytest tests/
```

### Los logs de ETL no aparecen en Railway

Railway captura stdout. Asegúrate de usar `print()` o `logging` sin buffering: `python -u script.py`.
