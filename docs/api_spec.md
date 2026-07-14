# API Specification — OpenFarma

La API de OpenFarma sigue el estándar OpenAPI 3.0. Documentación interactiva (Swagger UI) disponible en producción: `https://openfarma-production.up.railway.app/docs`

---

## Base URL

```
https://openfarma-production.up.railway.app
```

---

## Endpoints

### GET /medicamentos/buscar

Búsqueda de medicamentos en tiempo real. Consulta la API Socrata del CUM activo y registros en renovación. Si Socrata no está disponible, usa búsqueda local en `cum_normalizado`.

**Parámetros:**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `q` | string | Sí | Término de búsqueda (mínimo 2 caracteres) |
| `solo_activos` | boolean | No (default: true) | Filtrar solo medicamentos con estado CUM activo |
| `limit` | integer | No (default: 20, max: 100) | Número máximo de resultados |

**Respuesta 200:**
```json
[
  {
    "cum_id": "20176695-1",
    "nombre_comercial": "IBUPROFENO KERN PHARMA",
    "principios_dci": ["IBUPROFENO"],
    "tipo_formula": "monocomponente",
    "concentracion_display": "400 mg",
    "presentacion": "CAJA X 10 TABLETAS RECUBIERTAS",
    "forma_farmaceutica": "TABLETA RECUBIERTA",
    "via_administracion": "ORAL",
    "atc": "M01AE01",
    "descripcion_atc": "IBUPROFENO",
    "laboratorio": "GENFAR S.A.",
    "registro_sanitario": "INVIMA 2017M-0023456",
    "estado_registro": "Vigente",
    "estado_cum": "Activo",
    "fuente": "CUM_ACTIVO",
    "estado_invima": {
      "estado": "EN_MONITORIZACION",
      "estado_label": "Monitorización",
      "mes": 5,
      "anio": 2026,
      "severidad": 3,
      "causas": null
    },
    "dosis_total_mg": 400.0
  }
]
```

---

### GET /medicamentos/{cum_id}/alternativas

Calcula alternativas terapéuticas para un medicamento dado.

**Parámetros de ruta:**

| Parámetro | Formato | Ejemplo |
|-----------|---------|---------|
| `cum_id` | `{expediente}-{consecutivo}` | `20176695-1` |

**Respuesta 200:**
```json
[
  {
    "cum_origen": "20176695-1",
    "cum_destino": "20098765-2",
    "tipo": "A1",
    "descripcion": "Mismo principio activo, misma forma, misma concentración — laboratorio diferente",
    "componentes_compartidos": ["IBUPROFENO"],
    "medicamento_destino": { "...": "objeto MedicamentoLiveRead completo" }
  }
]
```

**Tipos de alternativa:**

| Tipo | Criterio |
|------|---------|
| A0 | Exactamente el mismo producto (referencia) |
| A1 | Mismo PA + forma + concentración, diferente laboratorio |
| A2 | Mismo PA + forma, diferente concentración |
| A3 | Mismo PA, diferente forma |
| A4 | Misma clase ATC nivel 5 |
| A5 | Misma clase ATC nivel 4 |
| A6 | Misma clase ATC nivel 3 |
| A7 | Misma clase ATC nivel 2 |

---

### GET /predicciones/{cum_id}

Predicción de riesgo de desabastecimiento para el mes siguiente.

**Respuesta 200:**
```json
{
  "cum_id": "20176695-1",
  "probabilidad": 0.34,
  "nivel_riesgo": "Medio",
  "nivel_num": 2,
  "features_principales": {
    "invima_sev_actual": 3.0,
    "num_competidores": 12,
    "monopolio": 0
  },
  "modelo_version": "1.0.0",
  "fecha_prediccion": "2026-07-08"
}
```

**Niveles de riesgo:**

| Nivel | Probabilidad | Descripción |
|-------|-------------|-------------|
| Bajo | < 0.25 | Sin señales de alerta |
| Medio | 0.25 – 0.50 | Señales de monitorización |
| Alto | 0.50 – 0.75 | Riesgo significativo — consulte alternativas |
| Crítico | > 0.75 | Alta probabilidad de desabastecimiento |

---

### GET /invima/estado/{atc}

Estado actual de alerta INVIMA para un código ATC.

**Parámetros de ruta:** `atc` — código ATC (mínimo 5 caracteres)

**Respuesta 200:**
```json
{
  "atc": "M01AE01",
  "estado": "MONITORIZACION",
  "mes": 5,
  "anio": 2026,
  "severidad": 3,
  "laboratorios_afectados": ["GENFAR S.A.", "TECNOQUIMICAS S.A."]
}
```

---

### POST /reportes/no-disponibilidad

Registra un reporte ciudadano de medicamento no disponible.

**Body:**
```json
{
  "cum_id": "20176695-1",
  "tipo_reporte": "sin_stock",
  "descripcion": "No encontré este medicamento en ninguna farmacia del barrio"
}
```

> `tipo_reporte`: `"sin_stock"` (default) | `"precio_alto"` | `"calidad_deficiente"`  
> `descripcion` es opcional.

**Respuesta 201:**
```json
{
  "id": 42,
  "cum_id": "20176695-1",
  "nombre_medicamento": "IBUPROFENO KERN PHARMA",
  "tipo_reporte": "sin_stock",
  "fecha": "2026-07-09T15:30:00",
  "mensaje": "Reporte registrado. Gracias por contribuir a OpenFarma."
}
```

---

### GET /reportes/dashboard

Panel de vigilancia ciudadana: medicamentos con más reportes recientes, spike detector y señales anticipadas.

**Respuesta 200:**
```json
{
  "resumen": {
    "total_reportes_historico": 142,
    "total_reportes_30d": 38,
    "medicamentos_con_spike": 3,
    "senales_anticipadas": 1
  },
  "top_reportados": [
    {
      "cum_id": "20176695-1",
      "nombre_medicamento": "IBUPROFENO KERN PHARMA",
      "total_30d": 12,
      "total_7d": 5,
      "total_1d": 2,
      "spike_ratio": 2.8,
      "tiene_alerta_invima": false,
      "severidad_invima": null,
      "senal_anticipada": true
    }
  ],
  "senales_anticipadas": [{ "...": "mismo objeto" }]
}
```

> **`senal_anticipada`**: `true` cuando el medicamento acumula ≥ 3 reportes en 7 días pero **no** aparece en el reporte INVIMA vigente — indica escasez emergente no detectada aún por el sistema oficial.

---

## Códigos de Error

| Código | Situación |
|--------|----------|
| 400 | Formato de CUM inválido (debe ser `expediente-consecutivo`) |
| 404 | Medicamento no encontrado en el CUM |
| 503 | datos.gov.co no disponible (búsqueda cae en fallback local) |
