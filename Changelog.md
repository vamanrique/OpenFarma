# Changelog

Todos los cambios relevantes del proyecto OpenFarma se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).

---

## [1.9.0] — 2026-07-13

### Añadido
- **`busquedas_norm` real en entrenamiento**: `retrain_invima.py` ahora carga `busquedas_log` y enriquece `busquedas_norm` para el modelo de producción (eval/train sigue en 0.0 — sin historial); listo para crecer con datos reales

### Corregido
- **`main.py` — copia DB sobre sí misma**: guard `_bundled_db.resolve() != _volume_path.resolve()` antes de `shutil.copy2`; evitaba `PermissionError [WinError 32]` en tests locales cuando `DATABASE_URL` apuntaba al mismo archivo bundleado

### Mejorado
- **Modelo ML reentrenado** (2026-07-13): ROC-AUC **0.8374** | Avg Precision **0.1707** (split temporal honesto, test mar–may 2026)
- **`docs/model_card.md`**: métricas actualizadas al retrain 2026-07-13

---

## [1.8.0] — 2026-07-09

### Añadido
- **Tab "Mapa de riesgo"**: `MapaRiesgo.tsx` (existía) ahora integrado en navegación principal — mapa interactivo de Colombia con riesgo por departamento y filtro por nivel (Bajo/Medio/Alto/Crítico)
- **`busquedas_norm` conectado a datos reales**: cada búsqueda registra los CUMs retornados en `busquedas_log` (background task asíncrona); el modelo normaliza búsquedas de los últimos 30 días (0–100 búsquedas = 0–1.0)
- **Tabla `busquedas_log`**: nueva tabla creada via migración idempotente en startup (`_crear_busquedas_log`)
- **Tests de integración API**: `tests/integration/test_api_endpoints.py` — 10 tests con TestClient (búsqueda fallback, predicción, dashboard vigilancia, reportes, grupos)
- **`tests/conftest.py`**: configura `DATABASE_URL` antes de cualquier import de app, resuelve path al DB real en `backend/openfarma.db`

### Corregido
- **`.gitattributes`**: añadido `*.db binary` para prevenir que `core.autocrlf=true` en Windows corrompa el archivo binario SQLite al hacer checkout (causa raíz de corrupción del DB local detectada y eliminada)
- **`test_transformacion_combinado`**: `tipo_formula == "combinado"` actualizado a `in ("combinado", "biconjugado")` para reflejar nomenclatura canónica actual
- **CI/CD integration tests**: `DATABASE_URL` ahora pasado como env var para que TestClient encuentre el DB correcto en workflows de GitHub Actions

---

## [1.7.0] — 2026-07-09

### Corregido
- **Ronda 105 de auditoría INN**: 700 productos en `cum_normalizado` con `principios_dci` desincronizado respecto al `dci_key` de su grupo corregidos — 35 patrones de sustitución cubriendo: sinónimos HIOSCINA (HIOSCINA / HIOSCINA BUTILBROMURO / HIOSCINA N-BUTILBROMURO / ESCOPOLAMINA / IBUPROFENO‖SCOPOLAMINA → BUTILBROMURO DE HIOSCINA), typo OOLANZAPINAA→OLANZAPINA, ortografía CLORFENAMINA→CLORFENIRAMINA, género ENTACAPONE→ENTACAPONA, tildes (CAFEÍNA→CAFEINA, ÁCIDO CLAVULÁNICO→ACIDO CLAVULANICO, ARTÍCAINA→ARTICAINA, ÁCAROS→ACAROS), duplicados (BETAMETASONA‖BETAMETASONA, DEXAMETASONA‖DEXAMETASONA, CALCIO‖POTASIO‖SODIO‖SODIO), INN (CADENA MEDIANA→CADENA MEDIA, SUCCILINADA→SUCCINILADA, TRETINOINA→ACIDO RETINOICO), nombres comerciales→INN (LAMICOL→TERBINAFINA, OVALE CHAMPU→KETOCONAZOL, DCI→KETOCONAZOL), y Neosaldina con DCI de lote ETL contaminado (BUTILBROMURO DE HIOSCINA‖CAFEÍNA‖METAMIZOL→CAFEINA‖ISOMETEPTENO‖METAMIZOL)
- **Corrección de grupo para Baxul F**: 2 productos (expediente 20007872) con DCI correcto BROMHEXINA‖FENILEFRINA‖PARACETAMOL estaban asignados al grupo BACLOFENO — removidos y reagrupados en nuevo grupo BROMHEXINA‖FENILEFRINA‖PARACETAMOL (id=3927)
- **Tenaflox (19938260-1)**: `principios_dci` corregido de METRONIDAZOL a LEVOFLOXACINO (nombre comercial con sufijo -flox, misma asignación de grupo LEVOFLOXACINO confirmada)
- **FEIBA (226747-4)**: `principios_dci` corregido de FACTOR VIII a FACTOR VIII INHIBIDOR BYPASS ACTIVITY (FEIBA = Factor Eight Inhibitor Bypassing Activity)

