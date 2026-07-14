# Marco Metodológico — CRISP-ML(Q)

OpenFarma sigue el ciclo **CRISP-ML(Q)** (Cross-Industry Standard Process for Machine Learning with Quality Assurance), adaptado al contexto de datos abiertos y salud pública colombiana.

---

## Fase 1 — Comprensión del Negocio

**Objetivo de negocio:** Reducir el impacto del desabastecimiento farmacéutico mediante alertas tempranas basadas en datos.

**Objetivo de ML:** Clasificar medicamentos según su probabilidad de entrar en desabastecimiento en el siguiente mes (tarea de clasificación binaria).

**KPI principal:** ROC-AUC ≥ 0.80 con split temporal honesto (sin data leakage).

---

## Fase 2 — Comprensión de los Datos

### Fuentes primarias

1. **CUM activo** (Socrata API `i7cb-raxc`): estado del registro, titular, forma farmacéutica, ATC, concentración — 52,000+ registros
2. **CUM renovación** (Socrata API `vgr4-gemg`): medicamentos en trámite de renovación de registro
3. **Alertas INVIMA** (PDFs mensuales): 3 categorías — MONITORIZACION, NO_DESABASTECIMIENTO, NO_COMERCIALIZADO — 17 meses, 9,795 entradas

### Integración de fuentes

Las fuentes se cruzan usando el código ATC (Clasificación Anatómica, Terapéutica y Química, niveles 5-7) como llave primaria de integración. El CUM tiene ATC hasta nivel 7; las alertas INVIMA se indexan por principio activo → ATC via tabla `invima_seguimiento`.

---

## Fase 3 — Preparación de Datos

### Pipeline ETL

```
PDF INVIMA → pdfminer → _limpiar_entrada() → invima_seguimiento (SQLite)
Socrata API → httpx async → agrupar_y_transformar() → cum_normalizado (SQLite)
cum_normalizado + invima_seguimiento → construir_features() → DataFrame entrenamiento
```

### Normalización de DCI

El CUM usa nombres comerciales y genéricos mezclados. Se implementó:
- Tabla `_SINONIMOS` (~420 entradas): variantes inglés/español, nombres colombianos (ACETAMINOFEN→PARACETAMOL)
- Tabla `grupos_equivalencia`: 3,204 grupos terapéuticos con DCI normalizado (Denominación Común Internacional OMS)
- Auditoría continua de 104 rondas para correcciones específicas

### Features engineered

Ver `docs/data_dictionary.md` para definición completa de las 15 features.

---

## Fase 4 — Modelado

### Selección del modelo

Se evaluaron:
- Regresión Logística (baseline)
- Random Forest
- Gradient Boosting (XGBoost)

**Seleccionado:** `RandomForestClassifier` con calibración de probabilidades (`CalibratedClassifierCV`, método Platt).

**Razón:** Mejor ROC-AUC en test temporal; las probabilidades calibradas permiten mapear a niveles de riesgo (Bajo/Medio/Alto/Crítico) con semántica real.

### Estrategia de split temporal

El historial INVIMA tiene 17 meses. Se generan filas por (principio_activo × mes_objetivo):
- **Train:** meses enero 2025 – febrero 2026 (14 meses)
- **Test:** meses marzo – mayo 2026 (últimos 3 meses)

Esta estrategia evita data leakage: el modelo nunca ve información futura durante el entrenamiento.

---

## Fase 5 — Evaluación

| Métrica | Valor | Interpretación |
|---------|-------|----------------|
| ROC-AUC | 0.8374 | Excelente discriminación |
| Avg Precision | 0.1707 | Alto en contexto de clase muy desbalanceada (1.6% positivos) |
| Feature más importante | `invima_sev_actual` (28.3%) | La severidad del mes anterior es la señal más fuerte |

**Pruebas de equidad (bias):** Verificación de que el modelo no clasifica sistemáticamente como anomalía a ningún grupo ATC específico por estructura de datos, sino por señal real de riesgo.

---

## Fase 6 — Despliegue

- **API REST** (FastAPI): endpoint `/predicciones/{cum_id}` retorna probabilidad + nivel de riesgo
- **Integración frontend**: ficha de cada medicamento muestra nivel de riesgo con explicación ciudadana
- **Reentrenamiento automático**: script `retrain_invima.py` — se ejecuta mensualmente cuando INVIMA publica nuevo PDF
- **Monitoreo de drift:** comparación de distribución de features mes a mes (implementación pendiente)
