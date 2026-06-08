"""
Transformaciones del CUM: normalización de principios activos,
detección de conjugaciones, construcción de concentración real.

La fuente es siempre el JSON online — este módulo solo transforma,
no lee ni escribe archivos.
"""
import re
import pandas as pd
from dataclasses import dataclass, field

# Sufijos de sal/éster/forma a eliminar para obtener la DCI (nombre genérico)
_SUFIJOS_SAL = re.compile(
    r"\b(TRIHIDRATO|MONOHIDRATO|DIHIDRATO|ANHIDRO|HEMIHIDRATO|"
    r"SODICO|SODICA|POTASICO|POTASICA|CALCICO|CALCICA|MAGNESICO|"
    r"CLORHIDRATO|DICLORHIDRATO|HIDROCLORURO|BROMHIDRATO|"
    r"FOSFATO|BISFOSFATO|SULFATO|BISULFATO|TARTRATO|BITARTRATO|"
    r"MALEATO|FUMARATO|SUCCINATO|GLUCONATO|ACETATO|PROPIONATO|"
    r"MESILATO|TOSILATO|BESILATO|ACESULATO|ADIPATO|ESTEARATO|"
    r"LACTATO|CITRATO|MALATO|OXALATO|VALERATO|BUTIRATO|"
    r"DIPROPIONATO|FUROATO|PROPIONATO|HEXANOATO|DECANOATO|"
    r"PALMITATO|ESTEARATO|BENZOATO|SALICILATO|"
    r"TRIHIDRATADA?|DIHIDRATADA?|MONOHIDRATADA?|BASE)\b",
    re.IGNORECASE,
)

# Extrae el primer valor numérico de un string de concentración ("25 mg" → 25.0)
_NUM_DOSIS = re.compile(r'(\d+(?:[.,]\d+)?)')

# Extrae volumen de referencias del CUM: "AMPOLLA POR 3 ML", "1ML", "FRASCO 100 ML"
_VOL_EN_REF = re.compile(r'(\d+(?:[.,]\d+)?)\s*(ml|dl|l)\b', re.IGNORECASE)

# Extrae ratio de concentración del nombre del producto como fallback:
# "DORMICUM® 15MG/3ML" → (15, mg, 3, ml) → "5 mg/mL"
# "BENZOSED® 5MG/ML"   → (5, mg, None, ml) → "5 mg/mL" (denominador implícito = 1)
_CONC_EN_NOMBRE = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(mg|g|mcg|µg|ug|ui|iu|meq|mmol)'
    r'\s*/\s*(?:(\d+(?:[.,]\d+)?)\s*)?(ml|dl|l)\b',
    re.IGNORECASE,
)

# Patrón para extraer el DCI de "NOMBRE EQUIVALENTE A DCI" — tolera espacio faltante antes del DCI
# cubre tanto "EQUIVALENTE A FENTANILO" como "EQUIVALENTE AFENTANILO" (sin espacio, frecuente en CUM)
_EQUIV_PATRON = re.compile(
    r"EQUIVALENTE\s+A?\s*(.+?)(?:\s*\d[\d.,]*\s*(?:MG|MCG|G|UI|U|ML))?$",
    re.IGNORECASE,
)

# Limpia cualquier residuo "EQUIVALENTE [A] X" que quede tras la extracción parcial
_EQUIV_RESIDUO = re.compile(r"\s+EQUIVALENTE\b.*$", re.IGNORECASE)

# Patrón para limpiar concentraciones incrustadas en el nombre
_CONCENTRACION_INCRUSTADA = re.compile(
    r"\s+\d[\d.,]*\s*(?:MG|MCG|G|UI|U|ML|%)\b.*$",
    re.IGNORECASE,
)

# Patrón CUM frecuente: "5 MG DE MIDAZOLAM", "0.5MG DE ALPRAZOLAM CADA TABLETA"
# La DCI real es la parte posterior a "DE".
_DOSIS_DE_INN = re.compile(
    r"^\d[\d.,]*\s*(?:MG|G|MCG|UI|IU|ML|%)\s+DE\s+(.+)$",
    re.IGNORECASE,
)

# Agrega espacio entre letra y dígito cuando van pegados en nombres del CUM:
# "INYECTABLE5" → "INYECTABLE 5", "DORMICUM5MG" → "DORMICUM 5MG"
_LETRA_DIGITO = re.compile(r'([A-Za-zÁÉÍÓÚÀÈÌÒÙáéíóúàèìòùÑñ])(\d)')

