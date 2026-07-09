# Model Card — FarmaVigia: Modelo de Predicción de Desabastecimiento Farmacéutico

**Versión del modelo:** 1.0.0  
**Fecha de entrenamiento:** Julio 2026  
**Archivo de producción:** `backend/data/modelo_rf.pkl`  
**Proyecto:** Datos al Ecosistema 2026 — datos.gov.co

---

## 1. Descripción General

| Campo | Valor |
|-------|-------|
| **Tipo** | `CalibratedClassifierCV` (Platt scaling) sobre `RandomForestClassifier` |
| **Librería** | scikit-learn 1.9.0 |
| **Tarea** | Clasificación binaria: ¿estará este medicamento en desabastecimiento el próximo mes? |
| **Salida** | Probabilidad continua [0, 1] convertida a nivel de riesgo |
| **Dominio** | Mercado farmacéutico colombiano (~52,000 presentaciones activas) |

El modelo predice, para cada presentación del Catálogo Único de Medicamentos (CUM), la probabilidad de que el mes siguiente aparezca en los comunicados INVIMA bajo estado de desabastecimiento confirmado o en riesgo. La calibración Platt asegura que las probabilidades tengan interpretación estadística real (un score de 0.40 significa que el modelo ha observado desabastecimiento en ~40% de casos con ese perfil).

### Niveles de riesgo

| Nivel | Rango de probabilidad |
|-------|-----------------------|
| Bajo | < 25% |
| Medio | 25% – 50% |
| Alto | 50% – 75% |
| Crítico | > 75% |

---

## 2. Datos de Entrenamiento

### Fuentes

| Fuente | Entidad | Cobertura | Registros |
|--------|---------|-----------|-----------|
| Comunicados INVIMA (PDFs mensuales) | INVIMA | Enero 2025 – Mayo 2026 | 9,795 entradas limpias |
| CUM activo (Socrata `i7cb-raxc`) | INVIMA / datos.gov.co | Snapshot al momento del entrenamiento | ~52,830 presentaciones |
| CUM en renovación (Socrata `vgr4-gemg`) | INVIMA / datos.gov.co | Complementario | ~8,000 |

### Construcción del dataset de entrenamiento

El dataset se genera como producto cruzado **(principio_activo × mes_objetivo)**. Cada fila representa el estado de un principio activo en un mes dado, usando exclusivamente información disponible _antes_ del mes objetivo:

- Features INVIMA: derivadas del historial acumulado hasta el mes inmediatamente anterior al mes objetivo.
- Features CUM: estructura de mercado observada al momento de inferencia (estática en el período de entrenamiento).

**Volumen total:** ~450,000 filas (≈ 7,100 principios activos × 14–17 meses × expansión a CUM).  
**Tasa de positivos (y=1):** 1.6% (clase altamente desbalanceada — refleja la realidad del mercado).

### Estrategia de split temporal (sin data leakage)

| Conjunto | Período | Meses |
|----------|---------|-------|
| Entrenamiento | Enero 2025 – Febrero 2026 | 14 meses |
| Test (evaluación honesta) | Marzo – Mayo 2026 | 3 meses |

El modelo de producción (`modelo_prod`) se reentrena sobre el dataset completo (17 meses) para maximizar cobertura. Las métricas reportadas provienen de `modelo_eval` entrenado solo sobre los primeros 14 meses y evaluado en los 3 restantes.

> **Por qué este split es crítico:** con un split aleatorio, el mismo principio activo puede aparecer en train (mes 3) y test (mes 8). Los desabastecimientos duran varios meses, por lo que `invima_sev_actual` del mes anterior es casi idéntico al target: el modelo memorizaría, no aprendería. ROC-AUC con split aleatorio alcanzaba 1.000 — data leakage trivial.

---

## 3. Variables del Modelo (Features)

El modelo usa exactamente 15 variables en el orden de `FEATURE_COLS`.

### 3.1 Estructura de mercado CUM (10 variables)

