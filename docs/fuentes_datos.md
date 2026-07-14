# Fuentes de Datos

## 1. Catálogo Único de Medicamentos (CUM) — Activos

| Campo | Valor |
|-------|-------|
| **Nombre** | Catálogo de Medicamentos con Registro Sanitario Activo |
| **Entidad** | INVIMA — Instituto Nacional de Vigilancia de Medicamentos y Alimentos |
| **Portal** | datos.gov.co |
| **Dataset ID** | `i7cb-raxc` |
| **Endpoint** | `https://www.datos.gov.co/resource/i7cb-raxc.json` |
| **Formato** | JSON via Socrata SODA API |
| **Registros** | ~52,000 presentaciones activas |
| **Actualización** | Continua (tiempo real) |
| **Fecha de acceso** | Snapshot ETL: julio 2026; búsquedas en tiempo real vía Socrata |
| **Licencia** | Datos Abiertos Colombia (Ley 1712 de 2014) |

**Campos utilizados:** `expedientecum`, `consecutivocum`, `producto`, `principioactivo`, `estadocum`, `atc`, `forma`, `via`, `concentracion`, `titular`, `registro`

---

## 2. CUM — Registros en Trámite de Renovación

| Campo | Valor |
|-------|-------|
| **Nombre** | Medicamentos con Registro Sanitario en Trámite de Renovación |
| **Entidad** | INVIMA |
| **Dataset ID** | `vgr4-gemg` |
| **Endpoint** | `https://www.datos.gov.co/resource/vgr4-gemg.json` |
| **Registros** | ~8,000 |
| **Fecha de acceso** | Snapshot ETL: julio 2026; consulta en tiempo real en producción |
| **Licencia** | Datos Abiertos Colombia |
| **Uso** | Complementa búsqueda: productos cuyo registro venció pero están en renovación |

---

## 3. Alertas INVIMA — PDFs Mensuales

| Campo | Valor |
|-------|-------|
| **Nombre** | Comunicados de Situación de Disponibilidad de Medicamentos |
| **Entidad** | INVIMA |
| **Portal** | [invima.gov.co/medicamentos-y-productos-biologicos/](https://www.invima.gov.co/medicamentos-y-productos-biologicos/) |
| **Formato** | PDF (descarga directa) |
| **Cobertura** | Enero 2025 – Mayo 2026 (17 meses, 9,795 entradas) |
| **Frecuencia** | Mensual (publicación aproximada los viernes) |
| **Fecha de acceso** | Enero 2025 – Mayo 2026 (procesados al momento del entrenamiento) |
| **Licencia** | Información pública (INVIMA) |

**Categorías en los PDFs:**
- `MONITORIZACION`: medicamento con señal de riesgo, bajo vigilancia activa
- `NO_DESABASTECIMIENTO`: confirmado disponible luego de monitorización
- `NO_COMERCIALIZADO`: retirado del mercado (no es desabastecimiento, es decisión comercial)

**Pipeline de ingesta:** `etl/invima_scraper.py` → `etl/invima_parser.py` → tabla `invima_seguimiento` (SQLite)

---

## 4. Reportes Ciudadanos — OpenFarma

| Campo | Valor |
|-------|-------|
| **Nombre** | Reportes de No Disponibilidad |
| **Origen** | Formulario propio en OpenFarma |
| **Tabla** | `reportes_no_disponibilidad` (SQLite) |
| **Campos capturados** | `cum_id`, `fecha_reporte`, `descripcion` |
| **Uso en modelo** | Feature `reportes_norm`: conteo de reportes recientes normalizado |

*Nota: Dataset en crecimiento — aún con baja cobertura. Se pondera con factor de confianza bajo hasta alcanzar masa crítica.*

---

## Política de Datos

- Los datos del CUM e INVIMA son de acceso libre y uso irrestricto (Ley 1712 de 2014 — Transparencia y Acceso a la Información)
- No se almacenan datos personales de ciudadanos; los reportes son anónimos
- El NITs de empresas titulares son datos públicos del registro mercantil (no se anonomizan)
- El modelo ML opera sobre datos agregados por ATC; no genera perfiles individuales