# Sinónimos INN: grafías en inglés, variantes -ina/-ino u otras presentes en el CUM → DCI canónico
_SINONIMOS: dict[str, str] = {
    # Variantes inglés → español
    "METOTREXATE":      "METOTREXATO",
    "METHOTREXATE":     "METOTREXATO",
    "DEXAMETHASONE":    "DEXAMETASONA",
    "PREDNISOLONE":     "PREDNISOLONA",
    "HYDROCORTISONE":   "HIDROCORTISONA",
    "TESTOSTERONE":     "TESTOSTERONA",
    "PROGESTERONE":     "PROGESTERONA",
    "FLUOROURACIL":     "FLUOROURACILO",
    "VINCRISTINE":      "VINCRISTINA",
    "VINBLASTINE":      "VINBLASTINA",
    "CYCLOPHOSPHAMIDE": "CICLOFOSFAMIDA",
    "CHLORAMBUCIL":     "CLORAMBUCILO",
    "MERCAPTOPURINE":   "MERCAPTOPURINA",
    # Variantes -ina/-ino frecuentes en el CUM colombiano
    "NIFEDIPINA":       "NIFEDIPINO",
    "AMLODIPINA":       "AMLODIPINO",
    "FELODIPINA":       "FELODIPINO",
    "LERCANIDIPINA":    "LERCANIDIPINO",
    "LACIDIPINA":       "LACIDIPINO",
    "NISOLDIPINA":      "NISOLDIPINO",
    "NIMODIPINA":       "NIMODIPINO",
    "ISRADIPINA":       "ISRADIPINO",
    "BARNIDIPINA":      "BARNIDIPINO",
    # Sinónimos clínicos Colombia — el CUM usa el nombre del fabricante, no siempre el INN
    "ACETAMINOFEN":     "PARACETAMOL",   # nombre colombiano más común en el CUM
    "ACETAMINOFÉN":     "PARACETAMOL",
    "TYLENOL":          "PARACETAMOL",
    "DIPIRONA":         "METAMIZOL",
    "DIPIRONA SODICA":  "METAMIZOL",
    "DIPIRONA SODICA MONOHIDRATADA": "METAMIZOL",
    "METAMIZOL SODICO": "METAMIZOL",
    "MEPERIDINA":       "PETIDINA",
    "PETHIDINE":        "PETIDINA",
    "ALBUTEROL":        "SALBUTAMOL",    # nombre en inglés / EE.UU.
    "VITAMINA C":       "ACIDO ASCORBICO",
    "ÁCIDO ASCÓRBICO":  "ACIDO ASCORBICO",
    "ACIDO ASCORBICO":  "ACIDO ASCORBICO",
    # Variantes inglés adicionales frecuentes en búsquedas
    "FUROSEMIDE":       "FUROSEMIDA",
    "AMOXICILLIN":      "AMOXICILINA",
    "CIPROFLOXACIN":    "CIPROFLOXACINO",
    "CIPROFLOXACINA":   "CIPROFLOXACINO",
    "METRONIDAZOLE":    "METRONIDAZOL",
    "NIFUROXAZIDE":     "NIFUROXAZIDA",
    "MICONAZOLE":       "MICONAZOL",
    "CLOTRIMAZOLE":     "CLOTRIMAZOL",
    "ISOCONAZOLE":      "ISOCONAZOL",
    "OMEPRAZOLE":       "OMEPRAZOL",
    "LOSARTAN":         "LOSARTAN",      # sin tilde — normaliza grafías
    "LOSARTÁN":         "LOSARTAN",
    "CAPTOPRIL":        "CAPTOPRIL",
    "ENALAPRIL":        "ENALAPRIL",
    "ENALAPRILAT":      "ENALAPRIL",
    "MORFINA":          "MORFINA",
    "MORPHINE":         "MORFINA",
    "FENTANYL":         "FENTANILO",
    "FENTANIL":         "FENTANILO",
    "TRAMADOL":         "TRAMADOL",
    "DICLOFENAC":       "DICLOFENACO",
    "DICLOFENACO SODICO":   "DICLOFENACO",
    "DICLOFENACO POTASICO": "DICLOFENACO",
    "KETOPROFEN":       "KETOPROFENO",
    "NAPROXEN":         "NAPROXENO",
    "WARFARIN":         "WARFARINA",
    "HEPARIN":          "HEPARINA",
    "INSULIN":          "INSULINA",
    "METFORMIN":        "METFORMINA",
    "GLIBENCLAMIDE":    "GLIBENCLAMIDA",
    "GLIBENCLAMIDA":    "GLIBENCLAMIDA",
    "ATORVASTATIN":     "ATORVASTATINA",
    "SIMVASTATIN":      "SIMVASTATINA",
    "LOVASTATINA":      "LOVASTATINA",
    "LOVASTATIN":       "LOVASTATINA",
    "CLARITHROMYCIN":   "CLARITROMICINA",
    "AZITHROMYCIN":     "AZITROMICINA",
    "DOXYCYCLINE":      "DOXICICLINA",
    "CLINDAMYCIN":      "CLINDAMICINA",
    "VANCOMYCIN":       "VANCOMICINA",
    "AMPICILLIN":       "AMPICILINA",
    "GENTAMICIN":       "GENTAMICINA",
    "TOBRAMYCIN":       "TOBRAMICINA",
    "FLUCONAZOLE":      "FLUCONAZOL",
    "ITRACONAZOLE":     "ITRACONAZOL",
    "KETOCONAZOLE":     "KETOCONAZOL",
    "ACYCLOVIR":        "ACICLOVIR",
    "ACICLOVIR":        "ACICLOVIR",
    "HALOPERIDOL":      "HALOPERIDOL",
    "DIAZEPAM":         "DIAZEPAM",
    "LORAZEPAM":        "LORAZEPAM",
    "ALPRAZOLAM":       "ALPRAZOLAM",
    "PHENOBARBITAL":    "FENOBARBITAL",
    "PHENYTOIN":        "FENITOINA",
    "FENITOINA":        "FENITOINA",
    "CARBAMAZEPINE":    "CARBAMAZEPINA",
    "VALPROIC ACID":    "ACIDO VALPROICO",
    "ACIDO VALPROICO":  "ACIDO VALPROICO",
    "SALBUTAMOL SULFATO": "SALBUTAMOL",
    "BECLOMETASONA DIPROPIONATO": "BECLOMETASONA",
    "BECLOMETHASONE":   "BECLOMETASONA",
    "BUDESONIDE":       "BUDESONIDA",
    "BUDESONIDA":       "BUDESONIDA",
    "FLUTICASONE":      "FLUTICASONA",
    "FLUTICASONA":      "FLUTICASONA",
    "IPRATROPIUM":      "IPRATROPIO",
    "IPRATROPIO":       "IPRATROPIO",
    "TIOTROPIUM":       "TIOTROPIO",
    "FORMOTEROL":       "FORMOTEROL",
    "SALMETEROL":       "SALMETEROL",
}

# ─── Normalización de unidades ────────────────────────────────────────────────

# Formas farmacéuticas que son polvos para reconstitución: el volumen que aparece
# en unidadreferencia (ej. "VIAL POR 20 ML") es el del solvente, no del fármaco.
# Dividir la masa por ese volumen daría una concentración errónea.
_FORMAS_POLVO = ("POLVO", "LIOFILIZADO")

