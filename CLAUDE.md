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

Tabla central del sistema. Estado actual (2026-06-24, tras ronda 81):

| Métrica | Valor |
|---------|-------|
| Total grupos | 3,240 |
| NULL concentracion_norm | **0 (0%)** ✓ |
| SIN_CONCENTRACION | 214 — vacunas, biológicos, gases, sin cuantificar |
| Duplicados (dci+via+conc) | **0** ✓ |
| OTRO grupos | 0 |

**cum_normalizado DCI corrupción (resuelta 2026-06-08):**
- Causa: LLM contaminación de batch → 50,065/52,830 productos asignados con DCIs de fluoroquinolonas (CIPROFLOXACINO, LEVOFLOXACINO, etc.)
- `grupos_equivalencia.dci_key` siempre fue correcto — se usó como fuente de verdad
- **fix_dci_mismatch.py Fase 1**: 48,580 productos corregidos desde grupos
- **fix_dci_mismatch.py Fase 2**: 669 huérfanos INN-nombrados corregidos + 592 asignados a grupo
- Pendiente: ~1,525 huérfanos marca-nombrados (DeepSeek en curso)

### Distribución por grupo_via

| grupo_via | Grupos |
|-----------|--------|
| SOLIDO_ORAL | 1,543 |
| INYECTABLE | 974 |
| LIQUIDO_ORAL | 456 |
| TOPICO | 249 |
| OFTALMICO | 148 |
| INHALADO | 78 |
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
| `backend/fix_dci_normalization.py` | Normaliza dci_key en grupos_equivalencia + principios_dci en cum_normalizado; fusiona duplicados generados |
| `backend/fix_null_conc3.py` | **Tercera pasada (definitiva)**: Fase1 reglas, Fase2 DeepSeek 212 grupos, Fase3 SIN_CONCENTRACION, Fase4 merge. NULL=0 |
| `backend/fix_dci_mismatch.py` | **Corrige DCI contaminados**: Fase1 sincroniza cum_normalizado desde grupos_equivalencia (48,580 fixes), Fase2 huérfanos. |
| `backend/fix_auditoria_conc01..81.py` | **Auditoría INN continua** (rondas 1–81): typos, anglicismos, orden de palabras, merges. Ver sección abajo. |

## Auditoría INN — convenciones aprendidas (rondas 1–81)

### Reglas de nomenclatura establecidas

