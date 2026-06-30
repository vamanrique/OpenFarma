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

Tabla central del sistema. Estado actual (2026-06-30, tras ronda 104):

| Métrica | Valor |
|---------|-------|
| Total grupos | 3,204 |
| NULL concentracion_norm | **0 (0%)** ✓ |
| SIN_CONCENTRACION | 213 — vacunas, biológicos, gases, sin cuantificar |
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
| `backend/fix_auditoria_conc01..104.py` | **Auditoría INN continua** (rondas 1–104): typos, anglicismos, orden de palabras, merges. Ver sección abajo. |
| `backend/fix_english_dci.py` | ZINC OXIDE→OXIDO DE ZINC, SODIUM IODIDE I-131→YODURO DE SODIO (131I), ZINC ACETATE→ACETATO DE ZINC. |
| `backend/fix_salt_names.py` | Orden incorrecto sal+catión: CALCIO GLUCONATO→GLUCONATO DE CALCIO, BARIO SULFATO→SULFATO DE BARIO, etc. |
| `backend/fix_vitamins_units.py` | Vitamina A mal clasificada como ACIDO ASCORBICO; TOCOFEROL 400/800 mg → 400/800 UI. |
| `backend/fix_zero_mg_conc.py` | Sub-mg parseados como 0: LEVOTIROXINA mcg, CALCITRIOL, PARICALCITOL, FLUTICASONA NASAL, etc. |
| `backend/fix_remaining_groups.py` | Grupos misceláneos con DCI erróneo o SIN_CONC incorrecto (batch ETL tardío). |
| `backend/fix_sinconc_batch2.py` | Segunda ronda de SIN_CONC → concentración real (ENOXAPARINA, CLINDAMICINA||CLOTRIMAZOL, etc.). |
| `backend/fix_batch_contamination.py` | Grupos ids ~3789-3912 con DCI de nombre comercial → INN correcto + merge. |