# Factores de conversión a miligramos-equivalente para comparar homólogos.
# UI/IU no tienen factor universal (depende del fármaco), se dejan como están.
_UNIT_TO_MG: dict[str, float] = {
    "mg": 1.0,
    "g": 1000.0, "gr": 1000.0,
    "mcg": 0.001, "µg": 0.001, "ug": 0.001,
}

# Convierte gramos a miligramos en el NUMERADOR de concentraciones para display uniforme.
# Solo actúa sobre la parte antes de "/" para no convertir denominadores en masa (ej. "5 mg/100 g").
_G_A_MG_RE = re.compile(
    r'(\d+(?:[.,]\d+)?)\s+(?:g|gr)\b(?!/)',
    re.IGNORECASE,
)

# Extrae porcentaje del nombre de producto para formas tópicas: "ACICLOVIR 5% UNGUENTO" → "5%"
_PORCENTAJE_EN_NOMBRE = re.compile(r'(\d+(?:[.,]\d+)?)\s*%', re.IGNORECASE)

# Extrae dosis standalone (sin denominador /mL) del nombre del producto para sólidos orales:
# "VALACICLOVIR 1 G" → (1, 'g'), "AMOXICILINA 500 MG" → (500, 'mg')
_DOSIS_ORAL_EN_NOMBRE = re.compile(
    r'\b(\d+(?:[.,]\d+)?)\s*(mg|g|gr)\b(?!\s*/)',
    re.IGNORECASE,
)


def _to_mg_equiv(valor: float, unidad: str) -> float:
    """Convierte valor de concentración a mg-equivalente para comparación de homólogos."""
    factor = _UNIT_TO_MG.get(unidad.lower(), None)
    return round(valor * factor, 6) if factor is not None else valor


def _normalizar_g_a_mg(conc: str) -> str:
    """Convierte gramos a mg solo en el NUMERADOR: '0.5 g' → '500 mg', '1 gr' → '1000 mg'.
    No toca el denominador ('5 mg/100 g' permanece igual — evita '5 mg/100000 mg')."""
    def repl(m: re.Match) -> str:
        val = float(m.group(1).replace(',', '.'))
        return f"{val * 1000:g} mg"
    # Dividir en numerador/denominador y solo convertir el numerador
    partes = conc.split('/', 1)
    partes[0] = _G_A_MG_RE.sub(repl, partes[0])
    return '/'.join(partes)


def normalizar_principio(principio: str) -> str:
    """
    Extrae el DCI limpio de un principio activo del CUM.

    Ejemplos:
      "AMOXICILINA TRIHIDRATO EQUIVALENTE A AMOXICILINA" → "AMOXICILINA"
      "CLAVULANATO DE POTASIO EQUIVALENTE A ACIDO CLAVULANICO" → "ACIDO CLAVULANICO"
      "METFORMINA CLORHIDRATO" → "METFORMINA"
      "LEVODOPA" → "LEVODOPA"
    """
    p = str(principio).strip().upper()

    # Patrón "5 MG DE MIDAZOLAM [CADA AMPOLLA]" → extraer solo el INN
    m_de = _DOSIS_DE_INN.match(p)
    if m_de:
        p = m_de.group(1).strip()
        # Quitar sufijos descriptivos como "CADA AMPOLLA", "POR TABLETA", etc.
        p = re.sub(r'\s+(?:CADA|POR)\s+\w+$', '', p).strip()

    # Si hay "EQUIVALENTE [A] X", tomar la parte posterior (tolera espacio faltante)
    m = _EQUIV_PATRON.search(p)
    if m:
        p = m.group(1).strip()

    # Quitar concentraciones incrustadas al final
    p = _CONCENTRACION_INCRUSTADA.sub("", p).strip()

    # Quitar sufijos de sal/forma
    p = _SUFIJOS_SAL.sub("", p)

    # Limpiar cualquier residuo "EQUIVALENTE ..." que no capturó el patrón principal
    p = _EQUIV_RESIDUO.sub("", p).strip()

    # Limpiar espacios múltiples
    p = re.sub(r"\s{2,}", " ", p).strip()

    # Unificar grafías inglés→español para DCI de un solo token (metotrexate → metotrexato)
    p = _SINONIMOS.get(p, p)

    return p


def terminos_busqueda(query: str) -> list[str]:
    """
    Devuelve el término de búsqueda original más sus sinónimos conocidos,
    para ampliar la query al API y no perder productos con grafías alternativas.

    Ejemplo: "NIFEDIPINO" → ["NIFEDIPINO", "NIFEDIPINA"]
             "NIFEDIPINA" → ["NIFEDIPINA", "NIFEDIPINO"]
    """
    q = query.strip().upper()
    terms: set[str] = {q}
    # Si el término es directamente un sinónimo, agregar la forma canónica
    if q in _SINONIMOS:
        terms.add(_SINONIMOS[q])
    # Si el término es la forma canónica, agregar todas las variantes que apuntan a él
    for variante, canonico in _SINONIMOS.items():
        if canonico == q:
            terms.add(variante)
    return list(terms)


_UNIDADES_MASA = {"MG", "G", "MCG", "µG", "UG", "MEQ", "MMOL", "UI", "IU", "U"}