| # | Variable | Tipo | Descripción |
|---|----------|------|-------------|
| 1 | `tasa_inactivacion_atc5` | Numérica [0,1] | Porcentaje de registros inactivos dentro del mismo grupo ATC nivel 5. Proxy de abandono del mercado en la categoría terapéutica. |
| 2 | `num_competidores` | Entera ≥ 1 | Número de titulares distintos que comercializan la misma forma farmacéutica y principio activo. |
| 3 | `tiene_alternativas` | Binaria (0/1) | 1 si existe más de un titular comercializando el producto (opuesto de monopolio). |
| 4 | `tipo_formula_num` | Entera ≥ 1 | Número de principios activos en la fórmula (1 = monocomponente, 2 = bicomponente, etc.). |
| 5 | `es_combinado` | Binaria (0/1) | 1 si la fórmula contiene más de un principio activo. |
| 6 | `monopolio` | Binaria (0/1) | 1 si existe un único titular comercial. Los monopolios son más vulnerables a desabastecimiento. |
| 7 | `grupo_atc_enc` | Categórica codificada | Categoría anatómica ATC de primer nivel, codificada numéricamente (A=0, B=1, C=2, ... V=15). |
| 8 | `num_presentaciones_activas` | Entera ≥ 0 | Número de presentaciones activas bajo el mismo expediente CUM. |
| 9 | `busquedas_norm` | Numérica [0,1] | Volumen de búsquedas recientes normalizado. Actualmente 0 para todos los productos (pendiente integración). |
| 10 | `reportes_norm` | Numérica [0,1] | Reportes ciudadanos de no disponibilidad recientes, normalizados. Cobertura baja en la fase actual. |

### 3.2 Historial INVIMA (5 variables)

Estas son las variables de mayor peso predictivo. Derivan del procesamiento de los PDFs mensuales INVIMA.

**Escala de severidad (0–5):**

| Valor | Estado INVIMA |
|-------|---------------|
| 0 | Sin alerta |
| 1 | Descontinuado |
| 2 | No comercializado |
| 3 | En monitorización |
| 4 | En riesgo |
| 5 | Desabastecimiento confirmado |

| # | Variable | Tipo | Descripción | Importancia |
|---|----------|------|-------------|-------------|
| 11 | `invima_sev_actual` | Numérica [0,5] | Severidad el mes inmediatamente anterior al mes objetivo. | **28.3%** |
| 12 | `invima_sev_t3_avg` | Numérica [0,5] | Promedio de severidad en los últimos 3 meses. Suaviza fluctuaciones. | **11.1%** |
| 13 | `invima_meses_monitoreado` | Entera ≥ 0 | Total de meses en los que el principio activo tuvo cualquier estado INVIMA. Proxy de historial problemático. | **12.0%** |
| 14 | `invima_peor_sev_hist` | Numérica [0,5] | Peor severidad registrada en todo el historial disponible. | **21.7%** |
| 15 | `invima_tendencia` | Numérica [-5,5] | Diferencia entre promedio de últimos 3 meses y promedio de los 3 meses previos. Positivo = empeorando. | 1.2% |

### 3.3 Importancias consolidadas

| Rango | Variable | Importancia estimada |
|-------|----------|---------------------|
| 1 | `invima_sev_actual` | 28.3% |
| 2 | `invima_peor_sev_hist` | 21.7% |
| 3 | `invima_meses_monitoreado` | 12.0% |
| 4 | `invima_sev_t3_avg` | 11.1% |
| 5 | `num_competidores` | ~8% |
| 6 | `tasa_inactivacion_atc5` | ~6% |
| 7–14 | Resto de variables CUM | < 5% cada una |
| 15 | `invima_tendencia` | 1.2% |

Las 5 variables INVIMA acumulan ~74% de la importancia total, confirmando que el historial regulatorio es la señal dominante.

---

## 4. Métricas de Rendimiento

Evaluación sobre el conjunto de test temporal (Marzo – Mayo 2026, datos nunca vistos durante el entrenamiento).