- **Orden de palabras**: ACIDO siempre primero (ACIDO MALICO no MALICO ACIDO)
- **Género**: ACEITE es masculino → ACEITE DE SOYA REFINADO (no REFINADA)
- **Isótopo radiofármacos**: número+símbolo sin guion, entre paréntesis DESPUÉS del nombre base → MOLIBDATO DE SODIO (99MO), PERTECNETATO DE SODIO (99MTC), YODURO DE SODIO (131I), IOBENGUANO (131I), CITRATO DE GALIO (67GA), CLORURO DE LUTECIO (177LU), TECNECIO (99MTC)
- **Vacunas**: no incluir la palabra VACUNA en el DCI (es forma farmacéutica)
- **Hemaglutinina**: una sola G → HEMAGLUTININA FILAMENTOSA (no HEMAGGLUTININA)
- **Bordetella**: doble S → BORDETELLA PERTUSSIS (no PERTUSIS)
- **Poliovirus**: forma abreviada → POLIOVIRUS INACTIVADO TIPO X (no VIRUS DE POLIO INACTIVADO TIPO X, no VIRUS POLIOMIELITIS TIPO X)
- **INN abreviado sobre nombre científico**: TOXINA BOTULINICA TIPO A; SESTAMIBI (no TETRAFLUOROBORATO/TETRAKIS)
- **Español sobre inglés**: LUMEFANTRINA, SITAGLIPTINA, DONEPEZILO, CEFTAZIDIMA, PERTUSICO
- **SOYA** (no SOJA): término colombiano regional, se mantiene
- **Sin tildes**: DB usa mayúsculas ASCII sin acentos
- **ISPAGHULA** (no ISPAGHULA HUSK): HUSK es descriptor inglés, no parte del INN OMS
- **Hepatitis A canónica**: VIRUS DE LA HEPATITIS A (INACTIVADO)
- **Hepatitis B canónica**: ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B (sin HBSAG, sin PURIFICADO, con "LA")
- **Alfa-1 proteinasa**: INHIBIDOR DE ALFA-1 PROTEINASA (HUMANO) — no ALFA-1 ANTITRIPSINA, no sin "DE", no sin guion
- **PERTECNETATO DE SODIO** (no PERTECNETATO solo; no TECNECIO TC-99M)
- **Technescan DTPA**: TECNECIO (99MTC) PENTETATO (no PERTECNETATO; DTPA=pentetato, no pertecnetato)
- **Vacunas influenza cuadrivalente**: INFLUENZA A H1N1||INFLUENZA A H3N2||INFLUENZA B LINAJE VICTORIA||INFLUENZA B LINAJE YAMAGATA (no cepas anuales específicas)
- **Neumocócica conjugada**: POLISACARIDO DEL SEROTIPO NEUMOCOCICO X + CRM197 (no POLISACARIDO SEROTIPO X, no PROTEINA TRANSPORTADORA CRM 197)
- **Antígenos pertussis**: nombre corto sin prefijo bacteriano — HEMAGLUTININA FILAMENTOSA (no BORDETELLA PERTUSSIS HEMAGLUTININA), PERTACTINA, TOXOIDE PERTUSICO
- **Toxoides difteria/tétanos**: TOXOIDE DIFTERICO / TOXOIDE TETANICO (no CORYNEBACTERIUM DIPHTHERIAE TOXOIDE / CLOSTRIDIUM TETANI TOXOIDE)
- **Hib**: POLISACARIDO CAPSULAR DE HAEMOPHILUS INFLUENZAE TIPO B (no HAEMOPHILUS INFLUENZAE TIPO B POLISACARIDO)
- **Virus vacunales vivos atenuados**: cualificador entre paréntesis DESPUÉS del nombre → VIRUS DE LA FIEBRE AMARILLA (VIVO ATENUADO), VIRUS DEL SARAMPION (VIVO ATENUADO), VIRUS DE LA VARICELA (VIVO ATENUADO), VIRUS DENGUE SEROTIPO X (VIVO ATENUADO)
- **Virus vacunales inactivados**: igual con (INACTIVADO) → VIRUS DE LA HEPATITIS A (INACTIVADO), VIRUS DE LA RABIA (INACTIVADO)
- **MMR**: VIRUS DE LA PAROTIDITIS (no VIRUS PAROTIDITIS, no PAPERA)
- **Twinrix HepA+HepB**: ANTIGENO DE SUPERFICIE DEL VIRUS DE LA HEPATITIS B||VIRUS DE LA HEPATITIS A (INACTIVADO)

### Rondas recientes

| Ronda | Script | Cambio principal |
|-------|--------|--------|
| 71 | fix_auditoria_conc71.py | TECNECIO PERTECNETATO→PENTETATO (DTPA), Prevenar13 POLISACARIDO SEROTIPO→DEL SEROTIPO NEUMOCOCICO + CRM197 |
| 72 | fix_auditoria_conc72.py | Twinrix HepA+HepB canónico, hexavalente Hexaxim antígenos, DTP+IPV id=3107 POLIOVIRUS INACTIVADO |
| 73 | fix_auditoria_conc73.py | Adacel DTPa5 y pentavalente: drop prefijos BP/CT/CD, fix Hib, toxoides canónicos |
| 74 | fix_auditoria_conc74.py | MMR PAROTIDITIS (no PAPERA), ProQuad PAPERA→PAROTIDITIS, DTwP toxoides canónicos |
| 75 | fix_auditoria_conc75.py | Influenza cepas anuales→subtipos canónicos (merge 3611→3610), VIRUS DE LA RABIA (INACTIVADO) |
| 76 | fix_auditoria_conc76.py | VIVO ATENUADO con paréntesis (MMR, varicela), VIRUS DE LA VARICELA con artículo |
| 77 | fix_auditoria_conc77.py | Dengvaxia VIRUS DENGUE SEROTIPO X (VIVO ATENUADO) |
| 78 | fix_auditoria_conc78.py | ProQuad CEPA con paréntesis: CEPA JERYL LYNN → (CEPA JERYL LYNN), etc. |
| 79 | fix_auditoria_conc79.py | Gardasil 9 L1VPH→L1 VPH TIPO (uniform HPV naming), Infanrix Hexa HBsAg sin RECOMBINANTE |
| 80 | fix_auditoria_conc80.py | Typhim Vi polisacárido-primero: SALMONELLA TYPHI POLISACARIDO VI→POLISACARIDO VI DE SALMONELLA TYPHI; Pneumovax 23 forma adjetival POLISACARIDOS NEUMOCOCICOS |
| 81 | fix_auditoria_conc81.py | Arexvy RSV GLUCOPROTEINA F drop RECOMBINANTE (proceso de producción, no parte del INN) |

### Convenciones adicionales (rondas 78-81)