# ──────────────────────────────────────────────────────────────────────────────
# Formas farmacéuticas agrupadas por equivalencia de intercambio.
# La vía de administración tiene precedencia sobre el nombre de forma
# (capsula oral ≠ capsula vaginal aunque el nombre de forma sea igual).
# Definidas aquí para ser compartidas con alternativas.py (importa desde aquí).
# ──────────────────────────────────────────────────────────────────────────────
FORMAS_EQUIVALENTES: dict[str, frozenset[str]] = {
    # Sólidos orales: tabletas y cápsulas son intercambiables entre sí
    "SOLIDO_ORAL": frozenset({
        "TABLETA", "TABLETA RECUBIERTA", "TABLETA CUBIERTA CON PELICULA",
        "TABLETA MASTICABLE", "COMPRIMIDO", "GRAGEA",
        "CAPSULA", "CAPSULA DURA", "CAPSULA BLANDA", "CAPSULA GELATINOSA",
    }),
    # Sólidos orales de liberación prolongada/controlada/modificada/sostenida
    # Tableta LP y Cápsula LP del mismo PA y dosis son intercambiables entre sí
    # NO son intercambiables con la forma de liberación inmediata (SOLIDO_ORAL)
    "SOLIDO_ORAL_LP": frozenset({
        "TABLETA DE LIBERACION PROLONGADA", "TABLETA DE LIBERACION CONTROLADA",
        "TABLETA DE LIBERACION MODIFICADA", "TABLETA DE LIBERACION SOSTENIDA",
        "TABLETA DE LIBERACION RETARDADA", "TABLETA DE ACCION PROLONGADA",
        "CAPSULA DE LIBERACION PROLONGADA", "CAPSULA DE LIBERACION CONTROLADA",
        "CAPSULA DE LIBERACION MODIFICADA", "CAPSULA DE LIBERACION SOSTENIDA",
        "CAPSULA DE LIBERACION RETARDADA", "CAPSULA DE ACCION PROLONGADA",
        "COMPRIMIDO DE LIBERACION PROLONGADA", "COMPRIMIDO DE LIBERACION CONTROLADA",
    }),
    # Dispersables/efervescentes: misma molécula pero preparación diferente
    "ORAL_DISPERSABLE": frozenset({
        "TABLETA DISPERSABLE", "TABLETA EFERVESCENTE",
        "POLVO PARA SUSPENSION ORAL", "GRANULADO ORAL",
    }),
    # Líquidos orales
    "LIQUIDO_ORAL": frozenset({
        "JARABE", "SOLUCION ORAL", "SUSPENSION ORAL", "ELIXIR",
        "GOTAS ORALES", "SOLUCION", "SUSPENSION", "EMULSION ORAL",
    }),
    # Sublingual/bucal
    "SUBLINGUAL": frozenset({
        "TABLETA SUBLINGUAL", "COMPRIMIDO SUBLINGUAL",
        "TABLETA BUCODISPERSABLE", "FILM SUBLINGUAL",
    }),
    # Parenterales (todas las vías inyectables son intercambiables a nivel de dispensación)
    "INYECTABLE": frozenset({
        "SOLUCION INYECTABLE", "POLVO PARA SOLUCION INYECTABLE",
        "SOLUCION PARA INYECCION", "INYECTABLE",
        "POLVO LIOFILIZADO PARA RECONSTITUIR A SOLUCION INYECTABLE",
        "CONCENTRADO PARA SOLUCION PARA PERFUSION",
        "SUSPENSION INYECTABLE", "EMULSION INYECTABLE",
    }),
    # Tópicos cutáneos
    "TOPICO": frozenset({
        "CREMA", "UNGÜENTO", "GEL", "LOCION", "POMADA", "EMULSION", "ESPUMA",
    }),
    # Inhalados
    "INHALADO": frozenset({
        "AEROSOL PARA INHALACION", "POLVO PARA INHALACION",
        "SOLUCION PARA INHALACION", "INHALADOR",
    }),
    # Oftálmicos
    "OFTALMICO": frozenset({
        "COLIRIO", "SOLUCION OFTALMICA", "GOTAS OFTALMICAS",
        "POMADA OFTALMICA", "GEL OFTALMICO",
    }),
    # Vaginales — NO intercambiables con orales aunque tengan el mismo nombre de forma
    "VAGINAL": frozenset({
        "OVULO", "OVULOS", "CAPSULA VAGINAL", "TABLETA VAGINAL",
        "COMPRIMIDO VAGINAL", "CREMA VAGINAL", "GEL VAGINAL",
        "SOLUCION VAGINAL", "ESPUMA VAGINAL",
    }),
    # Rectales
    "RECTAL": frozenset({
        "SUPOSITORIO", "SUPOSITORIOS", "ENEMA", "CREMA RECTAL",
        "GEL RECTAL", "SOLUCION RECTAL",
    }),
    # Transdérmicos
    "TRANSDERMICO": frozenset({
        "PARCHE TRANSDERMICO", "PARCHE", "GEL TRANSDERMICO",
    }),
    # Óticos
    "OTICO": frozenset({"GOTAS OTICAS", "GOTAS ÓTICAS", "SOLUCION OTICA"}),
    # Nasales
    "NASAL": frozenset({
        "SPRAY NASAL", "GOTAS NASALES", "SOLUCION NASAL", "GEL NASAL",
    }),
}

_FORMA_A_GRUPO: dict[str, str] = {
    f: g for g, fs in FORMAS_EQUIVALENTES.items() for f in fs
}

# La vía de administración tiene precedencia: capsula VAGINAL → VAGINAL,
# aunque la forma farmacéutica "CAPSULA" normalmente mapee a SOLIDO_ORAL.
_VIA_A_GRUPO: dict[str, str] = {
    'VAGINAL': 'VAGINAL',
    'RECTAL': 'RECTAL',
    'SUBLINGUAL': 'SUBLINGUAL',
    'BUCAL': 'SUBLINGUAL',
    'SUBLINGUAL - BUCAL': 'SUBLINGUAL',
    'OFTALMICA': 'OFTALMICO',
    'OCULAR': 'OFTALMICO',
    'OTICA': 'OTICO',
    'AUDITIVA': 'OTICO',
    'NASAL': 'NASAL',
    'INTRANASAL': 'NASAL',
    'INHALATORIA': 'INHALADO',
    'PULMONAR': 'INHALADO',
    'INHALACION': 'INHALADO',
    'TRANSDERMICA': 'TRANSDERMICO',
    'CUTANEA': 'TRANSDERMICO',
    'INTRAVENOSA': 'INYECTABLE',
    'INTRAMUSCULAR': 'INYECTABLE',
    'SUBCUTANEA': 'INYECTABLE',
    'PARENTERAL': 'INYECTABLE',
    'INTRAARTICULAR': 'INYECTABLE',
    'INTRATECAL': 'INYECTABLE',
    'INTRAPERITONEAL': 'INYECTABLE',
}


