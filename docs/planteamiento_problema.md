# Planteamiento del Problema

## Contexto

El desabastecimiento de medicamentos es un problema crítico de salud pública en Colombia. Según el INVIMA, en los últimos 17 meses (enero 2025 – mayo 2026) se han emitido alertas para medicamentos en categorías que van desde antiinfecciosos hasta oncológicos y cardiovasculares.

## Problema Central

**Las alertas de desabastecimiento llegan tarde.** El sistema actual funciona de forma reactiva: el INVIMA emite una alerta de monitorización o desabastecimiento solo cuando el problema ya es visible en la cadena de suministro. Para ese momento:

- Los pacientes en tratamientos crónicos ya han interrumpido su medicación
- Las IPS y EPS no tienen tiempo de gestionar alternativas terapéuticas
- La señal llega fragmentada (PDFs mensuales) y sin cruce con datos del mercado

## Datos que Existen pero No se Cruzan

| Fuente | Dato disponible | Uso actual |
|--------|----------------|------------|
| CUM (datos.gov.co) | 52,000+ medicamentos, titular, estado registro | Manual / consulta individual |
| Alertas INVIMA (PDF) | Historial de 17+ meses de alertas | Difusión mensual reactiva |
| Reportes ciudadanos | No capturados sistemáticamente | Ninguno |

## Pregunta de Investigación

> ¿Es posible predecir con anticipación qué medicamentos tienen mayor probabilidad de desabastecimiento en Colombia, cruzando la estructura del mercado (CUM) con el historial de alertas del INVIMA?

## Hipótesis

Los medicamentos con **historial previo de alertas INVIMA** + **baja competencia de mercado** (monopolio, pocos titulares) + **tendencia de inactivación de registros sanitarios** tienen significativamente mayor probabilidad de desabastecimiento el mes siguiente.

## Impacto Esperado

- **Para pacientes**: acceso anticipado a información de alternativas antes de que su medicamento desaparezca del mercado
- **Para el sistema de salud**: señal temprana que permite a IPS y EPS gestionar sustituciones terapéuticas con tiempo
- **Para reguladores**: canal ciudadano que complementa la vigilancia oficial del INVIMA