---

## [1.6.0] — 2026-07-09

### Añadido
- **Endpoint `GET /predicciones/{cum_id}`**: predicción nacional de riesgo de desabastecimiento para el próximo mes (probabilidad + nivel Bajo/Medio/Alto/Crítico + top features), conforme a la especificación OpenAPI documentada
- **Badge de riesgo ML en ficha de medicamento**: al seleccionar un medicamento en el buscador aparece `ML XX%` con color semántico (verde/ámbar/naranja/rojo), obtenido del modelo RandomForest en tiempo real
- **Endpoint `GET /reportes/dashboard`**: vigilancia ciudadana con top 20 medicamentos más reportados, spike detector (ratio hoy vs. promedio semanal), y señales anticipadas (spike ≥ 3 reportes/7d sin alerta INVIMA)
- **Panel "Vigilancia ciudadana"** en PanelModelo: KPIs de reportes, sección de señales anticipadas destacadas, tabla top reportados cruzada con estado INVIMA
- **`reportes_norm` conectado a datos reales**: el modelo ahora usa el conteo real de reportes ciudadanos por CUM (normalizado 0–20 reportes = 0–1.0) en lugar de siempre 0
- **`docs/model_card.md`**: ficha técnica completa del modelo (datos de entrenamiento, features, métricas, evaluación de equidad, limitaciones, uso previsto, proceso de actualización)

### Corregido
- Test de sesgo `test_sin_sesgo_por_atc_grupo`: import y acceso al modelo corregidos (`artefacto["modelo"]` — clave correcta del pkl)
- `GET /predicciones/mapa`: N+1 queries eliminado con `joinedload(region)` en la consulta SQLAlchemy

---

## [1.5.0] — 2026-07-09

### Corregido
- **Backend — endpoint muerto eliminado**: `GET /reportes/estadisticas/{region_id}` referenciaba `ConsultaRegion` nunca importada → NameError 500 al llamarse; endpoint eliminado junto con el concepto de región ya descartado
- **Backend — manejo de timeout diferenciado**: timeout de Socrata en `/medicamentos/{cum_id}/alternativas` ahora logea `ERROR` con causa específica (antes logueaba como `WARNING` genérico indiferenciado)
- **Backend — registros INVIMA sin ATC**: registros con `atc = NULL` en `invima_seguimiento` ahora se descartan explícitamente con log de advertencia en lugar de omitirse silenciosamente
- **Tests — import incorrecto en bias tests**: `from app.services.prediccion_service import cargar_modelo` → `from app.ml.modelo import cargar_modelo` (módulo correcto)
- **Tests — assert incorrecto**: `hasattr(artefacto, "modelo_prod")` → `"modelo_prod" in artefacto` (`cargar_modelo()` retorna dict, no objeto con atributos)
- **Tests — dependencias faltantes**: `pytest>=7.4.0` y `pytest-asyncio>=0.21.0` agregados a `requirements.txt`; se eliminó la instalación manual duplicada en el pipeline CI/CD
- **CI/CD — PYTHONPATH relativo**: reemplazado `PYTHONPATH: backend` por `PYTHONPATH: ${{ github.workspace }}/backend` en los tres pasos de test para garantizar resolución correcta desde cualquier directorio de trabajo
- **Frontend — null crash en laboratorio**: `m.laboratorio.split(...)` → `(m.laboratorio ?? '—').split(...)` en la lista agrupada del buscador; evita crash cuando laboratorio es `null`
- **Frontend — React keys con índice**: reemplazados `key={i}` por `key={p.cum_id}` en `GrupoSection` y `key={dci}` en DCIs del panel de ficha; evita pérdida de estado al reordenar listas
- **Frontend — null guard en reportes**: `setRecientes(r.data)` / `setTotal(t.data.total)` ahora protegidos con `r?.data` / `t?.data?.total != null` en `loadRecientes()`