def _grupo_forma(forma: str, via: str = '') -> str:
    """Clasifica una forma farmacéutica en un grupo de equivalencia.
    La vía de administración tiene precedencia. Si no hay coincidencia exacta
    en el diccionario, usa keywords para cubrir las variantes del CUM
    (ej. "UNGUENTO TOPICO", "POLVO PARA RECONSTITUIR A SUSPENSION ORAL").
    """
    via_u = via.strip().upper()
    if via_u in _VIA_A_GRUPO:
        return _VIA_A_GRUPO[via_u]
    f = forma.strip().upper()
    if f in _FORMA_A_GRUPO:
        return _FORMA_A_GRUPO[f]
    # Keyword fallback — mismo orden de prioridad que el componente frontend
    if re.search(r'OFTALM', f):                                                           return 'OFTALMICO'
    if re.search(r'VAGINAL', f):                                                          return 'VAGINAL'
    if re.search(r'RECTAL|SUPOSITORIO', f):                                               return 'RECTAL'
    if re.search(r'\bNASAL\b', f):                                                        return 'NASAL'
    if re.search(r'\bOTIC|OTICA\b', f):                                                   return 'OTICO'
    if re.search(r'INHALACI|INHALADO|INHALADOR|PULMONAR|NEBULIZACI', f):                  return 'INHALADO'
    if re.search(r'PARCHE|TRANSDER', f):                                                  return 'TRANSDERMICO'
    if re.search(r'SUBLINGUAL|BUCODISPERS', f):                                           return 'SUBLINGUAL'
    if re.search(r'LIBERACI.N (PROLONGADA|CONTROLADA|MODIFICADA|SOSTENIDA|RETARDADA)|ACCION PROLONGADA', f): return 'SOLIDO_ORAL_LP'
    if re.search(r'LIOFILIZ|POLVO.*(INYECT|RECONSTITUIR.*INYECT)|CONCENTRADO.*PERFUS|EMULSION INYECT|SUSPENSION INYECT', f): return 'INYECTABLE'
    if re.search(r'INYECT|PARENTERAL', f):                                                return 'INYECTABLE'
    if re.search(r'POLVO PARA (RECONSTITUIR|SUSPENSION)|GRANULADO ORAL|EFERVESCENTE', f): return 'ORAL_DISPERSABLE'
    if re.search(r'TABLETA|COMPRIMIDO|GRAGEA', f):                                        return 'SOLIDO_ORAL'
    if re.search(r'\bCAPSULA\b', f):                                                      return 'SOLIDO_ORAL'
    if re.search(r'JARABE|SOLUCION ORAL|SUSPENSION ORAL|ELIXIR|GOTAS ORAL|EMULSION ORAL', f): return 'LIQUIDO_ORAL'
    if re.search(r'UNGÜENTO|UNGUENTO|POMADA|CREMA|GEL|LOCION|PASTA|EMULSIO|ESPUMA', f):  return 'TOPICO'
    return f


# Grupos que se normalizan a concentración por mL
_GRUPOS_NORM_ML = frozenset({'INYECTABLE', 'LIQUIDO_ORAL'})
# Grupos donde la unidad de referencia es "por dosis"
_GRUPOS_NORM_DOSIS = frozenset({'INHALADO', 'NASAL'})

# Extrae número de dosis/inhalaciones de la referencia: "200 DOSIS" → 200
_NDOSIS_EN_REF = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(?:dosis|inhalaciones|aplicaciones|sprays|pulsaciones)\b',
    re.IGNORECASE,
)


def _conc_desde_nombre(nombre: str) -> str:
    """
    Extrae concentración por mL desde el nombre del producto como último recurso.
    "DORMICUM® 15MG/3ML"        → "5 mg/mL"
    "BENZOSED® 5MG/ML"          → "5 mg/mL"
    "DORMICUM 5 MG/5 ML"        → "1 mg/mL"
    "METFORMINA 500MG TABLETA"  → ""  (no denominator in mL → sin resultado)
    """
    m = _CONC_EN_NOMBRE.search(nombre)
    if not m:
        return ""
    try:
        qty = float(m.group(1).replace(',', '.'))
        unit = m.group(2)
        vol = float(m.group(3).replace(',', '.')) if m.group(3) else 1.0
        vol_unit = m.group(4).lower()
        if vol == 0:
            return ""
        if vol_unit == 'dl':
            vol *= 100
        elif vol_unit == 'l':
            vol *= 1000
        ratio = qty / vol
        u = "UI" if unit.upper() in ("UI", "IU") else unit.lower()
        return f"{ratio:g} {u}/mL"
    except (ValueError, ZeroDivisionError):
        return ""