- **CEPA entre paréntesis**: designaciones de cepa vacunal siempre entre paréntesis → `(CEPA JERYL LYNN)`, `(CEPA OKA/MERCK)`, `(CEPA WISTAR RA 27/3)`, `(CEPA EDMONSTON B)`, `(CEPA RIX4414)`
- **VPH nomenclatura**: `PROTEINA L1 VPH TIPO X` (con espacio entre L1 y VPH, y con TIPO antes del número)
- **RECOMBINANTE**: NO incluir en INN cuando toda la clase es recombinante (HBsAg vacunal, glucoproteína F RSV). SÍ incluir cuando distingue de versión plasmática (Factor VIII, Factor IX, eritropoyetinas)
- **Polisacárido primero**: componente activo antes del organismo — `POLISACARIDO VI DE SALMONELLA TYPHI` (no SALMONELLA TYPHI POLISACARIDO VI)
- **Forma adjetival para bacterias comunes**: POLISACARIDOS NEUMOCOCICOS (no STREPTOCOCCUS PNEUMONIAE), POLISACARIDO MENINGOCOCICO (no NEISSERIA MENINGITIDIS)

### Pendiente identificado

- `id=3623` (Technescan MAG3): `BETIATIDA` — verificar si es sinónimo de MERTIATIDA (INN OMS); concentraciones distintas (SIN_CONC vs 0.2mg) → no merge aunque sean iguales
- ROTARIX `ROTAVIRUS HUMANO VIVO ATENUADO (CEPA RIX4414)` — VIVO ATENUADO sin parens (aceptable por complejidad dual-parens; nombre establacido)

## API endpoints clave

- `GET /grupos/medicamentos/{cum_id}` — grupos de equivalencia para un producto
- `GET /medicamentos/buscar?q=...` — búsqueda en Socrata API + enriquecimiento local
- `GET /predicciones/{cum_id}` — predicción de desabastecimiento

## Normalización de principios activos (DCI)

### Estado: 100% normalizado (2026-06-08)

**`_SINONIMOS`** en `etl/transformacion.py`: ~420 entradas cubriendo:
- Variantes inglés→español (-ine/-ina, -ol/-ole, etc.)
- Fluoroquinolonas: siempre terminan en **-INO** (CIPROFLOXACINO, LEVOFLOXACINO, etc.)
- Nombres colombianos: ACETAMINOFEN→PARACETAMOL, DIPIRONA→METAMIZOL, ALBUTEROL→SALBUTAMOL
- Eritropoyetinas: EPOETIN ALFA→EPOETINA ALFA, orden canónico ERITROPOYETINA HUMANA RECOMBINANTE

**`_SUFIJOS_SAL`** en `etl/transformacion.py`: ~50 formas de sal eliminadas (CLORHIDRATO, SULFATO, SODICO, LISINA, etc.)

**Advertencia**: `_SUFIJOS_SAL` elimina SULFATO, CITRATO, LACTATO, GLUCONATO — NO aplicar `normalizar_principio()` a DCIs donde la sal ES el INN (CONDROITINA SULFATO, LACTATO DE SODIO, GLUCONATO DE ZINC, etc.). Estos están correctos en la DB tal como están.

## Problemas conocidos / deuda técnica

### SIN_CONCENTRACION (214 grupos, 6.6%)

Productos donde la concentración no aplica o no tiene una presentación estandarizada:
- **Vacunas y biológicos complejos**: MMR, Hepatitis A/B, Dengue, BCG, factores de coagulación, inmunoglobulinas
- **Terapias génicas/celulares**: Zolgensma, Luxturna, etc.
- **Anticoagulantes de múltiples dosis**: Heparina (5000/25000 UI/mL), Enoxaparina (IU anti-Xa)
- **Gases médicos**: O2, N2O, CO2, Helio, Nitrógeno
- **Productos sin fórmula estándar**: Agua inyectable, soluciones electrolíticas complejas, radiofármacos

El valor `SIN_CONCENTRACION` no afecta alternativas A4–A7 (basadas en ATC). Solo excluye A0–A3 (basadas en concentración exacta). El frontend lo omite del display.

### Singletons (502 grupos)

Mayoría son productos genuinamente únicos. Los que están "cerca" de otros grupos tienen concentraciones diferentes de verdad (p.ej. Emtricitabina+TAF 245mg vs TDF 300mg = drogas distintas).

### ORAL_DISPERSABLE (0 grupos)

La ETL no genera esta categoría porque los granulados/polvos se clasifican bajo SOLIDO_ORAL. El label está disponible en el sistema pero sin grupos.

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