| Métrica | Valor | Contexto |
|---------|-------|---------|
| **ROC-AUC** | **0.8732** | Excelente discriminación. El modelo asigna mayor probabilidad al medicamento correcto en el 87.3% de los pares (desabastecido vs. disponible). |
| **Average Precision** | **0.1720** | Alto en el contexto de 1.6% de positivos. La AP esperada de un clasificador aleatorio en este dataset es 0.016; el modelo la multiplica por ~10.7×. |
| **Tasa de positivos (test)** | 1.6% | Desbalance real del mercado: la gran mayoría de medicamentos no está en desabastecimiento. |

**Interpretación de la Average Precision:** un valor de 0.17 con 1.6% de positivos es técnicamente sólido. El modelo genera falsos positivos inevitables a alta sensibilidad. Esto es aceptable en un sistema de alerta temprana: mejor priorizar un falso positivo que ignorar un desabastecimiento real.

---

## 5. Evaluación de Equidad (Bias Assessment)

### Naturaleza del modelo

El modelo predice sobre medicamentos, no sobre pacientes. No existen variables demográficas (edad, sexo, etnia, nivel socioeconómico). El riesgo de sesgo discriminatorio directo contra grupos poblacionales es bajo por diseño.

### Prueba de equidad entre grupos terapéuticos

Se verifica que el modelo no clasifique sistemáticamente como "de alto riesgo" a ningún grupo ATC por artefactos de la estructura de datos, sino únicamente por señal real de riesgo.

**Metodología:** Para productos con historial INVIMA neutro (severidad = 0 en todos los meses), se computa la distribución de scores predichos por grupo ATC. La varianza entre grupos debe ser < 0.15.

**Resultado:** Varianza entre grupos ATC con historial neutro < 0.15 (umbral superado). No se detecta sesgo sistemático por categoría terapéutica.

### Limitaciones del análisis de equidad

- El análisis de equidad no cubre sesgos geográficos (el modelo no tiene variables de región).
- Los grupos ATC con muy pocos productos en el historial INVIMA tienen estimaciones menos estables.
- La cobertura geográfica real del mercado farmacéutico colombiano no está reflejada en el CUM (no hay datos de disponibilidad por departamento).

---

## 6. Limitaciones Conocidas

| Limitación | Impacto | Mitigación |
|------------|---------|-----------|
| **Baja tasa de positivos (1.6%)** | Alta sensibilidad genera falsos positivos. El nivel "Crítico" debe interpretarse como señal de alerta, no como diagnóstico definitivo. | Calibración Platt; uso de niveles de riesgo con semántica clara. |
| **`busquedas_norm` y `reportes_norm` = 0** | Dos variables del modelo no aportan señal en la fase actual. El modelo opera efectivamente con 13 variables. | Pendiente integración de búsquedas y masa crítica de reportes ciudadanos. |
| **Historial limitado a 17 meses** | El modelo no captura estacionalidades anuales completas ni ciclos de desabastecimiento multianual. | Se ampliará conforme INVIMA publique nuevos comunicados. |
| **Features CUM estáticas** | La estructura de mercado (competidores, presentaciones) se actualiza en cada reentrenamiento, no en tiempo real. | Reentrenamiento mensual sincronizado con publicaciones INVIMA. |
| **Medicamentos sin historial INVIMA** | El 85–90% de los productos CUM tienen `invima_sev_actual = 0` por ausencia de alertas previas. Para estos, el modelo depende casi exclusivamente de variables de estructura de mercado. | El modelo retorna niveles "Bajo" o "Medio" con alta confianza para productos sin historial — interpretación correcta dado el prior. |
| **Cambios regulatorios no anticipados** | Una resolución INVIMA que cambie la escala de severidad o los criterios de clasificación invalidaría parte del historial. | Monitoreo de cambios normativos en cada reentrenamiento. |

---

## 7. Uso Previsto

### Casos de uso autorizados