def _normalizar_por_forma(conc: str, g_forma: str, nombre_prod: str, forma_raw: str = '') -> str:
    """
    Normaliza la concentración según el grupo farmacéutico:
    - INYECTABLE / LIQUIDO_ORAL → ratio /mL desde campos estructurados o nombre.
    - ORAL_DISPERSABLE (polvos para suspensión) → extrae ratio /mL del nombre
      del producto (ej. "AMOXICILINA 250MG/5ML" → "50 mg/mL").
    - TOPICO → extrae porcentaje del nombre (ej. "ACICLOVIR 5% UNGÜENTO" → "5%").
    - INHALADO / NASAL → primer valor+unidad con /dosis.
    - Sólidos orales y otros → sin cambio.
    - POLVO/LIOFILIZADO inyectable → sin normalización /mL.
    """
    if g_forma in _GRUPOS_NORM_ML:
        # Polvos inyectables para reconstitución: la masa total por vial ya es correcta.
        if any(kw in forma_raw.upper() for kw in _FORMAS_POLVO):
            return conc
        if g_forma == 'LIQUIDO_ORAL':
            c_fb = _conc_desde_nombre(nombre_prod)
            if c_fb:
                return c_fb
        # Aceptar solo si tiene unidad de masa antes del /mL (descarta "5 ml/5 ml").
        _masa_por_ml = re.compile(
            r'^\d[\d.,]*\s*(mg|g|mcg|µg|ug|ui|iu|meq|mmol)\s*/mL', re.IGNORECASE
        )
        if _masa_por_ml.match(conc):
            return conc
        c_fb = _conc_desde_nombre(nombre_prod)
        return c_fb if c_fb else conc

    if g_forma == 'ORAL_DISPERSABLE':
        # Polvos para suspensión oral: la concentración real está en el nombre del producto
        # (ej. "AMOXICILINA 250MG/5ML" → 50 mg/mL tras reconstitución).
        # Tabletas efervescentes/dispersables no tienen ratio /mL en el nombre → sin cambio.
        c_fb = _conc_desde_nombre(nombre_prod)
        if c_fb:
            return c_fb
        return conc

    if g_forma == 'TOPICO':
        # Preparaciones tópicas: la concentración estándar es el porcentaje.
        # El CUM frecuentemente almacena "5 U / 100 G" → debería mostrarse como "5%".
        m_pct = _PORCENTAJE_EN_NOMBRE.search(nombre_prod)
        if m_pct:
            return f"{m_pct.group(1).rstrip('0').rstrip('.')}%"
        return conc

    if g_forma in _GRUPOS_NORM_DOSIS:
        if '/dosis' in conc.lower() or '/mL' in conc or '/ml' in conc:
            return conc
        m = re.match(r'^(\d+(?:[.,]\d+)?)\s*(\S+)', conc)
        if m:
            return f"{m.group(1)} {m.group(2)}/dosis"
        return conc

    return conc


def _extraer_presentacion(row: pd.Series, g_forma: str, nombre_prod: str) -> str:
    """
    Extrae la cantidad total por envase/unidad de dispensación.
    Complementa la concentración: mientras la concentración describe cuánto
    principio activo hay por unidad de volumen, la presentación describe el
    tamaño total del envase o la unidad de dispensación.

    Ejemplos:
      INYECTABLE  "AMPOLLA POR 3 ML"      → "3 mL"
      INYECTABLE  "AMPOLLA" + "15MG/3ML"  → "3 mL" (desde nombre)
      INYECTABLE  "BENZOSED 5MG/ML"       → "1 mL" (denominador implícito)
      LIQUIDO_ORAL "FRASCO 60 ML"         → "60 mL"
      INHALADO    "200 DOSIS"             → "200 dosis"
    """
    unidad_ref = str(row.get("unidadreferencia", "")).strip()

    if g_forma == 'INYECTABLE':
        vol_m = _VOL_EN_REF.search(unidad_ref)
        if vol_m:
            vol = float(vol_m.group(1).replace(',', '.'))
            vol_unit = vol_m.group(2).lower()
            if vol_unit == 'dl': vol *= 100
            elif vol_unit == 'l': vol *= 1000
            return f"{vol:g} mL"
        # Fallback: denominador del ratio en el nombre del producto
        nm = _CONC_EN_NOMBRE.search(nombre_prod)
        if nm:
            vol = float(nm.group(3).replace(',', '.')) if nm.group(3) else 1.0
            vol_unit = nm.group(4).lower() if nm.group(4) else 'ml'
            if vol_unit == 'dl': vol *= 100
            elif vol_unit == 'l': vol *= 1000
            return f"{vol:g} mL"
        return ""

    if g_forma == 'LIQUIDO_ORAL':
        vol_m = _VOL_EN_REF.search(unidad_ref)
        if vol_m:
            vol = float(vol_m.group(1).replace(',', '.'))
            vol_unit = vol_m.group(2).lower()
            if vol_unit == 'dl': vol *= 100
            elif vol_unit == 'l': vol *= 1000
            return f"{vol:g} mL"
        return ""

    if g_forma == 'INHALADO':
        m_d = _NDOSIS_EN_REF.search(unidad_ref)
        if m_d:
            n = int(float(m_d.group(1).replace(',', '.')))
            return f"{n} dosis"
        return ""

    return ""


