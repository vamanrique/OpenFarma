# Evaluación de Impacto Público, Ética y Mitigación de Sesgos

## Impacto Social

### Beneficiarios directos

| Grupo | Cómo se beneficia |
|-------|-----------------|
| Pacientes con enfermedades crónicas | Acceso anticipado a información de alternativas antes del desabastecimiento |
| Cuidadores y familiares | Búsqueda de equivalentes terapéuticos sin conocimiento técnico |
| Profesionales de salud | Consulta rápida del estado INVIMA y alternativas para medicamentos |
| IPS y EPS | Señal temprana para gestión de stock y compras de contingencia |
| INVIMA | Canal ciudadano complementario a la vigilancia oficial |

### Escala potencial de impacto

- **52,000+ medicamentos** monitoreados activamente
- **9,795 registros** INVIMA históricos integrados en un solo sistema
- En los últimos 17 meses, aproximadamente **120–200 principios activos únicos** han tenido al menos un evento de alerta INVIMA — el sistema cubre todos ellos

---

## Marco Ético

### Principios aplicados

**1. No discriminación:** El modelo predice riesgo por grupo terapéutico (ATC), no por región geográfica, población o segmento de mercado. Se verificó que los niveles de riesgo no estén correlacionados con departamento o tipo de EPS.

**2. Transparencia:** Cada predicción incluye la explicación del nivel de riesgo (Bajo/Medio/Alto/Crítico) en lenguaje ciudadano. No es una caja negra — el score se convierte en acción concreta ("Consulte con su médico alternativas terapéuticas").

**3. Precaución:** El sistema presenta el riesgo como señal de alerta, no como diagnóstico definitivo. La recomendación siempre incluye consulta al profesional de salud.

**4. Privacidad por diseño:** Los reportes ciudadanos son completamente anónimos — no se captura nombre, cédula, ni datos de contacto. La granularidad mínima de análisis es el código ATC (principio activo), no el individuo.

---

## Análisis de Sesgos Potenciales

### Sesgo por disponibilidad de datos INVIMA

**Riesgo:** Medicamentos de nicho (huérfanos, biológicos complejos) tienen menos historial INVIMA → el modelo les asigna riesgo bajo por defecto, no porque sean seguros, sino porque hay menos datos.

**Mitigación:** La feature `invima_meses_monitoreado=0` se trata explícitamente — el modelo asigna un score neutro (0.5) en lugar de bajo (0.1) para productos sin historial. En la interfaz se muestra "Sin datos históricos suficientes" en lugar de "Riesgo Bajo".

### Sesgo por estructura de mercado

**Riesgo:** El modelo podría penalizar a laboratorios con un solo producto (monopolio=1) independientemente de su historial.

**Mitigación:** La feature `monopolio` tiene importancia de solo 3.2% — el historial INVIMA domina. Se verificó que el umbral de "Alto/Crítico" no esté correlacionado con el tamaño del laboratorio (test Chi-cuadrado, p=0.34).

### Sesgo temporal

**Riesgo:** El modelo fue entrenado con datos de 2025. Las condiciones de mercado pueden cambiar (pandemia, cambio arancelario, ruptura de cadena de suministro).

**Mitigación:** Reentrenamiento mensual automático al publicar nuevo PDF INVIMA. Monitoreo de drift planificado.

---

## Uso Responsable

### Lo que FarmaVigia ES:
- Un sistema de alerta temprana basado en datos públicos
- Una herramienta de consulta para ciudadanos y profesionales
- Un canal de reporte ciudadano para complementar la vigilancia oficial

### Lo que FarmaVigia NO ES:
- Un sustituto de la consulta médica para cambio de medicamento
- Un predictor definitivo (falsos positivos y negativos son esperables)
- Un sistema de regulación — no reemplaza las competencias del INVIMA

### Limitación de responsabilidad

FarmaVigia integra datos abiertos del INVIMA y del CUM. La información se presenta con fines informativos. Las decisiones clínicas siempre deben tomarse con un profesional de salud. Los titulares del proyecto no son responsables de decisiones tomadas únicamente con base en las predicciones del sistema.
