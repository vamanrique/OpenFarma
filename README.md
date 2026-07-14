# OpenFarma — Sistema de Alerta Temprana de Desabastecimiento Farmacéutico

**Nivel:** Avanzado · **Concurso:** Datos al Ecosistema 2026 · **datos.gov.co**

> Plataforma de inteligencia farmacéutica que combina datos abiertos del CUM, historial de alertas del INVIMA y reportes ciudadanos para predecir y alertar sobre el desabastecimiento de medicamentos en Colombia antes de que ocurra.

---

## Problema

El desabastecimiento de medicamentos afecta a millones de pacientes colombianos cada año. Las alertas del INVIMA llegan tarde — cuando el problema ya es crítico. No existe un sistema público que integre señales tempranas (variaciones en el mercado, historial de alertas, reportes ciudadanos) para anticipar escasez.

**OpenFarma** resuelve esto con tres componentes:
1. **Búsqueda inteligente** del Catálogo Único de Medicamentos (CUM) en tiempo real
2. **Modelo predictivo** de desabastecimiento con ROC-AUC 0.8374
3. **Canal ciudadano** de reporte de no disponibilidad → alimenta el modelo

---

## Datos Utilizados

| Dataset | Fuente | Registros |
|---------|--------|-----------|
| Catálogo Único de Medicamentos (CUM) activos | [datos.gov.co · i7cb-raxc](https://www.datos.gov.co/resource/i7cb-raxc.json) | ~52,000 presentaciones |
| CUM — Registros en trámite de renovación | [datos.gov.co · vgr4-gemg](https://www.datos.gov.co/resource/vgr4-gemg.json) | ~8,000 registros |
| Historial de alertas INVIMA (PDF) | Portal INVIMA | 17 meses, 9,795 entradas (ene 2025 – may 2026) |
| Reportes ciudadanos | OpenFarma (formulario propio) | En crecimiento |

---

## Arquitectura

```
[Ciudadano]
     │
     ▼
[React Frontend] ──► [FastAPI Backend] ──► [Socrata API / datos.gov.co]
                            │
                            ├──► [SQLite: cum_normalizado, grupos_equivalencia]
                            ├──► [INVIMA: cache en memoria (PDF scraper)]
                            └──► [Modelo ML: CalibratedRandomForest]
```

**Flujo de búsqueda:**
1. El usuario escribe un medicamento → consulta en tiempo real a datos.gov.co (CUM activo + renovación)
2. Si Socrata no responde → fallback local en `cum_normalizado` (52,830 productos)
3. Enriquecimiento con grupos de equivalencia → muestra alternativas terapéuticas y estado INVIMA
4. Predicción de riesgo de desabastecimiento para el mes siguiente

---

## Modelo Predictivo

| Métrica | Valor | Interpretación |
|---------|-------|----------------|
| ROC-AUC | **0.8374** | Discriminación excelente |
| Avg Precision | 0.1707 | Alta en contexto de 1.6% positivos |
| Split | Temporal honesto | Últimos 3 meses = test; nunca vio el futuro |

**Tipo:** `CalibratedClassifierCV` sobre `RandomForestClassifier` (scikit-learn 1.9.0)

**Features más importantes:**
- Severidad INVIMA el mes anterior (28.3%)
- Peor severidad histórica (21.7%)
- Meses bajo monitorización INVIMA (12.0%)
- Tendencia reciente (promedio 3m vs anterior)
- Estructura de mercado: número de competidores, monopolio, tasa de inactivación ATC

---

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11 · FastAPI · SQLAlchemy · SQLite |
| Frontend | React 18 · Vite · Tailwind CSS |
| ML | scikit-learn 1.9.0 · pandas · numpy |
| ETL / NLP | DeepSeek API (clasificación farmacológica ATC) |
| Deploy | Railway (auto-deploy desde `main`) |
| Datos | Socrata SODA API · httpx (async) · pdfminer |

---

## Instalación y Ejecución Local

### Requisitos
- Python 3.11+
- Node.js 20+

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

La API queda disponible en `http://localhost:8000`. Documentación interactiva: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

El frontend queda disponible en `http://localhost:5173`

---

## Endpoints Principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/medicamentos/buscar?q=ibuprofeno` | Búsqueda en tiempo real (CUM + fallback local) |
| GET | `/medicamentos/{cum_id}/alternativas` | Alternativas terapéuticas por grupo ATC |
| GET | `/predicciones/{cum_id}` | Predicción de desabastecimiento (0–1) |
| GET | `/invima/estado/{atc}` | Estado de alerta INVIMA por código ATC |
| POST | `/reportes` | Reportar medicamento no disponible |

---

## Estructura del Repositorio

```
openfarma/
├── RECURSOS/               # Presentación del proyecto
├── README.md
├── LICENSE
├── Changelog.md
├── requirements.txt
├── nixpacks.toml           # Configuración de deploy Railway
├── docs/                   # Documentación técnica y metodológica
├── notebooks/              # Análisis exploratorio y notebooks
├── backend/
│   ├── app/                # API FastAPI
│   ├── etl/                # Pipeline de datos (INVIMA, CUM, transformación)
│   ├── data/               # Modelo ML y datos auxiliares
│   └── openfarma.db        # SQLite con CUM normalizado y grupos
├── frontend/
│   └── src/                # React + Tailwind
└── reports/                # Figuras y reporte final
```

---

## Demo

**URL de producción:** [https://openfarma-production.up.railway.app](https://openfarma-production.up.railway.app)

---

## Equipo

Concurso Datos al Ecosistema 2026 — Categoría Avanzado

Contacto: vamanrique@gmail.com

---

## Licencia

MIT License — ver [LICENSE](LICENSE)