def construir_concentracion(row: pd.Series) -> str:
    """
    Construye la concentración real a partir de cantidad + unidad + unidadreferencia.
    El campo 'concentracion' del API contiene letras (A/B/S), no valores.

    Para líquidos/inyectables, normaliza a concentración por mL cuando la referencia
    contiene un volumen: "15 mg / AMPOLLA POR 3 ML" → "5 mg/mL" (=5 mg/mL).
    Esto permite comparar correctamente 15mg/3mL, 50mg/10mL y 5mg/1mL como idénticos.
    """
    cantidad = str(row.get("cantidad", "")).strip()
    unidad = str(row.get("unidad", "")).strip()
    unidad_ref = str(row.get("unidadreferencia", "")).strip()
    unidad_medida = str(row.get("unidadmedida", "")).strip()

    if not cantidad or cantidad in ("nan", "None", ""):
        return ""

    # Valores de campo que no son unidades reales (basura del CUM)
    _INVALIDOS = {"nan", "None", "U", "", "SI", "NO", "S", "N", "N/A", "NA"}

    # Unidad real: preferir unidadmedida, luego unidad; descartar valores inválidos
    unidad_real = unidad_medida if unidad_medida.upper() not in _INVALIDOS else unidad
    if unidad_real.upper() in _INVALIDOS:
        unidad_real = "mg"  # default para sólidos orales

    # Normalizar a por-mL cuando unidad_ref contiene un volumen numérico y la unidad
    # es de masa (mg, mcg, UI…). Ejemplos:
    #   "15 mg" + "AMPOLLA POR 3 ML"  → 15/3 = 5   → "5 mg/mL"
    #   "50 mg" + "AMPOLLA POR 10 ML" → 50/10 = 5  → "5 mg/mL"
    #   " 5 mg" + "1 ML DE SOLUCION"  → 5/1  = 5   → "5 mg/mL"
    #   " 1 mg" + "1ML"               → 1/1  = 1   → "1 mg/mL"
    # EXCEPCIÓN: polvos/liofilizados — el volumen es el del solvente de reconstitución,
    # no de la solución final. "250 mg / VIAL 20 ML" NO es 12.5 mg/mL del fármaco.
    forma_raw_conc = str(row.get("formafarmaceutica", "")).strip().upper()
    es_polvo = any(kw in forma_raw_conc for kw in _FORMAS_POLVO)

    if (not es_polvo
            and unidad_ref and unidad_ref.upper() not in _INVALIDOS
            and unidad_real.upper() in _UNIDADES_MASA):
        vol_m = _VOL_EN_REF.search(unidad_ref)
        if vol_m:
            try:
                qty = float(cantidad.replace(',', '.'))
                vol = float(vol_m.group(1).replace(',', '.'))
                vol_unit = vol_m.group(2).lower()
                if vol > 0:
                    if vol_unit == 'dl':
                        vol *= 100
                    elif vol_unit == 'l':
                        vol *= 1000
                    ratio = qty / vol
                    u = "UI" if unidad_real.upper() in ("UI", "IU") else unidad_real.lower()
                    return f"{ratio:g} {u}/mL"
            except (ValueError, ZeroDivisionError):
                pass

    # Casing consistente con el path normalizado: UI en mayúsculas, resto en minúsculas
    unidad_display = "UI" if unidad_real.upper() in ("UI", "IU") else unidad_real.lower()
    base = f"{cantidad} {unidad_display}"

    # Si la unidad original era "U" (inválida, convertida a mg por defecto) y el resultado
    # parece incorrecto (cantidad pequeña como "1 mg"), intentar extraer la dosis del nombre
    # del producto para sólidos orales. Ejemplo: VALACICLOVIR 1 G → qty=1 U → "1 mg" es
    # incorrecto; el nombre tiene "1 G" → extraer → "1000 mg".
    if unidad.upper() in _INVALIDOS and unidad_real == "mg":
        nombre_raw = str(row.get("producto", "")).upper()
        m_oral = _DOSIS_ORAL_EN_NOMBRE.search(nombre_raw)
        if m_oral:
            val = float(m_oral.group(1).replace(',', '.'))
            u_name = m_oral.group(2).lower()
            if u_name in ('g', 'gr'):
                val *= 1000
                u_name = 'mg'
            base = f"{val:g} {u_name}"

    # Agregar referencia SOLO si contiene un valor numérico real (volumen, masa, etc.)
    # Excluir: nombres de forma farmacéutica sin dígitos, conteos de dosis,
    # polvos/liofilizados, y casos donde la unidad principal ya es un volumen
    # (unidad=mL indica que la cantidad es un volumen, no una masa — appending daría
    # "5 ml/5 ml" que no tiene sentido clínico).
    _UNIDADES_VOLUMEN = {"ML", "DL", "L", "CC", "CM3"}
    if (not es_polvo
            and unidad_real.upper() not in _UNIDADES_VOLUMEN
            and unidad_ref and unidad_ref.upper() not in _INVALIDOS
            and unidad_ref.upper() != unidad_real.upper()
            and re.search(r'\d', unidad_ref)
            and not _NDOSIS_EN_REF.search(unidad_ref)):
        # Extraer solo "número + unidad" limpio, ignorando texto descriptivo anterior/posterior.
        # "100 G DE UNGUENTO"           → "100 g"
        # "CADA 100 ML DE SUSPENSION"   → "100 ml"  (re.search ignora el prefijo textual)
        _m_ref = re.search(
            r'(\d[\d.,]*)\s*(mg|g|gr|gramo[s]?|kg|mcg|µg|ml|dl|l|cm|mm|%|ui|iu)\b',
            unidad_ref.strip(), re.IGNORECASE,
        )
        if _m_ref:
            num  = _m_ref.group(1)
            unit = re.sub(r'gramo[s]?', 'g', _m_ref.group(2), flags=re.IGNORECASE).lower()
            unit = 'UI' if unit in ('ui', 'iu') else unit
            ref_display = f"{num} {unit}"
        else:
            ref_display = unidad_ref
        base = f"{base}/{ref_display}"

    return base.strip()


@dataclass
class MedicamentoTransformado:
    cum_id: str                          # expedientecum-consecutivocum
    expedientecum: str
    consecutivocum: str
    nombre_comercial: str
    principios_activos_raw: list[str]    # tal como vienen del API
    principios_dci: list[str]            # normalizados
    tipo_formula: str                    # monocomponente|biconjugado|triconjugado|tetraconjugado
    concentraciones: list[str]           # una por componente
    concentracion_display: str           # para mostrar en UI
    dosis_numerica: float | None         # primer valor numérico de concentraciones[0] (para comparar exacto)
    presentacion: str                    # tamaño del envase/unidad: "3 mL", "60 mL", "200 dosis", ""
    forma_farmaceutica: str
    via_administracion: str
    atc: str
    descripcion_atc: str
    laboratorio: str
    registro_sanitario: str
    estado_registro: str
    estado_cum: str
    modalidad: str
    # Fuente del registro: CUM_ACTIVO | CUM_RENOVACION
    fuente:               str              = field(default='CUM_ACTIVO')
    # Campos opcionales enriquecidos por LLM (None si el caché aún no tiene este CUM)
    principios_dci_llm:   list[str] | None = field(default=None)
    dosis_total_mg:       float | None     = field(default=None)
    concentracion_mg_ml:  float | None     = field(default=None)
    volumen_ml_por_unidad: float | None    = field(default=None)
    forma_normalizada:    str | None       = field(default=None)
    via_normalizada:      list[str] | None = field(default=None)
    atc_llm:              str | None       = field(default=None)
    tipo_formula_llm:     str | None       = field(default=None)  # MONO, BI, TRI, TETRA
    componentes_llm:      list | None      = field(default=None)  # [{"dci","concentracion_mg_ml","dosis_mg"}]
    notas_llm:            str | None       = field(default=None)


