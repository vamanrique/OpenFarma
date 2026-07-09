# Conclusiones, Hallazgos y Próximos Pasos

## Hallazgos Principales

### 1. Es posible predecir el desabastecimiento con anticipación

El modelo alcanzó **ROC-AUC 0.8732** con un split temporal honesto — sin ver el futuro durante el entrenamiento. Esto confirma que las señales en el CUM y en el historial INVIMA contienen información predictiva real, no artefactos de data leakage.

### 2. El historial INVIMA es la señal más poderosa

El **72% de la importancia del modelo** proviene de solo 4 features basadas en el historial INVIMA:
- Severidad el mes anterior (28.3%)
- Peor severidad histórica (21.7%)
- Meses bajo monitorización (12.0%)
- Promedio últimos 3 meses (11.1%)

**Implicación:** Un medicamento que ya estuvo en alerta INVIMA tiene probabilidad significativamente mayor de volver a entrar en problemas. El sistema de alertas del INVIMA es valioso, pero su valor predictivo está subutilizado.

### 3. La estructura de mercado importa menos de lo esperado

Las features de monopolio y número de competidores tienen importancia inferior al historial INVIMA. Sin embargo, son cruciales para medicamentos que **nunca han estado en alerta** — en ese caso, el historial es 0 y la estructura de mercado es la única señal disponible.

### 4. Los datos abiertos son suficientes para el problema

No fue necesario acceso a datos privados de distribución o ventas. El CUM público y los PDFs del INVIMA, integrados correctamente, son suficientes para construir un sistema con métricas útiles en escenario real.

### 5. El sistema es resiliente

La implementación de búsqueda con fallback local garantiza que los ciudadanos siempre reciban resultados, incluso cuando datos.gov.co no está disponible. Los 52,830 medicamentos del CUM normalizado quedan accesibles sin internet.

---

## Limitaciones

| Limitación | Impacto | Mitigación aplicada |
|------------|---------|---------------------|
| Solo 17 meses de historial INVIMA | El modelo puede no capturar ciclos multianuales | Se re-entrena mensualmente al publicar nuevo PDF |
| Clase muy desbalanceada (1.6% positivos) | Avg Precision baja (0.17) | Calibración Platt + uso como sistema de alerta, no oráculo |
| `busquedas_norm` y `reportes_norm` aún con datos escasos | Features con poca señal real hoy | Arquitectura preparada; mejorará con uso |
| ATC del CUM a veces incorrectos | Agrupaciones erróneas | Corrección con LLM (atc_llm) para los casos detectados |
| Falta de datos de ventas/distribución | No captura shocks de demanda | Señal ciudadana como proxy parcial |

---

## Próximos Pasos

### Corto plazo (1 mes)
- [ ] Dashboard privado `/admin/alertas` para visualizar top-20 medicamentos con reportes recientes vs. estado INVIMA
- [ ] Detector de spikes: medicamentos con reportes ciudadanos que no tienen alerta INVIMA activa
- [ ] Automatizar reentrenamiento mensual con GitHub Actions al detectar nuevo PDF INVIMA

### Mediano plazo (3 meses)
- [ ] Monitoreo de drift: comparar distribución de features mes a mes → alerta si el modelo degrada
- [ ] API pública para IPS y EPS: endpoint autenticado con predicciones actualizadas
- [ ] Conectar búsquedas del CUM como señal de demanda (`busquedas_norm`)

### Largo plazo
- [ ] Acuerdo formal con INVIMA para retroalimentar el sistema con datos de cadena de suministro
- [ ] Extensión a dispositivos médicos (CUM de dispositivos, misma fuente datos.gov.co)
- [ ] Modelo de series de tiempo (LSTM/Prophet) para capturar estacionalidad en alertas

---

## Reproducibilidad

Todos los datos fuente son públicos y accesibles sin autenticación:
- CUM: `https://www.datos.gov.co/resource/i7cb-raxc.json`
- PDFs INVIMA: `https://www.invima.gov.co/medicamentos-y-productos-biologicos/`

El pipeline completo (ETL → features → modelo) está documentado en `docs/marco_metodologico.md` y el código en `backend/etl/` y `retrain_invima.py`.
