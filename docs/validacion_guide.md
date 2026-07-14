# Guía de Validación — Para Pares Evaluadores

Esta guía permite a cualquier evaluador verificar de forma independiente los resultados reportados por OpenFarma.

---

## Validación 1 — Búsqueda de Medicamentos (CUM en tiempo real)

### Qué verificar
Que la búsqueda en OpenFarma retorna los mismos medicamentos que la fuente oficial.

### Pasos

1. Ir a [OpenFarma](https://openfarma-production.up.railway.app) y buscar "ibuprofeno"
2. Verificar en la fuente oficial: [https://www.datos.gov.co/resource/i7cb-raxc.json?$where=upper(producto)%20like%20'%25IBUPROFENO%25'&$limit=5](https://www.datos.gov.co/resource/i7cb-raxc.json?$where=upper(producto)%20like%20'%25IBUPROFENO%25'&$limit=5)
3. Comparar: los nombres comerciales, principios activos, titulares y estados deben coincidir con los datos oficiales

**Resultado esperado:** OpenFarma mostrará un subconjunto deduplicado de los resultados del CUM (agrupa presentaciones del mismo principio activo + forma + concentración).

---

## Validación 2 — Alertas INVIMA

### Qué verificar
Que el estado INVIMA mostrado en OpenFarma coincide con el último comunicado oficial.

### Pasos

1. Ir al [portal INVIMA](https://www.invima.gov.co/medicamentos-y-productos-biologicos/) y descargar el comunicado más reciente (sección "Situación de Disponibilidad de Medicamentos")
2. Buscar un medicamento que aparezca en ese comunicado en OpenFarma
3. Verificar que el estado (Monitorización / No desabastecimiento) coincide

**Limitación conocida:** La base de datos de OpenFarma se actualiza cuando el script `actualizar_invima.py` se ejecuta (proceso manual o por cron los viernes). Puede haber hasta 7 días de diferencia con el comunicado más reciente.

---

## Validación 3 — Modelo Predictivo

### Qué verificar
Que el ROC-AUC reportado (0.8732) es reproducible.

### Pasos

```bash
# Clonar el repositorio
git clone https://github.com/vamanrique/OpenFarma
cd OpenFarma

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar reentrenamiento con métricas de evaluación
cd backend
python retrain_invima.py --db openfarma.db --eval-only
```

**Salida esperada:**
```
[EVAL] ROC-AUC (temporal split): 0.8732
[EVAL] Avg Precision: 0.1720
[EVAL] Test set: mar-may 2026 (3 meses), 1.6% positivos
```

**Nota:** Los resultados pueden variar ligeramente si el INVIMA publicó nuevos PDFs desde que se generaron los resultados reportados. El script usa el historial disponible en `openfarma.db`.

---

## Validación 4 — Grupos de Equivalencia

### Qué verificar
Que la agrupación de alternativas terapéuticas es clínicamente coherente.

### Pasos

1. Buscar "metformina" en OpenFarma
2. Seleccionar un producto y verificar las alternativas (A0-A3: mismo grupo; A4-A7: misma clase ATC)
3. Verificar en la base de datos del CUM que los productos del mismo grupo tienen el mismo principio activo, forma y concentración

**Verificación SQL directa** (requiere `sqlite3`):
```sql
-- Conectar a openfarma.db
SELECT dci_key, grupo_via, concentracion_norm, COUNT(json_array_length(cum_ids)) as productos
FROM grupos_equivalencia
WHERE dci_key LIKE '%METFORMINA%'
GROUP BY dci_key, grupo_via, concentracion_norm;
```

---

## Contacto

Para preguntas sobre la validación: vamanrique@gmail.com