- **Alerta temprana ciudadana:** informar a pacientes y profesionales de salud sobre medicamentos con señal de riesgo, facilitando búsqueda de alternativas preventiva.
- **Priorización de vigilancia:** orientar la atención de equipos de farmacovigilancia hacia productos con señal elevada.
- **Investigación en salud pública:** análisis de patrones de desabastecimiento en el mercado colombiano.
- **Transparencia regulatoria:** complementar la información pública de INVIMA con una perspectiva predictiva basada en datos abiertos.

### Casos de uso no autorizados

- **Decisiones clínicas individuales:** el modelo no evalúa la idoneidad de un medicamento para un paciente específico.
- **Sustitución de alertas oficiales INVIMA:** el modelo es complementario, no sustituto, de los comunicados oficiales.
- **Acaparamiento o especulación comercial:** el uso de las predicciones para acumular inventarios o manipular precios va en contra del propósito del sistema.
- **Decisiones de compra institucional sin validación adicional:** hospitales e IPS deben contrastar las predicciones con sus propias cadenas de suministro y canales oficiales.

### API de producción

```
GET /predicciones/{cum_id}
Respuesta: { "probabilidad": 0.34, "nivel_riesgo": "Medio", "cum_id": "...", "nombre": "..." }
```

---

## 8. Proceso de Actualización (Reentrenamiento)

El modelo debe reentrenarse mensualmente, después de que INVIMA publique el nuevo comunicado de disponibilidad de medicamentos (aproximadamente los viernes de cada mes).

### Flujo de actualización

```
1. etl/invima_scraper.py   — descarga el nuevo PDF del portal INVIMA
2. etl/invima_parser.py    — extrae entradas y actualiza tabla invima_seguimiento (SQLite)
3. retrain_invima.py       — reconstruye features + reentrena + guarda modelo_rf.pkl
4. backend/data/modelo_rf.pkl se commitea al repositorio
5. Railway redeploy automático — el nuevo modelo entra en producción
```

### Comando de reentrenamiento

```bash
# Desde la raíz del repositorio
.venv/Scripts/python.exe retrain_invima.py --db farmavigia.db
```

### Criterios de aceptación antes de subir a producción

| Criterio | Umbral |
|----------|--------|
| ROC-AUC (split temporal) | ≥ 0.80 |
| Average Precision | ≥ 0.10 |
| Varianza ATC (bias test) | < 0.15 |
| Medicamentos con predicción | ≥ 50,000 (cobertura CUM) |

Si alguna métrica cae por debajo del umbral, investigar antes de reemplazar el modelo en producción.

### Trigger automatizado

El background task `_loop_viernes_invima()` en `backend/app/main.py` verifica cada 6 horas si INVIMA publicó un nuevo PDF. El trigger Cloud `trig_01YUczECNbarwSQfQu9ew4hr` (cron `0 14 * * 5`) dispara el proceso adicionalmente cada viernes a las 14:00.

---

## 9. Información Técnica Adicional

### Dependencias clave

| Componente | Versión |
|------------|---------|
| scikit-learn | 1.9.0 |
| Python | 3.11+ |
| Serialización | pickle (`.pkl`) |

### Reproducibilidad

El modelo es reproducible dado el mismo snapshot de `farmavigia.db` y el mismo código de `retrain_invima.py`. El split temporal es determinístico (basado en fechas, no en semillas aleatorias). La aleatoriedad interna de `RandomForestClassifier` se fija con `random_state`.

### Marco metodológico

El desarrollo sigue CRISP-ML(Q) (Cross-Industry Standard Process for Machine Learning with Quality Assurance). Ver `docs/marco_metodologico.md` para detalle completo de cada fase.

### Datos y licencias

- CUM INVIMA: Datos Abiertos Colombia — uso irrestricto (Ley 1712 de 2014).
- Comunicados INVIMA: información pública, acceso libre.
- Reportes ciudadanos: anónimos, sin datos personales almacenados.
- El modelo opera sobre datos agregados por principio activo / ATC — no genera perfiles individuales de pacientes ni empresas.
