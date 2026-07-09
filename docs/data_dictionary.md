# Diccionario de Datos

## Tabla: `cum_normalizado`

Versión local normalizada del CUM activo. 52,830 productos.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `expediente_cum` | TEXT | Número de expediente CUM (ej: `20176695`) |
| `consecutivo_cum` | TEXT | Consecutivo dentro del expediente (ej: `1`) |
| `nombre_comercial_norm` | TEXT | Nombre del producto en mayúsculas normalizadas |
| `principios_dci` | JSON | Lista de DCIs (Denominación Común Internacional OMS) |
| `tipo_formula` | TEXT | `monocomponente` o `combinado` |
| `forma_normalizada` | TEXT | Forma farmacéutica normalizada (ver `grupo_via`) |
| `via_normalizada` | JSON | Lista de vías de administración |
| `atc_normalizado` | TEXT | Código ATC hasta nivel 7 (corregido con LLM cuando CUM tiene error) |
| `dosis_total_mg` | REAL | Dosis total en mg (NULL si no aplica o unidades especiales) |
| `concentracion_mg_ml` | REAL | Concentración mg/mL para líquidos (NULL si no aplica) |
| `volumen_ml_por_unidad` | REAL | Volumen por unidad (NULL si no aplica) |
| `estado_cum` | TEXT | `Activo` / `Inactivo` |
| `estado_registro` | TEXT | `Vigente` / `Vencido` / `Cancelado` |
| `titular_registro` | TEXT | Empresa titular del registro sanitario |
| `registro_sanitario` | TEXT | Número de registro sanitario INVIMA |
| `fuente` | TEXT | `CUM_ACTIVO` o `CUM_RENOVACION` |
| `componentes` | JSON | Lista de componentes para fórmulas combinadas |
| `notas` | TEXT | Notas del proceso de normalización LLM |

---

## Tabla: `grupos_equivalencia`

3,204 grupos de equivalencia terapéutica.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | INTEGER | Identificador del grupo |
| `dci_key` | TEXT | `\|\|`.join(sorted(principios_dci)) — llave del grupo |
| `grupo_via` | TEXT | Clasificación ruta/forma (ver abajo) |
| `concentracion_norm` | TEXT | Concentración canónica del grupo (ej: `500 mg`, `5 mg/mL`, `SIN_CONCENTRACION`) |
| `cum_ids` | JSON | Lista de `expediente-consecutivo` de productos en el grupo |
| `atc_normalizado` | TEXT | ATC del grupo (nivel 7) |

**Valores de `grupo_via`:**

| Valor | Descripción |
|-------|-------------|
| `SOLIDO_ORAL` | Tabletas, cápsulas, comprimidos (liberación inmediata) |
| `SOLIDO_ORAL_LP` | Tabletas/cápsulas de liberación prolongada (LP, SR, ER, MR, XL) |
| `LIQUIDO_ORAL` | Jarabes, suspensiones, soluciones orales |
| `INYECTABLE` | IV, IM, SC — todas las vías parenterales |
| `TOPICO` | Cremas, ungüentos, geles dérmicos |
| `OFTALMICO` | Colirios, ungüentos oftálmicos |
| `INHALADO` | MDI, DPI, nebulización |
| `VAGINAL` | Óvulos, cremas vaginales |
| `TRANSDERMICO` | Parches transdérmicos |
| `NASAL` | Sprays nasales |
| `RECTAL` | Supositorios, enemas |
| `OTICO` | Gotas óticas |
| `SUBLINGUAL` | Tabletas sublinguales |

---

## Tabla: `invima_seguimiento`

9,795 entradas de alertas INVIMA. Fuente: PDFs mensuales.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | INTEGER | Identificador interno |
| `mes` | INTEGER | Mes de la alerta (1–12) |
| `anio` | INTEGER | Año de la alerta |
| `principio_activo` | TEXT | Nombre del principio activo tal como aparece en el PDF |
| `forma` | TEXT | Forma farmacéutica (fragmentada en algunos PDFs) |
| `concentracion` | TEXT | Concentración (fragmentada en algunos PDFs) |
| `laboratorio` | TEXT | Nombre del laboratorio |
| `estado` | TEXT | `MONITORIZACION` / `NO_DESABASTECIMIENTO` / `NO_COMERCIALIZADO` |
| `atc` | TEXT | ATC inferido via cruce con CUM |
| `severidad` | INTEGER | Escala 0–5 (ver abajo) |

**Escala de severidad:**

| Valor | Significado |
|-------|------------|
| 0 | Sin alerta activa |
| 1 | Descontinuado (decisión comercial) |
| 2 | No comercializado (retirado, no escasez) |
| 3 | En monitorización (señal temprana) |
| 4 | En riesgo de desabastecimiento |
| 5 | Desabastecido (confirmado) |

---

## Tabla: `reportes_no_disponibilidad`

Reportes ciudadanos de medicamentos no encontrados en farmacias.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | INTEGER | Identificador interno |
| `cum_id` | TEXT | `expediente-consecutivo` del medicamento reportado |
| `nombre_medicamento` | TEXT | Nombre comercial del medicamento |
| `tipo_reporte` | TEXT | `sin_stock` (default) / `precio_alto` / `calidad_deficiente` |
| `descripcion` | TEXT | Texto libre opcional del ciudadano |
| `fecha` | DATETIME | Fecha y hora del reporte (UTC) |

> **Nota:** El campo `region_id` fue eliminado en v1.4.0. La escasez farmacéutica en Colombia tiene alcance nacional; la geolocalización por departamento no aporta señal diferenciada y añadía fricción al formulario ciudadano.

---

## Features del Modelo ML

Las 15 features que alimentan el `RandomForestClassifier`:

### Features de estructura de mercado (CUM)

| Feature | Tipo | Descripción |
|---------|------|-------------|
| `tasa_inactivacion_atc5` | REAL (0–1) | % de registros del mismo grupo ATC5 que están inactivos |
| `num_competidores` | INTEGER | Cantidad de titulares distintos con el mismo principio activo + forma |
| `monopolio` | BINARY | 1 si hay un solo comercializador |
| `tiene_alternativas` | BINARY | 1 si hay más de un comercializador |
| `num_presentaciones_activas` | INTEGER | Presentaciones activas del mismo expediente |
| `es_combinado` | BINARY | 1 si es fórmula con más de un principio activo |
| `tipo_formula_num` | INTEGER | Número de principios activos (1, 2, 3+) |
| `grupo_atc_enc` | INTEGER | Categoría anatómica ATC codificada (A=0, B=1, ... Z=25) |
| `busquedas_norm` | REAL (0–1) | Búsquedas recientes normalizadas (actualmente 0, pendiente) |
| `reportes_norm` | REAL (0–1) | Reportes ciudadanos normalizados |

### Features de historial INVIMA

| Feature | Tipo | Importancia | Descripción |
|---------|------|-------------|-------------|
| `invima_sev_actual` | REAL (0–5) | 28.3% | Severidad el mes inmediatamente anterior |
| `invima_peor_sev_hist` | REAL (0–5) | 21.7% | Severidad máxima en todo el historial |
| `invima_meses_monitoreado` | INTEGER | 12.0% | Meses con cualquier estado INVIMA |
| `invima_sev_t3_avg` | REAL (0–5) | 11.1% | Promedio de severidad últimos 3 meses |
| `invima_tendencia` | REAL | 1.2% | promedio_últimos_3m − promedio_anteriores_3m |