## Auditoría INN — convenciones aprendidas (rondas 1–104)

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
| 82 | fix_auditoria_conc82.py | Penicilinas INN canónicas: PENICILINA G→BENCILPENICILINA, G BENZATINICA→BENCILPENICILINA BENZATINA, G PROCAINA→BENCILPENICILINA PROCAINA, PENICILINA V→FENOXIMETILPENICILINA |
| 83 | fix_auditoria_conc83.py | Radiofármacos generadores Mo/Tc: CLORURO DE SODIO\|\|TECNECIO→MOLIBDATO DE SODIO (99MO)\|\|PERTECNETATO DE SODIO (99MTC); LUTECIO (177LU)→CLORURO DE LUTECIO (177LU) |
| 84 | fix_auditoria_conc84.py | Factores coagulación recombinantes INN: RURIOCTOCOG ALFA PEGOL (Adynovate), OCTOCOG ALFA (Kovaltry), NONACOG GAMMA (Rixubis); fix conc 800→800000 UI BENCILPENICILINA PROCAINA |
| 85 | fix_auditoria_conc85.py | FOLITROPINA→FOLITROPINA ALFA (Bemfola); EPTACOG ALFA→EPTACOG ALFA (ACTIVADO) (NovoSeven) |
| 86 | fix_auditoria_conc86.py | Fix conc parseo: DESMOPRESINA 0.1→0.12 mg (Minirin Melt 120μg); VALACICLOVIR 1→1000 mg (Valtrois); merge→1422 |
| 87 | fix_auditoria_conc87.py | Terapias génicas: VORETIGEN→VORETIGENE NEPARVOVEC (Luxturna); ONASEMNOGEN→ONASEMNOGENE ABEPARVOVEC (Zolgensma); ANTITIMOCITOS HUMANA→(CONEJO) (Timoglobulina) |
| 88 | fix_auditoria_conc88.py | ACIDO METILENDIFOSFONICO→ACIDO MEDRONICO (Rotop-MDP); TENOFOVIR→TENOFOVIR DISOPROXILO (6 grupos TDF: Truvada, Stribild, Atripla, Delstrigo, Didivir, Tendifu); merge 1306+1683 |
| 89 | fix_auditoria_conc89.py | BETIATIDA→MERTIATIDA (Technescan MAG3); ALBUMINA HUMANA→ALBUMINA SERICA HUMANA NANOCOLOIDE (Nano-Albumon); Survanta 2878/2879→BERACTANT |
| 90 | fix_auditoria_conc90.py | BLES 3554 (FOSFOLIPIDOS/LIQUIDO_ORAL)→BERACTANT/INYECTABLE; Blesurf 3600→BERACTANT; merges→3554/3600 |
| 91 | fix_auditoria_conc91.py | Survanta 4mL (684 FOSFOLIPIDOS TOTALES)→BERACTANT; Infasurf (1088 FOSFOLIPIDOS)→CALFACTANT; merge 684→3554 |
| 92 | fix_auditoria_conc92.py | AmBisome→ANFOTERICINA B LIPOSOMAL; hierro IV: CARBOXIMALTOSA FERRICA (Ferinject), HIERRO SACAROSA (merge→1500), DERISOMALTOSA FERRICA (Monofer); PROTEINSUCCINILATO FERRICO (Ferroprotina) |
| 93 | fix_auditoria_conc93.py | HIERRO→SULFATO FERROSO (id=683), GLUCONATO FERROSO (ids 2753/2754); DOXORUBICINA LIPOSOMAL PEGILADA split de id=1045 (Doxopeg, Lipodox, Doxorubicina LD); HIERRO SACAROSA merge 2333+2463 |
| 94 | fix_auditoria_conc94.py | Split id=2755 (SULFATO FERROSO 7 prod + GLUCONATO FERROSO 5 prod a 25mg/mL); HIERRO→FUMARATO FERROSO (Ferrokids); HIERRO→CITRATO FERRICO AMONICO (Herrex, Eurofer) |
| 95 | fix_auditoria_conc95.py | CASPOFUNGINA 100x factor fix (0.7mg→70mg, 0.5mg→50mg); HepB antígeno singletons mg→SIN_CONC→merge id=3513; OCTREOTIDA id=2395→EDOTREOTIDA (Tektrotyd Ga-68) |
| 96 | fix_auditoria_conc96.py | HEPARINA '25 UI' (=25.000, mal parseo separador miles)→SIN_CONC; CLONIXINATO/CLONIXINATO DE LISINA→CLONIXINA en 5 grupos; merges CICLOBENZAPRINA combos |
| 97 | fix_auditoria_conc97.py | GUAIACOLATO DE GLICERILO→GUAIFENESINA (8 grupos, merges); N-ACETILCISTEINA→ACETILCISTEINA (INN OMS sin prefijo N-) |
| 98 | fix_auditoria_conc98.py | ISOSORBIDA DINITRATO→DINITRATO DE ISOSORBIDA (INN-Sp #4749); ISOPROPANOL/PROPAN-2-OL→ALCOHOL ISOPROPILICO (merge CLORHEXIDINA combos) |
| 99 | fix_auditoria_conc99.py | SESTAMIBI→TECNECIO (99MTC) SESTAMIBI; ACIDO PENTETICO→TECNECIO (99MTC) PENTETATO (DTPA renal); ACIDO DIMERCAPTOSUCCINICO→TECNECIO (99MTC) SUCCIMERO (DMSA renal/óseo) |
| 100 | fix_auditoria_conc100.py | HIDROXICOBALAMINA→HIDROXOCOBALAMINA; FOLINATO DE CALCIO→ACIDO FOLINICO; OXIDRONATO DE SODIO→TECNECIO (99MTC) OXIDRONATO (HDP bone scan); GADOBENATO DE DIMEGLUMINA→ACIDO GADOBENICO; MACROAGREGADOS DE ALBUMINA→TECNECIO (99MTC) MACROSALB |
| 101 | fix_auditoria_conc101.py | GBq parseados como 'g' (generadores Mo/Lu)→SIN_CONC+merge; MERTIATIDA→TECNECIO (99MTC) MERTIATIDA; EDOTREOTIDA→GALIO (68GA) EDOTREOTIDA |
| 102 | fix_auditoria_conc102.py | RADIO RA-223→DICLORURO DE RADIO (223RA) (INN #9982); YODO iny 480mg/mL→ACEITE DE ADORMIDERA YODADO (Lipiodol); DEXTRAN 70→DEXTRANO 70 (INN-Sp); HIERRO SACAROSA 100mg→20mg/mL→merge id=1500 |
| 103 | fix_auditoria_conc103.py | Completar V09 con prefijo Tc: EXAMETAZIMA→TECNECIO (99MTC) EXAMETAZIMA; ACIDO MEDRONICO→MEDRONATO; MEBROFENINA (3 grupos); TETRAFOSMINA→TETROFOSMINA (typo+prefijo); PIROFOSFATO DE SODIO→TECNECIO (99MTC) PIROFOSFATO |
| 104 | fix_auditoria_conc104.py | IOPRAMIDA (typo Ultravist 300)→IOPROMIDA; ALBUMINA SERICA HUMANA NANOCOLOIDE (V09DB01+V09GA04)→TECNECIO (99MTC) ALBUMINA SERICA HUMANA NANOCOLOIDE |

### Convenciones adicionales (rondas 78-104)

- **CEPA entre paréntesis**: designaciones de cepa vacunal siempre entre paréntesis → `(CEPA JERYL LYNN)`, `(CEPA OKA/MERCK)`, `(CEPA WISTAR RA 27/3)`, `(CEPA EDMONSTON B)`, `(CEPA RIX4414)`
- **VPH nomenclatura**: `PROTEINA L1 VPH TIPO X` (con espacio entre L1 y VPH, y con TIPO antes del número)
- **RECOMBINANTE**: NO incluir en INN cuando toda la clase es recombinante (HBsAg vacunal, glucoproteína F RSV). SÍ incluir cuando distingue de versión plasmática (eritropoyetinas)
- **Factores coagulación recombinantes**: usar INN específico OMS — OCTOCOG ALFA (rFVIII Advate/Kovaltry), MOROCTOCOG ALFA (ReFacto), TUROCTOCOG ALFA, SIMOCTOCOG ALFA, RURIOCTOCOG ALFA PEGOL (Adynovate pegilado), NONACOG ALFA (BeneFIX), NONACOG GAMMA (Rixubis). Plasma-derived permanecen como FACTOR VIII / FACTOR IX (sin INN único).
- **Penicilinas INN canónicas**: BENCILPENICILINA (G sódica/potásica), BENCILPENICILINA BENZATINA, BENCILPENICILINA PROCAINA, FENOXIMETILPENICILINA (Penicilina V oral)
- **Polisacárido primero**: componente activo antes del organismo — `POLISACARIDO VI DE SALMONELLA TYPHI` (no SALMONELLA TYPHI POLISACARIDO VI)
- **Forma adjetival para bacterias comunes**: POLISACARIDOS NEUMOCOCICOS (no STREPTOCOCCUS PNEUMONIAE), POLISACARIDO MENINGOCOCICO (no NEISSERIA MENINGITIDIS)
- **Terapias génicas vocal final -E**: VORETIGENE NEPARVOVEC (no VORETIGEN), ONASEMNOGENE ABEPARVOVEC (no ONASEMNOGEN). INN OMS con -gene en inglés → -gene/-geno en español (vocal final)
- **ATG especie**: INMUNOGLOBULINA ANTITIMOCITOS (CONEJO) para Thymoglobulin/Timoglobulina (rabbit); si fuera equina/humana se especifica entre paréntesis
- **Radiofármacos nombre sistemático → INN**: ACIDO METILENDIFOSFONICO (MDP) → ACIDO MEDRONICO; usar nombre INN OMS siempre que exista. OXIDRONATO DE SODIO (HDP) ya correcto.
- **TENOFOVIR oral 300mg = TDF prodrug**: el INN del compuesto aprobado VO es TENOFOVIR DISOPROXILO; TENOFOVIR (ácido libre) solo aplica si hubiera formulación IV de ácido libre
- **Surfactantes pulmonares**: BERACTANT (Survanta, BLES, Blesurf = bovino adulto), CALFACTANT (Infasurf = ternera), PORACTANT ALFA (Curosurf = porcino). Todos SIN_CONCENTRACION. FOSFOLIPIDOS/FOSFOLIPIDOS TOTALES son nombres composicionales, no INN.
- **Anfotericina B formulaciones**: ANFOTERICINA B (convencional/Fungizone) ≠ ANFOTERICINA B LIPOSOMAL (AmBisome/Amphosom-B/Limperic B). Son INN distintos (OMS #7372) con dosificación e indicaciones diferentes.
- **Preparaciones de hierro IV — INN específicos**: HIERRO SACAROSA (sucrose complex/Venofer), CARBOXIMALTOSA FERRICA (ferric carboxymaltose/Ferinject), DERISOMALTOSA FERRICA (ferric derisomaltose/Monofer, INN OMS 2020). HIERRO dextrano pendiente verificación.
- **Hierro oral especializado**: PROTEINSUCCINILATO FERRICO (ferric proteinsuccinylate/Ferroprotina, ATC B03AB99).
- **Hierro sales orales**: SULFATO FERROSO (B03AA07), GLUCONATO FERROSO (B03AA01), FUMARATO FERROSO (B03AB02), CITRATO FERRICO AMONICO (B03AB04). Nombre genérico HIERRO solo si ATC no identifica la sal.
- **DOXORUBICINA LIPOSOMAL PEGILADA** ≠ DOXORUBICINA convencional (grupos separados). Split id=1045 realizado en ronda 93.
- **GUAIFENESINA** (INN OMS #3774): no "guaiacolato de glicerilo" ni "gliceril guayacolato".
- **ACETILCISTEINA** (INN OMS #72): sin prefijo N- (N-ACETILCISTEINA es redundante).
- **DINITRATO DE ISOSORBIDA** (INN-Sp #4749): no "ISOSORBIDA DINITRATO".
- **CLONIXINA** (INN base): no CLONIXINATO DE LISINA, no CLONIXINATO.
- **Radiofármacos Tc-99m — nombre completo**: TECNECIO (99MTC) SESTAMIBI (Cardiolite), TECNECIO (99MTC) PENTETATO (DTPA renal), TECNECIO (99MTC) SUCCIMERO (DMSA renal/óseo), TECNECIO (99MTC) MERTIATIDA (MAG3 renal tubular), TECNECIO (99MTC) OXIDRONATO (HDP bone scan), TECNECIO (99MTC) MACROSALB (MAA pulmón), TECNECIO (99MTC) EXAMETAZIMA (HMPAO brain/Ceretec), TECNECIO (99MTC) MEDRONATO (MDP bone scan), TECNECIO (99MTC) MEBROFENINA (Choletec hepatobiliary), TECNECIO (99MTC) TETROFOSMINA (Myoview cardiac), TECNECIO (99MTC) PIROFOSFATO (PYP bone/cardiac), TECNECIO (99MTC) ALBUMINA SERICA HUMANA NANOCOLOIDE (Nano-Albumon/Rotop NanoHSA). Todos los kits V09 siguen esta convención: INN del radiofármaco final, no del ligando/sal precursor.
- **IOPROMIDA** (no IOPRAMIDA): INN OMS para iopromide (Ultravist, Bayer). Forma correcta en -a.
- **Radiofármacos Ga-68**: GALIO (68GA) EDOTREOTIDA (Tektrotyd DOTATOC PET).
- **DICLORURO DE RADIO (223RA)** (INN #9982, Xofigo): sigue convención isotopo-entre-paréntesis.
- **ACEITE DE ADORMIDERA YODADO** (Lipiodol 480mgI/mL): no "YODO" (que es antiséptico elemental).
- **DEXTRANO** (no DEXTRAN): INN-Sp español. Número de peso molecular es parte del INN (DEXTRANO 70).
- **HIDROXOCOBALAMINA** (no HIDROXICOBALAMINA): "hidroxo" del ligando en química de coordinación.
- **ACIDO FOLINICO** (no FOLINATO DE CALCIO): convención sal→ácido libre INN, igual que ACIDO FOLICO.
- **ACIDO GADOBENICO** (INN #9232, no GADOBENATO DE DIMEGLUMINA): igual que ACIDO GADOTERICO y ACIDO GADOXETICO.
- **GBq → SIN_CONCENTRACION**: actividad en gigabecquerel no es concentración molar — generadores Mo/Lu y similares usan SIN_CONCENTRACION.

### Pendiente identificado

- ROTARIX `ROTAVIRUS HUMANO VIVO ATENUADO (CEPA RIX4414)` — VIVO ATENUADO sin paréntesis externos (aceptable por complejidad dual-parens; nombre establecido)
- HIERRO dextrano (ATC B03AC): verificar INN específico (HIERRO DEXTRANO vs dextriferron vs ferumoxytol) para grupos con ATC B03AC que no sean hierro sacarosa/carboximaltosa/derisomaltosa

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