_TIPO_FORMULA = {1: "monocomponente", 2: "biconjugado", 3: "triconjugado", 4: "tetraconjugado"}


def agrupar_y_transformar(df: pd.DataFrame) -> list[MedicamentoTransformado]:
    """
    Agrupa las filas del CUM por (expedientecum, consecutivocum) y reconstruye
    cada presentación como un MedicamentoTransformado con su lista de componentes.
    """
    resultados: list[MedicamentoTransformado] = []

    grupo_cols = ["expedientecum", "consecutivocum"]
    for (exped, consec), grupo in df.groupby(grupo_cols):
        primera = grupo.iloc[0]

        # Deduplicar por principio activo (hay filas duplicadas por fabricante/importador)
        grupo_uniq = grupo.drop_duplicates(subset=["principioactivo"])

        principios_raw = grupo_uniq["principioactivo"].dropna().tolist()
        principios_dci = [normalizar_principio(p) for p in principios_raw]

        # Eliminar vacíos, repetidos, y valores basura del CUM (códigos de 1-2 chars como "A", "S")
        vistos: set[str] = set()
        principios_dci_uniq: list[str] = []
        principios_raw_uniq: list[str] = []
        for raw, dci in zip(principios_raw, principios_dci):
            if dci and len(dci) >= 3 and dci not in vistos:
                vistos.add(dci)
                principios_dci_uniq.append(dci)
                principios_raw_uniq.append(raw)

        n = len(principios_dci_uniq)
        tipo = _TIPO_FORMULA.get(n, "tetraconjugado" if n >= 4 else "monocomponente")

        nombre_prod = _LETRA_DIGITO.sub(r'\1 \2', str(primera.get("producto", "")).strip())
        nombre_prod = re.sub(r' {2,}', ' ', nombre_prod).strip()
        g_forma = _grupo_forma(
            str(primera.get("formafarmaceutica", "")).strip().upper(),
            str(primera.get("viaadministracion", "")).strip().upper(),
        )

        # Concentraciones por componente, normalizadas según forma farmacéutica
        forma_cruda = str(primera.get("formafarmaceutica", "")).strip()
        concentraciones: list[str] = []
        _conc_vistos: set[str] = set()
        for _, fila in grupo_uniq.iterrows():
            c = construir_concentracion(fila)
            if c:
                c_norm = _normalizar_por_forma(c, g_forma, nombre_prod, forma_cruda)
                # Normalizar gramos a miligramos para display uniforme ("0.5 g" → "500 mg")
                c_norm = _normalizar_g_a_mg(c_norm)
                if c_norm not in _conc_vistos:
                    _conc_vistos.add(c_norm)
                    concentraciones.append(c_norm)

        # Texto de concentración para mostrar
        # Monocomponente: solo la concentración (el DCI ya se muestra en otro campo)
        # Multicomponente: "DCI1 conc1 + DCI2 conc2" para distinguir cuál dosis es cuál
        if not concentraciones:
            concentracion_display = ""
        elif len(principios_dci_uniq) == 1:
            concentracion_display = concentraciones[0]
        elif len(principios_dci_uniq) == len(concentraciones):
            partes = [f"{dci} {c}" for dci, c in zip(principios_dci_uniq, concentraciones)]
            concentracion_display = " + ".join(partes)
        else:
            concentracion_display = " + ".join(concentraciones)

        # Valor numérico de la dosis del primer componente normalizado a mg-equivalente.
        # Esto permite comparar homólogos con diferentes unidades: "0.5 g" y "500 mg"
        # producen dosis_numerica=500, "200 mcg" produce 0.2 (coincide con "0.2 mg").
        dosis_numerica: float | None = None
        if concentraciones:
            _m_du = re.match(
                r'^(\d+(?:[.,]\d+)?)\s*(mg|g|gr|mcg|µg|ug|ui|iu|meq|mmol|%)',
                concentraciones[0], re.IGNORECASE,
            )
            if _m_du:
                try:
                    dosis_numerica = _to_mg_equiv(
                        float(_m_du.group(1).replace(',', '.')), _m_du.group(2)
                    )
                except ValueError:
                    pass
            if dosis_numerica is None:
                m_num = _NUM_DOSIS.search(concentraciones[0])
                if m_num:
                    try:
                        dosis_numerica = float(m_num.group(1).replace(',', '.'))
                    except ValueError:
                        pass

        resultados.append(MedicamentoTransformado(
            cum_id=f"{exped}-{consec}",
            expedientecum=str(exped),
            consecutivocum=str(consec),
            nombre_comercial=nombre_prod,
            principios_activos_raw=principios_raw_uniq,
            principios_dci=principios_dci_uniq,
            tipo_formula=tipo,
            concentraciones=concentraciones,
            concentracion_display=concentracion_display,
            dosis_numerica=dosis_numerica,
            presentacion=_extraer_presentacion(primera, g_forma, nombre_prod),
            forma_farmaceutica=str(primera.get("formafarmaceutica", "")).strip().upper(),
            via_administracion=str(primera.get("viaadministracion", "")).strip().upper(),
            atc=str(primera.get("atc", "")).strip().upper().replace(".", ""),
            descripcion_atc=str(primera.get("descripcionatc", "")).strip().upper(),
            laboratorio=str(primera.get("titular", primera.get("nombrerol", ""))).strip(),
            registro_sanitario=str(primera.get("registrosanitario", "")).strip(),
            estado_registro=str(primera.get("estadoregistro", "")).strip().capitalize(),
            estado_cum=str(primera.get("estadocum", "")).strip().capitalize(),
            modalidad=str(primera.get("modalidad", "")).strip(),
        ))

    return resultados