### Mejorado
- **Accesibilidad**: navegación por pestañas en `App.tsx` con `role="tablist"`, `role="tab"` y `aria-selected`; botón de alternativas terapéuticas con `aria-expanded`

---

## [1.4.0] — 2026-07-09

### Añadido
- Notebooks Jupyter (01–05): EDA, limpieza/transformación, análisis descriptivo, modelo predictivo y reportes automáticos — estructura requerida categoría Avanzado del concurso
- Estructura completa del concurso Avanzado: `docs/` (8 documentos), `tests/` (unit, integration, bias), `reports/`, `RECURSOS/`, `.github/workflows/ci-cd-pipeline.yml`
- Normalización de unidades farmacéuticas en el frontend: `mg`, `mL`, `mg/mL`, `mcg`, `mEq`, `mmol`; `IU` → `UI`

### Mejorado
- Badge INVIMA ahora muestra el período del reporte oficial: `⚠ INVIMA may 2026 · Monitorización` en lugar del estado solo

### Corregido
- Campo `region_id` eliminado del formulario de reportes ciudadanos y de la tabla `reportes_no_disponibilidad` (no aportaba señal diferenciada; la escasez farmacéutica en Colombia es de alcance nacional)
- `PYTHONPATH` configurado en el pipeline CI/CD para importaciones correctas del backend en los tres conjuntos de tests

---

## [1.3.0] — 2026-07-08

### Añadido
- Fallback de búsqueda local cuando datos.gov.co (Socrata) no está disponible
- Los 52,830 medicamentos del CUM normalizado quedan accesibles sin conexión a internet
- Mensaje diferenciado en el frontend: distingue error de Socrata vs. error de backend

### Corregido
- Error 500 en `/buscar` cuando la API Socrata retornaba timeout o error HTTP
- Error 500 en `/modelo/info` cuando el archivo pkl no estaba accesible

---

## [1.2.0] — 2026-07-03

### Añadido
- Pipeline de reportes ciudadanos conectado al modelo ML (`reportes_norm` feature)
- OG tags para compartir en redes sociales (portada del proyecto)
- Preservación de reportes entre deploys Railway (volumen persistente)

---

## [1.1.0] — 2026-06-30

### Añadido
- Modelo predictivo de desabastecimiento v1: `CalibratedClassifierCV` + `RandomForestClassifier`
- ROC-AUC 0.87 con split temporal honesto (últimos 3 meses como test)
- 15 features: 10 de estructura de mercado CUM + 5 de historial INVIMA
- Endpoint `/predicciones/{cum_id}` con nivel de riesgo (Bajo/Medio/Alto/Crítico)
- Auditoría INN ronda 104: 3,204 grupos con concentración 100% normalizada, 0 duplicados

### Corregido
- Data leakage en el entrenamiento del modelo (split aleatorio → split temporal)
- ATC de medicamentos en INVIMA que no coincidían con CUM: corregidos con LLM

---

## [1.0.0] — 2026-06-08

### Añadido
- Búsqueda en tiempo real del CUM vía Socrata API (datos.gov.co)
- Sistema de grupos de equivalencia terapéutica (3,204 grupos)
- Alternativas A0–A7: mismo grupo (A0-A3) + clase ATC (A4-A7)
- Integración con historial INVIMA: 17 meses, 9,795 registros (ene 2025 – may 2026)
- Estado de alerta INVIMA en tiempo real en la ficha de cada medicamento
- Normalización 100% de DCIs (Denominación Común Internacional) — 52,830 productos
- Rediseño de UI: búsqueda hero, accesibilidad de fuentes, navegación por teclado

### Técnico
- ETL INVIMA: scraper de PDFs del portal INVIMA con inferencia de mes/año
- `cum_normalizado`: tabla local con 52,830 productos para búsqueda offline
- `grupos_equivalencia`: tabla central del sistema de equivalencia
- Pipeline DeepSeek para clasificación farmacológica ATC y normalización INN

---

## [0.1.0] — 2026-05-15

### Añadido
- Prototipo inicial: búsqueda de medicamentos en CUM activos
- Backend FastAPI + frontend React básico
- Deploy inicial en Railway

---

*OpenFarma — Concurso Datos al Ecosistema 2026*
