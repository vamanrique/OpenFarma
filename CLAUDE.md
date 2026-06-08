# FarmaVigia Concurso — CLAUDE.md

## Proyecto

FarmaVigia es una aplicación para el concurso de datos.gov.co Colombia.
Ruta local: `C:\Users\aewal\farmavigia-concurso`
Repositorio: https://github.com/vamanrique/OpenFarma
Deploy: Railway (auto-deploy desde main)

## Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite (`backend/farmavigia.db`)
- **Frontend**: React (directorio `frontend/`)
- **DB en Railway**: `/data/farmavigia.db` (montado como volumen persistente)
- **Python env**: activar con `source .venv/Scripts/activate` o usar directamente desde `backend/`
- **AI**: DeepSeek API para clasificación farmacológica (clave en `backend/.env`)

## Base de datos: grupos_equivalencia

Tabla central del sistema. Estado actual (2026-06-08):

| Métrica | Valor |
|---------|-------|
| Total grupos | 3,701 |
| NULL concentracion_norm | 290 (7.8%) |
| OTRO grupos | 0 |
| Productos en grupos | 50,597 |

### Distribución por grupo_via

| grupo_via | Grupos |
|-----------|--------|
| SOLIDO_ORAL | 1,568 |
| INYECTABLE | 985 |
| LIQUIDO_ORAL | 458 |
| TOPICO | 249 |
| OFTALMICO | 152 |
| INHALADO | 79 |
| SOLIDO_ORAL_LP | 76 |
| VAGINAL | 56 |
| TRANSDERMICO | 22 |
| NASAL | 21 |
| RECTAL | 17 |
| OTICO | 15 |
| SUBLINGUAL | 4 |

### Invariantes del modelo de datos

- **dci_key** = `"||".join(sorted(principios_dci))` ej. `"AMOXICILINA||CLAVULANICO"`
- **grupo_via** = route/form classifier. SOLIDO_ORAL_LP = liberación prolongada (LP/SR/ER/XL/MR/ZOK/RETARD en nombre comercial)
- **concentracion_norm** = string display ej. `"500 mg"`, `"5 mg/mL"`, `"0.05 mg/mL"`, `"SIN_CONCENTRACION"`
- OFTALMICO usa **mg/mL** (no %), TOPICO usa **%**
- Sales equivalentes se agrupan juntas (METOPROLOL TARTRATO = METOPROLOL SUCCINATO) **EXCEPTO** LP vs IR (Betaloc ZOK → SOLIDO_ORAL_LP)
- Unidades especiales: EPO/insulinas en **UI**, no en mg

## Scripts de calidad (ya ejecutados)

| Script | Qué hace |
|--------|----------|
| `backend/construir_grupos.py` | ETL inicial: clasifica ~52K productos con DeepSeek en grupos |
| `backend/fix_grupos_calidad.py` | 7 pasos: OTRO→correct_via, NULL conc recovery, singleton merge, dedup |
| `backend/fix_lp_grupos.py` | Mueve LP products de SOLIDO_ORAL → SOLIDO_ORAL_LP usando LP_RE regex |
| `backend/fix_null_conc2.py` | Segunda pasada: OFTALMICO/NASAL/OTICO via conc_mg_ml, UI regex mejorado |

## API endpoints clave

- `GET /grupos/medicamentos/{cum_id}` — grupos de equivalencia para un producto
- `GET /medicamentos/buscar?q=...` — búsqueda en Socrata API + enriquecimiento local
- `GET /predicciones/{cum_id}` — predicción de desabastecimiento

## Problemas conocidos / deuda técnica

### NULL concentraciones restantes (290 grupos, 7.8%)

La mayoría son legítimos:
- **ORS** (Hidraplus, Electrolit, Pediasol): soluciones multi-componente con composición variable
- **Biológicos**: Zolgensma (vg/mL), Enoxaparina (IU anti-Xa), vacunas complejas
- **Gases médicos**: O2, N2O, CO2
- **Cremas/soluciones combinadas** sin concentración estandarizada en el CUM

### Singletons (aprox. 500 grupos)

Mayoría son productos genuinamente únicos. Los que están "cerca" de otros grupos tienen concentraciones diferentes de verdad (p.ej. Emtricitabina+TAF 245mg vs TDF 300mg = drogas distintas).

### ORAL_DISPERSABLE (0 grupos)

La ETL no genera esta categoría porque los granulados/polvos se clasifican bajo SOLIDO_ORAL. El label está disponible en el sistema pero sin grupos.

### ERITROPOYETINA dci_key inconsistencia

Dos dci_keys distintos para el mismo fármaco: "ERITROPOYETINA HUMANA RECOMBINANTE" y "EPOETIN ALFA". Son la misma molécula pero diferente normalización. Para unificarlos se necesita cambio en ETL.

## Flujo de trabajo Git

```bash
# Siempre trabajar en: C:\Users\aewal\farmavigia-concurso\backend\
cd backend

# Activar contexto Python
python fix_xxx.py --dry-run   # verificar
python fix_xxx.py             # aplicar

# Commit y push (Railway auto-deploya desde main)
cd ..
git add backend/farmavigia.db
git commit -m "fix: descripcion"
git push
```

## Reglas del proyecto

1. **No pedir permisos** — el usuario quiere trabajo autónomo total
2. **Usar DeepSeek** para clasificaciones ambiguas, no solo reglas manuales
3. **Las sales son equivalentes** en el mismo grupo EXCEPTO LP vs IR para Betaloc ZOK (METOPROLOL)
4. **OFTALMICO en mg/mL**, TOPICO en %
5. Los productos **rectal/IM/IV** del mismo fármaco son "complementarios" y válido que estén en grupos separados
6. Antes de cualquier cambio grande → `--dry-run` para verificar
